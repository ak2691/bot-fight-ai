from app.candidate_validation import (
    merge_authoritative_validation,
    normalize_candidate_response,
    validate_candidate_response,
)
from app.models import MatchContext


def context() -> MatchContext:
    return MatchContext.model_validate({
        "schema_version": "bot-fight-ai-match-context-v1",
        "ruleset_version": "duel-v1",
        "brain_schema_version": "bot-logic-tree-v1",
        "match_id": "test-match",
        "round_number": 1,
        "seed": 42,
        "self": {"selected_abilities": [1]},
        "opponent": {"known_abilities": [3], "observations": []},
    })


def test_accepts_known_ability_action() -> None:
    payload = {"candidates": [{
        "candidate_id": "candidate-1",
        "program": {
            "version": "bot-logic-tree-v1",
            "loadout": {"abilities": [1]},
            "roots": [{"branches": [{
                "conditions": [{"type": "always"}],
                "actions": [{"action": 1, "selectable": "opponent_1"}],
                "children": [],
            }]}],
        },
    }]}
    result = validate_candidate_response(payload, context())
    assert result[0].valid is True


def test_rejects_rotation_only_candidate() -> None:
    payload = {"candidates": [{
        "candidate_id": "candidate-rotation-only",
        "program": {
            "version": "bot-logic-tree-v1",
            "loadout": {"abilities": [1]},
            "roots": [{"branches": [{
                "conditions": [{"type": "always"}],
                "actions": [{"action": "rotate_toward_enemy", "selectable": "opponent_1"}],
                "children": [],
            }]}],
        },
    }]}

    result = validate_candidate_response(payload, context())

    assert result[0].valid is False
    assert {issue.code for issue in result[0].issues} == {"ability_action_required"}


def test_rejects_selected_ability_condition_without_ability_metadata() -> None:
    payload = {"candidates": [{
        "candidate_id": "candidate-1",
        "program": {
            "version": "bot-logic-tree-v1",
            "loadout": {"abilities": [1]},
            "roots": [{"branches": [{
                "conditions": [{
                    "type": "expression",
                    "left": "bot.selectedAbilityReady",
                    "comparator": "eq",
                    "right": {"type": "boolean", "value": True},
                }],
                "actions": [{"action": 1, "selectable": "opponent_1"}],
                "children": [],
            }]}],
        },
    }]}

    result = validate_candidate_response(payload, context())

    assert result[0].valid is False
    assert {issue.code for issue in result[0].issues} == {"ability_required"}


def test_repairs_selected_ability_metadata_from_branch_action() -> None:
    payload = {"candidates": [{
        "candidate_id": "candidate-1",
        "program": {
            "version": "bot-logic-tree-v1",
            "loadout": {"abilities": [1]},
            "roots": [{"branches": [{
                "conditions": [{
                    "type": "expression",
                    "left": "bot.selectedAbilityReady",
                    "comparator": "eq",
                    "right": {"type": "boolean", "value": True},
                }],
                "actions": [{"action": 1, "selectable": "opponent_1"}],
                "children": [],
            }]}],
        },
    }]}

    normalized = normalize_candidate_response(
        payload,
        context(),
        repair_selected_metadata=True,
    )

    condition = normalized["candidates"][0]["program"]["roots"][0]["branches"][0]["conditions"][0]
    assert condition["ability"] == 1
    assert validate_candidate_response(normalized, context())[0].valid is True


def test_repairs_unsupported_target_metadata_on_selected_ability_condition() -> None:
    payload = {"candidates": [{
        "candidate_id": "candidate-1",
        "program": {
            "version": "bot-logic-tree-v1",
            "loadout": {"abilities": [1]},
            "roots": [{"branches": [{
                "conditions": [{
                    "type": "expression",
                    "left": "bot.selectedAbilityReady",
                    "comparator": "eq",
                    "right": {"type": "boolean", "value": True},
                    "ability": 1,
                    "targetMode": "target",
                }],
                "actions": [{"action": 1}],
                "children": [],
            }]}],
        },
    }]}

    normalized = normalize_candidate_response(
        payload,
        context(),
        repair_selected_metadata=True,
    )

    condition = normalized["candidates"][0]["program"]["roots"][0]["branches"][0]["conditions"][0]
    assert "targetMode" not in condition
    assert validate_candidate_response(normalized, context())[0].valid is True


