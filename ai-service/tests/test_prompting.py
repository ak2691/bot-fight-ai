import json

from app.game_contracts import load_candidate_response_schema
from app.models import MatchContext
from app.prompting import (
    GAME_RULES,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
)


def test_user_prompt_contains_context_and_candidate_count() -> None:
    prompt = build_user_prompt(
        context=MatchContext.model_validate({
            "schema_version": "bot-fight-ai-match-context-v1",
            "ruleset_version": "duel-v1",
            "brain_schema_version": "bot-logic-tree-v1",
            "match_id": "test-match",
            "round_number": 1,
            "seed": 42,
            "self": {"selected_abilities": [1, 3]},
            "opponent": {"known_abilities": [5], "observations": []},
            "previous_round_telemetry": [],
        }),
        candidate_count=3,
        instructions="Return distinct programs with different legal condition and action structures.",
    )

    payload = json.loads(prompt)
    assert PROMPT_VERSION == "bot-fight-candidate-generation-v22-rules-contracts"
    assert payload["candidate_count"] == 3
    assert "BOT FIGHT PROGRAMMING RULES" in payload["game_rules"]
    assert "Direction" in payload["game_rules"]
    assert "180" in payload["game_rules"]
    assert "kiting" not in prompt.lower()
    assert "strategy_patterns" not in prompt
    assert "valid_program_example" not in prompt
    assert "strategy" not in GAME_RULES.lower()
    assert "tactic" not in GAME_RULES.lower()
    assert "strategy" not in SYSTEM_PROMPT.lower()
    assert "tactic" not in SYSTEM_PROMPT.lower()
    assert payload["game_and_match_context"]["match"]["round_number"] == 1
    assert payload["game_and_match_context"]["available_self_ability_ids"] == [1, 3, 19, 20, 34]
    assert {ability["id"] for ability in payload["game_and_match_context"]["abilities"]} == {1, 3, 5, 19, 20, 34}
    basic_strike = next(ability for ability in payload["game_and_match_context"]["abilities"] if ability["id"] == 34)
    assert "facing-dependent" in basic_strike["ability_rules"]["delivery"]
    assert basic_strike["ability_rules"]["facing_matters"] is True
    dash = next(ability for ability in payload["game_and_match_context"]["abilities"] if ability["id"] == 19)
    assert dash["ability_rules"]["delivery"] == "movement ability"
    fireball = next(ability for ability in payload["game_and_match_context"]["abilities"] if ability["id"] == 5)
    assert fireball["ability_rules"]["delivery"] == "projectile"
    assert any("19, 20, 34" in note for note in payload["output_contract"]["notes"])
    assert payload["additional_instructions"] == "Return distinct programs with different legal condition and action structures."


def test_prompt_states_program_rules_and_ability_requirement() -> None:
    context = MatchContext.model_validate({
        "schema_version": "bot-fight-ai-match-context-v1",
        "ruleset_version": "duel-v1",
        "brain_schema_version": "bot-logic-tree-v1",
        "match_id": "test-match",
        "round_number": 1,
        "seed": 42,
        "self": {"selected_abilities": [1]},
        "opponent": {"known_abilities": [3], "observations": []},
        "previous_round_telemetry": [],
    })

    payload = json.loads(build_user_prompt(context, 1, None))

    assert "opponent_1" in payload["task"]
    notes = payload["output_contract"]["notes"]
    assert any("walk-only" in note for note in notes)
    assert any("ability_rules" in note for note in notes)
    assert any("target-relative movement" in note for note in notes)
    assert "logic_contract_examples" not in payload["output_contract"]
    assert "action_examples" not in payload["output_contract"]
    assert "condition_examples" not in payload["output_contract"]
    variables = payload["game_and_match_context"]["logic"]["variables"]
    assert variables["bot.selectedAbilityReady"]["requiresAbility"] is True
    logic = payload["game_and_match_context"]["logic"]
    assert "ABILITY" in logic["action_configuration_templates"]
    assert logic["action_configuration_templates"]["ABILITY"]["optionalFields"] == ["selectable"]
    assert logic["ability_action_contracts"]["1"]["allowedFields"] == ["action"]
    assert "targetMode" in logic["ability_action_contracts"]["20"]["allowedFields"]
    assert logic["variable_contract_defaults"]["relativeBearingMaximum"] == 360.0


def test_response_schema_requires_requested_candidate_count() -> None:
    schema = load_candidate_response_schema(3)
    candidates = schema["properties"]["candidates"]
    assert candidates["minItems"] == 3
    assert candidates["maxItems"] == 3
    assert "strategy_note" not in candidates["items"]["properties"]
    condition = schema["$defs"]["condition"]["oneOf"][1]
    assert "ability" in condition["required"]


def test_response_schema_limits_ability_ids_to_match_context() -> None:
    schema = load_candidate_response_schema(1, (1, 3, 19, 20, 34))
    condition = schema["$defs"]["condition"]["oneOf"][1]
    ability_action = schema["$defs"]["action"]["oneOf"][5]
    loadout = schema["$defs"]["program"]["properties"]["loadout"]["properties"]["abilities"]
    assert condition["properties"]["ability"]["enum"] == [1, 3, 19, 20, 34]
    assert ability_action["properties"]["action"]["enum"] == [1, 3, 19, 20, 34]
    assert loadout["items"]["enum"] == [1, 3]


