import logging

from fastapi import FastAPI, HTTPException

from .candidate_validation import (
    merge_authoritative_validation,
    normalize_candidate_response,
    validate_candidate_response,
)
from .config import get_settings
from .decision import DecisionError, decide
from .evaluation import evaluate as evaluate_candidates
from .game_contracts import load_candidate_response_schema, load_game_knowledge
from .java_bridge import JavaBridge, JavaBridgeError
from .models import DecisionRequest, EvaluationRequest, GenerateRequest, GenerateResponse, SimulationRequest, ValidateBrainRequest
from .ollama_client import OllamaClient, OllamaError
from .prompting import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt


logger = logging.getLogger(__name__)
settings = get_settings()
ollama = OllamaClient(
    base_url=settings.ollama_base_url,
    timeout_seconds=settings.ollama_timeout_seconds,
)
java_bridge = JavaBridge(
    server_root=settings.botfight_server_root,
    timeout_seconds=settings.simulator_timeout_seconds,
)

app = FastAPI(
    title="Bot Fight AI",
    version="0.2.0-local",
    description=(
        "Local structured Bot Fight candidate generation with exported canonical "
        "game knowledge and a development bridge to authoritative Java validation/simulation."
    ),
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/ollama/health")
async def ollama_health() -> dict[str, object]:
    try:
        payload = await ollama.health()
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    models = payload.get("models", [])
    return {
        "status": "ok",
        "base_url": settings.ollama_base_url,
        "configured_model": settings.ollama_model,
        "installed_models": models,
    }


@app.get("/v1/contracts")
async def contracts() -> dict[str, object]:
    knowledge = load_game_knowledge()
    return {
        "contract_version": knowledge["contractVersion"],
        "ruleset_version": knowledge["rulesetVersion"],
        "brain_schema_version": knowledge["brainSchemaVersion"],
        "validator_version": knowledge["validatorVersion"],
        "game_source": knowledge["source"],
        "ability_count": len(knowledge["abilityDefinitions"]),
    }


@app.post("/v1/validate")
async def validate(request: ValidateBrainRequest) -> dict[str, object]:
    try:
        return await java_bridge.invoke("validate", request.model_dump(mode="json"))
    except JavaBridgeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/simulate")
async def simulate(request: SimulationRequest) -> dict[str, object]:
    payload = {
        "scenarioId": request.scenario_id,
        "seed": request.seed,
        "candidateBrain": request.candidate_brain,
        "opponentBrain": request.opponent_brain,
    }
    try:
        return await java_bridge.invoke("simulate", payload)
    except JavaBridgeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/evaluate")
async def evaluate(request: EvaluationRequest) -> dict[str, object]:
    try:
        return await evaluate_candidates(request, java_bridge)
    except JavaBridgeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    model = request.model or settings.ollama_model
    knowledge = load_game_knowledge()
    standard_abilities = {int(value) for value in knowledge["standardAbilities"]}
    allowed_ability_ids = tuple(sorted(standard_abilities | set(request.context.self.selected_abilities)))
    user_prompt = build_user_prompt(
        context=request.context,
        candidate_count=request.candidate_count,
        instructions=request.instructions,
        prompt_mode=settings.prompt_mode,
    )
    try:
        reply = await ollama.chat(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=request.temperature,
            response_schema=load_candidate_response_schema(request.candidate_count, allowed_ability_ids),
            context_window=settings.ollama_context_window,
            max_output_tokens=settings.ollama_max_output_tokens,
            keep_alive=settings.ollama_keep_alive,
        )
    except (OllamaError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    normalized_response = normalize_candidate_response(
        reply.parsed,
        request.context,
        repair_selected_metadata=True,
    )
    candidate_validation = (
        validate_candidate_response(normalized_response, request.context)
        if reply.parse_error is None
        else []
    )
    if isinstance(normalized_response, dict) and isinstance(normalized_response.get("candidates"), list) and normalized_response["candidates"]:
        items = [
            {
                "candidateId": candidate.get("candidate_id") if isinstance(candidate, dict) else None,
                "brain": candidate.get("program") if isinstance(candidate, dict) else None,
            }
            for candidate in normalized_response["candidates"][:20]
        ]
        try:
            authoritative = await java_bridge.invoke("validate-batch", {"items": items})
            candidate_validation = merge_authoritative_validation(candidate_validation, authoritative)
        except JavaBridgeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return GenerateResponse(
        model=reply.model,
        prompt_version=PROMPT_VERSION,
        candidate_count=request.candidate_count,
        raw_response=reply.content,
        parsed_response=normalized_response,
        parse_error=reply.parse_error,
        candidate_validation=candidate_validation,
        ollama_metadata=reply.metadata,
    )


@app.post("/v1/decide")
async def decide_programs(request: DecisionRequest) -> dict[str, object]:
    try:
        return await decide(
            request=request,
            ollama=ollama,
            java_bridge=java_bridge,
            model=settings.ollama_model,
            context_window=settings.ollama_context_window,
            max_output_tokens=settings.ollama_max_output_tokens,
            keep_alive=settings.ollama_keep_alive,
            prompt_mode=settings.prompt_mode,
        )
    except (DecisionError, JavaBridgeError) as exc:
        logger.error(
            "Bot Fight AI decision failed: match_id=%s round=%s candidate_count=%s error=%s",
            request.match_id,
            request.round_number,
            request.candidate_count,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
