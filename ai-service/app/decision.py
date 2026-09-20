import json
from typing import Any

from .candidate_validation import (
    merge_authoritative_validation,
    normalize_candidate_response,
    validate_candidate_response,
)
from .evaluation import evaluate
from .game_contracts import load_candidate_response_schema, load_game_knowledge
from .java_bridge import JavaBridge, JavaBridgeError
from .models import DecisionPlayerContext, DecisionRequest, EvaluationRequest, MatchContext, OpponentContext, PlayerContext
from .ollama_client import OllamaClient, OllamaError
from .prompting import SYSTEM_PROMPT, build_user_prompt


class DecisionError(RuntimeError):
    """Raised when no final program can be selected for a decision."""


async def decide(
    request: DecisionRequest,
    ollama: OllamaClient,
    java_bridge: JavaBridge,
    model: str,
    context_window: int | None = None,
    max_output_tokens: int | None = None,
    keep_alive: str | int | None = None,
    prompt_mode: str = "compact",
) -> dict[str, Any]:
    contexts = {
        "player_a": _match_context(request, request.player_a, request.player_b),
        "player_b": _match_context(request, request.player_b, request.player_a),
    }
    generated: dict[str, list[dict[str, Any]]] = {}
    for key, context in contexts.items():
        try:
            generated[key] = await _generate_authorized_candidates(
                context=context,
                candidate_count=request.candidate_count,
                ollama=ollama,
                java_bridge=java_bridge,
                model=model,
                context_window=context_window,
                max_output_tokens=max_output_tokens,
                keep_alive=keep_alive,
                prompt_mode=prompt_mode,
            )
        except DecisionError as exc:
            raise DecisionError(f"{key} candidate generation failed: {exc}") from exc

    selected: dict[str, dict[str, Any]] = {}
    for key, context in contexts.items():
        opponent_key = "player_b" if key == "player_a" else "player_a"
        candidates = generated[key]
        opponents = generated[opponent_key]
        # Keep every decision bounded for local inference and the simulator.
        opponent_limit = max(1, min(len(opponents), 200 // max(1, len(candidates))))
        evaluation = EvaluationRequest.model_validate({
            "candidates": candidates,
            "opponents": opponents[:opponent_limit],
            "seeds": [request.seed + request.round_number * 1009],
        })
        try:
            ranking = await evaluate(evaluation, java_bridge)
        except JavaBridgeError as exc:
            raise DecisionError(f"{key} simulation/ranking failed: {exc}") from exc
        if not ranking.get("ranking"):
            raise DecisionError(f"no ranked program was produced for {key}")
        selected_id = ranking["ranking"][0].get("candidate_id")
        program = next((item["brain"] for item in candidates if item["program_id"] == selected_id), None)
        if not isinstance(program, dict):
            raise DecisionError(f"selected program for {key} was not found")
        selected[key] = {
            "program": program,
            "selected_abilities": context.self.selected_abilities,
        }

    return {
        "match_id": request.match_id,
        "ruleset_version": request.ruleset_version,
        "round_number": request.round_number,
        "player_a": selected["player_a"],
        "player_b": selected["player_b"],
    }


def _match_context(
    request: DecisionRequest,
    self_context: DecisionPlayerContext,
    opponent_context: DecisionPlayerContext,
) -> MatchContext:
    return MatchContext.model_validate({
        "schema_version": request.schema_version,
        "ruleset_version": request.ruleset_version,
        "brain_schema_version": request.brain_schema_version,
        "match_id": request.match_id,
        "round_number": request.round_number,
        "seed": request.seed,
        "self": PlayerContext(
            selected_abilities=self_context.selected_abilities,
            slot=self_context.slot,
            team_number=self_context.team_number,
        ),
        "opponent": OpponentContext(
            known_abilities=self_context.known_opponent_abilities,
            slot=self_context.opponent_slot,
            team_number=self_context.opponent_team_number,
        ),
        "previous_round_telemetry": request.previous_round_telemetry,
    })


async def _generate_authorized_candidates(
    *,
    context: MatchContext,
    candidate_count: int,
    ollama: OllamaClient,
    java_bridge: JavaBridge,
    model: str,
    context_window: int | None,
    max_output_tokens: int | None,
    keep_alive: str | int | None,
    prompt_mode: str,
) -> list[dict[str, Any]]:
    knowledge = load_game_knowledge()
    standard_abilities = {int(value) for value in knowledge["standardAbilities"]}
    allowed_ability_ids = tuple(sorted(standard_abilities | set(context.self.selected_abilities)))
    response_schema = load_candidate_response_schema(candidate_count, allowed_ability_ids)
    try:
        reply = await ollama.chat(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(
                context=context,
                candidate_count=candidate_count,
                instructions=None,
                prompt_mode=prompt_mode,
            ),
            temperature=0.2,
            response_schema=response_schema,
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            keep_alive=keep_alive,
        )
    except (OllamaError, ValueError) as exc:
        raise DecisionError(f"candidate generation failed: {exc}") from exc

    if reply.parse_error is not None or not isinstance(reply.parsed, dict):
        raise DecisionError("candidate generation returned invalid JSON")
    raw_candidates = reply.parsed.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) != candidate_count:
        raise DecisionError("candidate generation returned the wrong candidate count")
    candidate_ids = [candidate.get("candidate_id") for candidate in raw_candidates if isinstance(candidate, dict)]
    if len(candidate_ids) != candidate_count or len(set(candidate_ids)) != candidate_count:
        raise DecisionError("candidate generation returned duplicate or invalid candidate IDs")

    normalized = normalize_candidate_response(
        reply.parsed,
        context,
        repair_selected_metadata=True,
    )
    prevalidation = validate_candidate_response(normalized, context)
    try:
        authoritative = await java_bridge.invoke("validate-batch", {
            "items": [
                {"candidateId": candidate.get("candidate_id"), "brain": candidate.get("program")}
                for candidate in normalized["candidates"]
            ],
        })
    except JavaBridgeError as exc:
        raise DecisionError(f"authoritative candidate validation failed: {exc}") from exc
    validation = merge_authoritative_validation(prevalidation, authoritative)
    candidates = [
        {
            "program_id": candidate["candidate_id"],
            "brain": candidate["program"],
        }
        for candidate, result in zip(normalized["candidates"], validation)
        if result.valid and isinstance(candidate.get("program"), dict)
    ]
    if not candidates:
        diagnostics = [
            {
                "candidate_id": result.candidate_id,
                "issues": [issue.model_dump(mode="json") for issue in result.issues],
            }
            for result in validation
        ]
        raise DecisionError(
            "candidate generation produced no valid programs: "
            + json.dumps(diagnostics, separators=(",", ":"))
        )
    return candidates