def test_response_schema_encodes_configuration_requirements() -> None:
    schema = load_candidate_response_schema(1, (1, 3, 19, 20, 34))
    custom = schema["$defs"]["customVariable"]
    operand = schema["$defs"]["operand"]
    condition = schema["$defs"]["condition"]["oneOf"][1]
    actions = schema["$defs"]["action"]["oneOf"]
    rotate = actions[3]
    ability = actions[5]

    assert custom["required"] == ["id", "name", "valueType", "initialValue"]
    assert operand["required"] == ["type", "value"]
    assert condition["required"] == ["type", "left", "comparator", "right", "ability"]
    assert actions[0]["required"] == ["action", "selectable", "movementMode"]
    assert actions[1]["required"] == ["action", "movementMode", "targetX", "targetY"]
    assert actions[2]["required"] == ["action", "movementMode", "movementDirection"]
    assert rotate["required"] == ["action", "selectable"]
    assert ability["required"] == ["action"]
    assert any(
        item.get("then", {}).get("required") == ["targetX", "targetY"]
        for item in rotate["allOf"]
    )
    assert any(
        item.get("then", {}).get("required") == ["targetAngle"]
        for item in ability["allOf"]
    )
    assert condition["properties"]["statusEffect"]["enum"] == [
        "stun", "bleed", "slow", "shock", "overclock", "burn", "silence"
    ]
    assert any(
        "bot.selectedStatusEffectActive" in item.get("if", {}).get("properties", {}).get("left", {}).get("enum", [])
        for item in condition["allOf"]
    )


def test_request_schema_encodes_authoritative_action_and_operand_restrictions() -> None:
    schema = load_candidate_response_schema(1, (1, 3, 19, 20, 34))
    condition = schema["$defs"]["condition"]["oneOf"][1]
    boolean_rule = next(
        item for item in condition["allOf"]
        if "bot.selectedAbilityReady" in item.get("if", {}).get("properties", {}).get("left", {}).get("enum", [])
    )
    assert boolean_rule["then"]["properties"]["right"]["properties"]["type"] == {"const": "boolean"}

    ability = schema["$defs"]["action"]["oneOf"][5]
    targetless_rule = next(
        item for item in ability["allOf"]
        if item.get("if", {}).get("properties", {}).get("action", {}).get("const") == 1
    )
    forbidden = targetless_rule["then"]["not"]["anyOf"]
    assert {field for item in forbidden for field in item["required"]} >= {"targetMode", "targetX", "targetY"}


def test_compact_prompt_keeps_relevant_contract_without_full_entity_registry() -> None:
    context = MatchContext.model_validate({
        "schema_version": "bot-fight-ai-match-context-v1",
        "ruleset_version": "duel-v1",
        "brain_schema_version": "bot-logic-tree-v1",
        "match_id": "test-match",
        "round_number": 1,
        "seed": 42,
        "self": {"selected_abilities": [1, 3]},
        "opponent": {"known_abilities": [5], "observations": []},
        "previous_round_telemetry": [],
    })

    compact = build_user_prompt(context, 1, None, prompt_mode="compact")
    full = build_user_prompt(context, 1, None, prompt_mode="full")
    compact_payload = json.loads(compact)

    assert len(compact) < len(full)
    assert compact_payload["game_and_match_context"]["prompt_mode"] == "compact"
    assert compact_payload["game_and_match_context"]["logic"]["ability_actions"] == [1, 3, 19, 20, 34]


def test_compact_context_retains_all_contract_types_within_local_context_budget() -> None:
    context = MatchContext.model_validate({
        "schema_version": "bot-fight-ai-match-context-v1",
        "ruleset_version": "duel-v1",
        "brain_schema_version": "bot-logic-tree-v1",
        "match_id": "round-three",
        "round_number": 3,
        "seed": 42,
        "self": {"selected_abilities": [12, 5, 26, 8, 15, 33]},
        "opponent": {"known_abilities": [12, 5, 26, 8, 15, 33], "observations": []},
        "previous_round_telemetry": [],
    })

    prompt = build_user_prompt(context, 1, None, prompt_mode="compact")
    payload = json.loads(prompt)
    logic = payload["game_and_match_context"]["logic"]

    # The default local Ollama context is 16k tokens.  This generous character
    # guard catches accidental re-expansion of the compact canonical metadata.
    assert len(prompt) < 60_000
    assert len(logic["variables"]) >= 30
    assert set(logic["action_configuration_templates"]) >= {"NONE", "VARIABLE", "MOVEMENT", "ROTATION", "ABILITY"}
    assert logic["action_contracts"]["move_walk"]["head"] == "MOVEMENT"
    assert logic["variables"]["bot.selectedAbilityReady"]["requiresAbility"] is True