def test_rejects_opponent_only_ability_action() -> None:
    payload = {"candidates": [{
        "candidate_id": "candidate-1",
        "program": {
            "version": "bot-logic-tree-v1",
            "loadout": {"abilities": [3]},
            "roots": [{"branches": [{
                "conditions": [],
                "actions": [{"action": 3}],
                "children": [],
            }]}],
        },
    }]}
    result = validate_candidate_response(payload, context())
    assert result[0].valid is False
    assert {issue.code for issue in result[0].issues} == {"unavailable_ability", "unavailable_action"}


def test_authoritative_issues_override_shallow_acceptance() -> None:
    prevalidation = validate_candidate_response({"candidates": [{
        "candidate_id": "candidate-1",
        "program": {"version": "bot-logic-tree-v1", "roots": []},
    }]}, context())
    merged = merge_authoritative_validation(prevalidation, {
        "results": [{"index": 0, "valid": False, "errors": ["brain.loadout is required"]}]
    })
    assert merged[0].valid is False
    assert merged[0].issues[-1].code == "authoritative_validation"


def test_normalizes_standard_abilities_from_program_loadout() -> None:
    payload = {"candidates": [{
        "candidate_id": "candidate-1",
        "program": {
            "version": "bot-logic-tree-v1",
            "loadout": {"abilities": [19, 1, 20, 34]},
            "roots": [],
        },
    }]}

    normalized = normalize_candidate_response(payload)

    assert normalized["candidates"][0]["program"]["loadout"]["abilities"] == [1]
    assert payload["candidates"][0]["program"]["loadout"]["abilities"] == [19, 1, 20, 34]


def test_normalizes_duplicate_nonstandard_loadout_abilities() -> None:
    payload = {"candidates": [{
        "candidate_id": "candidate-1",
        "program": {
            "version": "bot-logic-tree-v1",
            "loadout": {"abilities": [1, 1, 3, 1]},
            "roots": [],
        },
    }]}

    normalized = normalize_candidate_response(payload)

    assert normalized["candidates"][0]["program"]["loadout"]["abilities"] == [1, 3]
    assert payload["candidates"][0]["program"]["loadout"]["abilities"] == [1, 1, 3, 1]


def test_repairs_rotation_only_candidate_with_allowed_ability_action() -> None:
    payload = {"candidates": [{
        "candidate_id": "candidate-1",
        "program": {
            "version": "bot-logic-tree-v1",
            "loadout": {"abilities": [1]},
            "customVariables": [],
            "roots": [{"branches": [{
                "conditions": [{"type": "always"}],
                "actions": [{"action": "rotate_toward_enemy", "selectable": "opponent_1"}],
                "children": [],
            }]}],
        },
    }]}

    normalized = normalize_candidate_response(
        payload,
        context(),
        repair_selected_metadata=True,
    )

    actions = normalized["candidates"][0]["program"]["roots"][0]["branches"][0]["actions"]
    assert any(action["action"] == 1 for action in actions)
    assert validate_candidate_response(normalized, context())[0].valid is True


def test_repairs_unsupported_ability_action_metadata_and_boolean_operand() -> None:
    payload = {"candidates": [{
        "candidate_id": "candidate-1",
        "program": {
            "version": "bot-logic-tree-v1",
            "loadout": {"abilities": [1]},
            "customVariables": [],
            "roots": [{"branches": [{
                "conditions": [{
                    "type": "expression",
                    "left": "bot.selectedAbilityReady",
                    "comparator": "eq",
                    "right": {"type": "variable", "value": "bot.selectedAbilityReady"},
                }],
                "actions": [{
                    "action": 1,
                    "selectable": "opponent_1",
                    "targetMode": "coordinates",
                    "targetX": 100,
                    "targetY": 200,
                }],
                "children": [],
            }]}],
        },
    }]}

    normalized = normalize_candidate_response(
        payload,
        context(),
        repair_selected_metadata=True,
    )

    branch = normalized["candidates"][0]["program"]["roots"][0]["branches"][0]
    assert all(key not in branch["actions"][0] for key in ("targetMode", "targetX", "targetY"))
    assert branch["conditions"] == [{"type": "always"}]
    assert validate_candidate_response(normalized, context())[0].valid is True
