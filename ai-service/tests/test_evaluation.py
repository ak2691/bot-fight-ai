import asyncio
from typing import Any

from app.evaluation import evaluate
from app.models import EvaluationRequest


class FakeBridge:
    async def invoke(self, mode: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert mode == "simulate-batch"
        results = []
        for scenario in payload["scenarios"]:
            winner = "candidate" if scenario["candidateBrain"]["strength"] > 1 else None
            results.append({
                "scenarioId": scenario["scenarioId"],
                "status": "COMPLETED",
                "winner": winner,
            })
        return {"rulesetVersion": "duel-v1", "scenarioCount": len(results), "results": results}


def test_evaluation_ranks_wins_before_draws() -> None:
    request = EvaluationRequest.model_validate({
        "candidates": [
            {"program_id": "draw", "brain": {"strength": 1}},
            {"program_id": "winner", "brain": {"strength": 2}},
        ],
        "opponents": [{"program_id": "baseline", "brain": {}}],
        "seeds": [1, 2],
    })
    result = asyncio.run(evaluate(request, FakeBridge()))  # type: ignore[arg-type]
    assert result["scenario_count"] == 4
    assert [item["candidate_id"] for item in result["ranking"]] == ["winner", "draw"]
    assert result["ranking"][0]["score"] == 1.0
    assert result["ranking"][1]["score"] == 0.5
