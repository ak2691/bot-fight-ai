import asyncio
import json

from app.decision import decide
from app.models import DecisionRequest
from app.ollama_client import OllamaReply


def request() -> DecisionRequest:
    return DecisionRequest.model_validate({
        "match_id": "dev-ai-42",
        "ruleset_version": "duel-v1",
        "brain_schema_version": "bot-logic-tree-v1",
        "round_number": 1,
        "seed": 42,
        "candidate_count": 2,
        "player_a": {
            "selected_abilities": [1],
            "known_opponent_abilities": [3],
            "slot": 1,
            "team_number": 1,
            "opponent_slot": 2,
            "opponent_team_number": 2,
        },
        "player_b": {
            "selected_abilities": [3],
            "known_opponent_abilities": [1],
            "slot": 2,
            "team_number": 2,
            "opponent_slot": 1,
            "opponent_team_number": 1,
        },
    })


class FakeOllama:
    def __init__(self):
        self.stages = []

    async def chat(self, *, user_prompt, **_kwargs):
        prompt = json.loads(user_prompt)
        self.stages.append(prompt.get("stage", "compiler"))
        ability = prompt["game_and_match_context"]["match"]["self"]["selected_abilities"][0]
        candidates = []
        for index in range(2):
            candidates.append({
                "candidate_id": f"candidate-{index}",
                "program": {
                    "version": "bot-logic-tree-v1",
                    "loadout": {"abilities": [ability]},
                    "customVariables": [],
                    "roots": [{"branches": [{
                        "conditions": [{"type": "always"}],
                        "actions": [{"action": ability, "selectable": "opponent_1"}],
                        "children": [],
                    }]}],
                },
            })
        return OllamaReply(
            model="fake",
            content=json.dumps({"candidates": candidates}),
            parsed={"candidates": candidates},
            parse_error=None,
            metadata={},
        )


class FakeBridge:
    def __init__(self):
        self.modes = []

    async def invoke(self, mode, payload):
        self.modes.append(mode)
        if mode == "validate-batch":
            return {"results": [
                {"index": index, "valid": True, "errors": []}
                for index, _item in enumerate(payload["items"])
            ]}
        if mode == "simulate-batch":
            return {
                "rulesetVersion": "duel-v1",
                "scenarioCount": len(payload["scenarios"]),
                "results": [
                    {"scenarioId": scenario["scenarioId"], "status": "COMPLETED", "winner": None}
                    for scenario in payload["scenarios"]
                ],
            }
        raise AssertionError(mode)


def test_decide_returns_final_programs_without_candidate_arrays():
    bridge = FakeBridge()
    ollama = FakeOllama()
    result = asyncio.run(decide(request(), ollama, bridge, "fake-model"))

    assert set(result) == {"match_id", "ruleset_version", "round_number", "player_a", "player_b"}
    assert "candidates" not in result
    assert result["player_a"]["program"]["version"] == "bot-logic-tree-v1"
    assert result["player_b"]["selected_abilities"] == [3]
    assert bridge.modes.count("validate-batch") == 2
    assert bridge.modes.count("simulate-batch") == 2
    assert ollama.stages == ["compiler", "compiler"]
