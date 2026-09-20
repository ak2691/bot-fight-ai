from typing import Any

from .java_bridge import JavaBridge
from .models import EvaluationRequest


async def evaluate(request: EvaluationRequest, bridge: JavaBridge) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    lookup: dict[str, tuple[str, str]] = {}
    sequence = 0
    for candidate in request.candidates:
        for opponent in request.opponents:
            for seed in request.seeds:
                scenario_id = f"eval-{sequence}"
                sequence += 1
                lookup[scenario_id] = (candidate.program_id, opponent.program_id)
                scenarios.append({
                    "scenarioId": scenario_id,
                    "seed": seed,
                    "candidateBrain": candidate.brain,
                    "opponentBrain": opponent.brain,
                })

    batch = await bridge.invoke("simulate-batch", {"scenarios": scenarios})
    summaries: dict[str, dict[str, Any]] = {
        candidate.program_id: {
            "candidate_id": candidate.program_id,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "rejected": 0,
            "failed": 0,
            "score": 0.0,
        }
        for candidate in request.candidates
    }
    for result in batch.get("results", []):
        scenario_id = result.get("scenarioId")
        candidate_id, _ = lookup.get(scenario_id, (None, None))
        if candidate_id is None:
            continue
        summary = summaries[candidate_id]
        status = result.get("status")
        winner = result.get("winner")
        if status == "REJECTED":
            summary["rejected"] += 1
        elif status != "COMPLETED":
            summary["failed"] += 1
        elif winner == "candidate":
            summary["wins"] += 1
        elif winner == "opponent":
            summary["losses"] += 1
        else:
            summary["draws"] += 1

    for summary in summaries.values():
        completed = summary["wins"] + summary["draws"] + summary["losses"]
        summary["score"] = round(
            (summary["wins"] + 0.5 * summary["draws"]) / completed, 6
        ) if completed else 0.0
    ranking = sorted(
        summaries.values(),
        key=lambda item: (-item["score"], -item["wins"], item["failed"] + item["rejected"], item["candidate_id"]),
    )
    for index, item in enumerate(ranking, start=1):
        item["rank"] = index
    return {
        "ruleset_version": batch.get("rulesetVersion"),
        "scenario_count": batch.get("scenarioCount"),
        "ranking": ranking,
        "scenario_results": batch.get("results", []),
    }
