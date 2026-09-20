import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from .models import MatchContext


GAME_KNOWLEDGE_PATH = Path(__file__).parent / "data" / "duel-v1-game-knowledge.json"
CANDIDATE_SCHEMA_PATH = Path(__file__).parents[1] / "contracts" / "v1" / "candidate-response.schema.json"


@lru_cache(maxsize=1)
def load_game_knowledge() -> dict[str, Any]:
    with GAME_KNOWLEDGE_PATH.open(encoding="utf-8-sig") as source:
        payload = json.load(source)
    if payload.get("rulesetVersion") != "duel-v1":
        raise RuntimeError("game knowledge ruleset is not duel-v1")
    if payload.get("brainSchemaVersion") != "bot-logic-tree-v1":
        raise RuntimeError("game knowledge brain schema is not bot-logic-tree-v1")
    return payload


@lru_cache(maxsize=64)
def load_candidate_response_schema(
    candidate_count: int | None = None,
    allowed_ability_ids: tuple[int, ...] | None = None,
) -> dict[str, Any]:
    with CANDIDATE_SCHEMA_PATH.open(encoding="utf-8") as source:
        schema = json.load(source)
    if candidate_count is not None:
        schema = deepcopy(schema)
        schema["properties"]["candidates"]["minItems"] = candidate_count
        schema["properties"]["candidates"]["maxItems"] = candidate_count
    if allowed_ability_ids is not None:
        schema = deepcopy(schema)
        allowed = sorted({int(value) for value in allowed_ability_ids})
        standard = {int(value) for value in load_game_knowledge()["standardAbilities"]}
        selectable_loadout_ids = [value for value in allowed if value not in standard]
        loadout_abilities = schema["$defs"]["program"]["properties"]["loadout"]["properties"]["abilities"]
        if selectable_loadout_ids:
            loadout_abilities["items"]["enum"] = selectable_loadout_ids
        else:
            # The canonical duel always has standard abilities implicitly, so
            # an empty non-standard selection is represented by an empty list.
            loadout_abilities["maxItems"] = 0
        condition = schema["$defs"]["condition"]["oneOf"][1]
        condition["properties"]["ability"]["enum"] = allowed
        ability_action = schema["$defs"]["action"]["oneOf"][5]
        ability_action["properties"]["action"]["enum"] = allowed
        _add_authoritative_condition_type_rules(schema, condition)
        _add_authoritative_ability_action_rules(schema, ability_action, allowed)
    return schema


def _add_authoritative_condition_type_rules(
    schema: dict[str, Any], condition: dict[str, Any]
) -> None:
    """Encode the Java validator's built-in variable operand rules.

    The base response schema intentionally keeps ``left`` open because custom
    variables are declared by the candidate itself.  Canonical built-in
    boolean variables are known, however, and the Java validator accepts only
    a boolean literal on their right-hand side (not a number or variable
    operand).  Constrain those fields before Ollama generation so its grammar
    cannot repeatedly emit an authoritative rejection.
    """
    variables = load_game_knowledge()["botLogic"]["variables"]
    boolean_variables = sorted(
        variable_id
        for variable_id, variable in variables.items()
        if isinstance(variable, dict) and str(variable.get("valueType", "")).upper() == "BOOLEAN"
    )
    if not boolean_variables:
        return
    condition.setdefault("allOf", []).append({
        "if": {
            "required": ["left"],
            "properties": {"left": {"enum": boolean_variables}},
        },
        "then": {
            "properties": {
                "right": {
                    "type": "object",
                    "required": ["type", "value"],
                    "properties": {
                        "type": {"const": "boolean"},
                        "value": {"type": "boolean"},
                    },
                },
            },
        },
    })


def _add_authoritative_ability_action_rules(
    schema: dict[str, Any], ability_action: dict[str, Any], allowed: list[int]
) -> None:
    """Constrain integer action configuration to each canonical ability.

    Most abilities do not have a target mode at all.  The static schema has to
    keep the union of possible fields, but its per-ability conditions can
    forbid unsupported target/movement metadata while retaining coordinate,
    movement, and orientation fields only where the exported action contract
    permits them.
    """
    contracts = load_game_knowledge()["botLogic"].get("actionContracts", {})
    rules: list[dict[str, Any]] = []
    target_fields = ["targetMode", "targetX", "targetY", "targetAngle"]
    movement_fields = ["movementMode", "movementDirection", "targetOffsetX", "targetOffsetY"]
    for ability_id in allowed:
        contract = contracts.get(str(ability_id))
        if not isinstance(contract, dict):
            continue
        coordinate_target = bool(contract.get("coordinateTarget"))
        movement_config = bool(contract.get("movementConfig"))
        target_mode = contract.get("targetMode")
        orientation_config = bool(contract.get("orientationConfig"))
        forbidden: list[str] = []
        if not coordinate_target and not movement_config:
            if target_mode is None:
                forbidden.extend(target_fields)
            else:
                # Target-only abilities may carry their one canonical mode,
                # but never coordinate/angle payload fields.
                forbidden.extend(["targetX", "targetY", "targetAngle"])
            forbidden.extend(movement_fields)
        elif movement_config:
            # Movement abilities use movementMode; targetMode is not consumed
            # by the authoritative action validator for this action head.
            forbidden.append("targetMode")
            forbidden.append("targetAngle")
            if not coordinate_target:
                forbidden.extend(["targetX", "targetY", "targetAngle"])
        elif coordinate_target:
            # Location-target abilities support target/coordinates.  The
            # exported targetMode is the default, not the only legal mode.
            if target_mode is not None:
                forbidden.append("targetAngle")
        if not orientation_config:
            forbidden.append("phaseFacingMode")
        if forbidden:
            rules.append({
                "if": {
                    "required": ["action"],
                    "properties": {"action": {"const": ability_id}},
                },
                "then": {
                    "not": {"anyOf": [{"required": [field]} for field in sorted(set(forbidden))]},
                },
            })
        if coordinate_target and not movement_config:
            rules.append({
                "if": {
                    "required": ["action", "targetMode"],
                    "properties": {
                        "action": {"const": ability_id},
                        "targetMode": {"const": "coordinates"},
                    },
                },
                "then": {"required": ["targetX", "targetY"]},
            })
        elif target_mode is not None and not movement_config:
            rules.append({
                "if": {
                    "required": ["action", "targetMode"],
                    "properties": {"action": {"const": ability_id}},
                },
                "then": {"properties": {"targetMode": {"const": target_mode}}},
            })
    ability_action.setdefault("allOf", []).extend(rules)


def _pick(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Keep only non-null fields that are useful to the program generator."""
    return {field: source[field] for field in fields if field in source and source[field] is not None}


def _compact_ability_definition(definition: dict[str, Any]) -> dict[str, Any]:
    return _pick(
        definition,
        (
            "cooldownMs",
            "windupMs",
            "activeMs",
            "durationMs",
            "damage",
            "healing",
            "range",
            "arc",
            "charges",
            "rechargeMs",
            "reuseCooldownMs",
            "resourceModel",
            "falloffMode",
            "falloff",
            "damageOverTime",
            "stats",
        ),
    )


def _compact_phase(phase: dict[str, Any]) -> dict[str, Any]:
    result = _pick(
        phase,
        ("id", "type", "trigger", "durationMs", "startMs", "transitionOnly", "skipOwner"),
    )
    if isinstance(phase.get("movement"), dict):
        result["movement"] = _pick(
            phase["movement"],
            ("speed", "turnDegrees", "size", "distance", "trailMs", "blockedByStatus"),
        )
    if isinstance(phase.get("hitbox"), dict):
        result["hitbox"] = _pick(
            phase["hitbox"],
            ("shape", "radius", "range", "arc", "radiusMultiplier", "width", "length", "includeTargetRadius"),
        )
    effects = phase.get("effects")
    if isinstance(effects, list):
        result["effects"] = [
            _pick(
                effect,
                (
                    "type",
                    "subtype",
                    "amount",
                    "durationMs",
                    "recipient",
                    "requiresConfirmedDamage",
                    "mirrorsDamage",
                    "distanceMode",
                    "intervalMs",
                    "movementLockMs",
                    "falloff",
                ),
            )
            for effect in effects
            if isinstance(effect, dict)
        ]
    events = phase.get("events")
    if isinstance(events, dict):
        compact_events: dict[str, Any] = {}
        for event_name, event in events.items():
            if not isinstance(event, dict):
                continue
            compact_event = _pick(event, ("actions", "effectTypes", "targetKinds", "transition"))
            if isinstance(event.get("schedule"), dict):
                compact_event["schedule"] = _pick(
                    event["schedule"],
                    ("mode", "intervalMs", "startImmediately", "count"),
                )
            compact_events[event_name] = compact_event
        if compact_events:
            result["events"] = compact_events
    return result


def _compact_ability_contract(contract: dict[str, Any]) -> dict[str, Any]:
    result = _pick(
        contract,
        ("abilityId", "entityType", "runtimeType", "category", "selectableOwner"),
    )
    activation = contract.get("activation")
    if isinstance(activation, dict):
        result["activation"] = _pick(
            activation,
            (
                "targetMode",
                "captureAtActivation",
                "phaseFacingDefault",
                "ignoresGlobalAbilityLock",
                "teleportOncePerActivation",
            ),
        )
    phases = contract.get("phases")
    if isinstance(phases, list):
        result["phases"] = [_compact_phase(phase) for phase in phases if isinstance(phase, dict)]
    return result


def _format_number(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    return f"{value:g}"


def _ability_effect_summary(contract: dict[str, Any]) -> list[str]:
    """Turn canonical effect records into short mechanical descriptions."""
    summaries: list[str] = []
    seen: set[str] = set()
    for phase in contract.get("phases", []):
        if not isinstance(phase, dict):
            continue
        for effect in phase.get("effects", []):
            if not isinstance(effect, dict):
                continue
            effect_type = str(effect.get("type", "")).lower().replace("_", " ")
            subtype = effect.get("subtype")
            label = f"{effect_type} ({subtype})" if subtype else effect_type
            amount = _format_number(effect.get("amount"))
            if amount and effect.get("type") in {"DAMAGE", "HEALING"}:
                label += f" {amount}"
            falloff = effect.get("falloff")
            if isinstance(falloff, dict):
                label += " with distance falloff"
            duration = _format_number(effect.get("durationMs"))
            if duration and duration != "0":
                label += f" for {duration}ms"
            interval = _format_number(effect.get("intervalMs"))
            if interval:
                label += f" every {interval}ms"
            if label and label not in seen:
                summaries.append(label)
                seen.add(label)
    return summaries


def _ability_hitbox_summary(contract: dict[str, Any]) -> tuple[list[str], bool]:
    shapes: list[str] = []
    facing_sensitive = False
    for phase in contract.get("phases", []):
        if not isinstance(phase, dict):
            continue
        hitbox = phase.get("hitbox")
        if isinstance(hitbox, dict):
            shape = str(hitbox.get("shape", "")).lower()
            if shape and shape not in shapes:
                shapes.append(shape)
            if shape in {"arc", "ray", "rectangle"}:
                facing_sensitive = True
    return shapes, facing_sensitive


def _ability_rules_summary(
    ability_id: int,
    definition: dict[str, Any],
    contract: dict[str, Any],
    action_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    """Project canonical ability data into concise mechanical language.

    The Java-exported contract remains authoritative. This is only a compact
    interpretation layer for prompting; it does not implement ability rules
    or recommend when an ability should be used.
    """
    effects = _ability_effect_summary(contract)
    effect_types = {
        str(effect.get("type", "")).upper()
        for phase in contract.get("phases", [])
        if isinstance(phase, dict)
        for effect in phase.get("effects", [])
        if isinstance(effect, dict)
    }
    effect_subtypes = {
        str(effect.get("subtype", "")).upper()
        for phase in contract.get("phases", [])
        if isinstance(phase, dict)
        for effect in phase.get("effects", [])
        if isinstance(effect, dict) and effect.get("subtype")
    }
    shapes, facing_sensitive = _ability_hitbox_summary(contract)
    phases = [phase for phase in contract.get("phases", []) if isinstance(phase, dict)]
    target_mode = (contract.get("activation") or {}).get("targetMode")
    orientation = any(isinstance(phase.get("orientation"), dict) for phase in phases)
    action_config = (action_contract or {}).get("configuration") or {}
    supports_movement_config = bool((action_contract or {}).get("movementConfig"))

    effect_categories: list[str] = []
    if "DAMAGE" in effect_types:
        effect_categories.append("damage")
    if "HEALING" in effect_types:
        effect_categories.append("healing")
    if "STATUS" in effect_types or {"STUN", "SILENCE", "SLOW", "BLEED", "BURN", "SHOCK"} & effect_subtypes:
        effect_categories.append("status")
    if {"KNOCKBACK", "PULL", "INTERRUPT"} & effect_types:
        effect_categories.append("displacement")
    if {"DAMAGE_REDUCTION", "DAMAGE_REFLECTION", "DAMAGE_IMMUNITY", "RESTORE_STATE"} & effect_types:
        effect_categories.append("damage_mitigation")
    if "BUFF" in effect_types:
        effect_categories.append("buff")
    if "TELEPORT" in effect_types:
        effect_categories.append("teleport")
    if supports_movement_config:
        effect_categories.append("movement")
    if orientation or ability_id == 20:
        effect_categories.append("orientation")
    if not effect_categories:
        effect_categories.append("utility")

    if ability_id == 19 or supports_movement_config:
        delivery = "movement ability"
    elif ability_id == 20 or target_mode == "target" or orientation:
        delivery = "target/orientation utility"
    elif "ray" in shapes or "arc" in shapes:
        delivery = "facing-dependent line/arc hitbox"
    elif "circle" in shapes:
        delivery = "area hitbox"
    elif "PROJECTILE" == contract.get("category"):
        delivery = "projectile"
    elif "HEALING" in effect_types or "DAMAGE_REDUCTION" in effect_types or "DAMAGE_IMMUNITY" in effect_types:
        delivery = "self-targeted effect"
    else:
        delivery = "ability effect"

    reach = definition.get("range")
    if not isinstance(reach, (int, float)) or isinstance(reach, bool) or reach <= 0:
        reach_values = [
            hitbox.get("range") or hitbox.get("length") or hitbox.get("radius")
            for phase in phases
            if isinstance(phase.get("hitbox"), dict)
            for hitbox in [phase["hitbox"]]
        ]
        numeric_reach = [value for value in reach_values if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0]
        reach = max(numeric_reach) if numeric_reach else None
    stats: dict[str, Any] = {}
    for source, target in (
        ("cooldownMs", "cooldown_ms"),
        ("windupMs", "windup_ms"),
        ("activeMs", "active_ms"),
        ("durationMs", "duration_ms"),
        ("charges", "charges"),
        ("rechargeMs", "recharge_ms"),
    ):
        value = definition.get(source)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value <= 0:
            # Zero is the registry default for fields that do not apply. In
            # particular, exposing charges=0 can make a model think an
            # otherwise usable ability has no charges.
            continue
        if value is not None:
            stats[target] = value
    if reach is not None:
        stats["reach"] = reach

    result: dict[str, Any] = {
        "effect_categories": list(dict.fromkeys(effect_categories)),
        "delivery": delivery,
        "effects": effects,
        "stats": stats,
    }
    if shapes:
        result["hitbox_shapes"] = shapes
    if facing_sensitive:
        result["facing_matters"] = True
    if target_mode:
        result["activation_target_mode"] = target_mode
    if supports_movement_config:
        result["movement_fields"] = {
            "modes": action_config.get("movementModes", []),
            "directions": action_config.get("absoluteDirections", []),
        }
    return result


def _compact_variable_contract(variable: dict[str, Any]) -> dict[str, Any]:
    """Project one canonical variable contract without repeating defaults.

    The variable ID is the mapping key.  Most contracts share the same
    defaults (selectable support, ordering, angle range, etc.), so compact
    mode emits only meaningful overrides.  ``variable_contract_defaults`` in
    the returned logic block documents those omitted values.
    """
    result: dict[str, Any] = {
        "valueType": variable.get("valueType"),
    }
    for key in (
        "requiresAbility",
        "requiresStatusEffect",
        "pairVariable",
        "angle",
        "circularAngle",
        "boundedRelativeBearing",
        "allowsNegativeInteger",
        "durationSeconds",
    ):
        if variable.get(key) is True:
            result[key] = True
    for key in ("selectableType", "selectableDependency", "targetModes"):
        value = variable.get(key)
        if value:
            result[key] = value
    maximum = variable.get("relativeBearingMaximum")
    if maximum is not None and maximum != 360.0:
        result["relativeBearingMaximum"] = maximum
    return result


def _compact_logic(
    logic: dict[str, Any],
    action_ability_ids: set[int],
    selectable_ability_ids: set[int],
) -> dict[str, Any]:
    variables = logic.get("variableContracts") or logic.get("variables")
    compact_variables: dict[str, Any] = {}
    if isinstance(variables, dict):
        for variable_id, variable in variables.items():
            if isinstance(variable, dict):
                compact_variables[variable_id] = _compact_variable_contract(variable)
                source = variable.get("source")
                if isinstance(source, str) and source.startswith("SELECTED_ABILITY_"):
                    compact_variables[variable_id]["requiresAbility"] = True
                if isinstance(source, str) and source.startswith("SELECTED_STATUS_EFFECT_"):
                    compact_variables[variable_id]["requiresStatusEffect"] = True
    action_ids = set(action_ability_ids)
    selectable_ids_for_entities = set(selectable_ability_ids)
    selectable_ids: list[str] = []
    for selectable_id, selectable in logic["selectables"].items():
        if selectable_id in {"my_bot", "opponent_1"}:
            selectable_ids.append(selectable_id)
            continue
        if not isinstance(selectable, dict):
            continue
        if (
            selectable_id.startswith(("my_bot_", "opponent_1_"))
            and selectable.get("abilityId") in selectable_ids_for_entities
        ):
            selectable_ids.append(selectable_id)
    action_contracts = logic.get("actionContracts") or {}
    compact_action_contracts: dict[str, Any] = {}
    action_configuration_templates: dict[str, Any] = {}
    compact_ability_action_contracts: dict[str, Any] = {}

    def add_action_contract(key: str, contract: Any) -> None:
        if not isinstance(contract, dict):
            return
        compact_action_contracts[key] = _pick(
            contract,
            (
                "action", "head", "variableAction", "movementConfig", "coordinateTarget",
                "locationTarget", "orientationConfig", "angleTarget", "targetMode", "usesTarget",
            ),
        )
        head = contract.get("head")
        configuration = contract.get("configuration")
        if isinstance(head, str) and isinstance(configuration, dict):
            action_configuration_templates.setdefault(head, {
                key: configuration[key]
                for key in (
                    "requiredFields", "optionalFields", "movementModes", "targetModes",
                    "absoluteDirections", "operations", "operandTypes", "angleRange",
                )
                if key in configuration
            })

    for action_id in logic.get("commonActions", []):
        add_action_contract(str(action_id), action_contracts.get(str(action_id)))

    # All integer ability actions share the same output shape. Keep one
    # ability template for shared fields, but preserve each ability's
    # authoritative targeting/movement restrictions separately. The exported
    # Java registry intentionally carries a broad union of optional fields;
    # exposing that union as if every ability supported it causes models to
    # emit targetMode on targetless abilities.
    ability_contract = next(
        (
            action_contracts.get(str(ability_id))
            for ability_id in sorted(action_ability_ids)
            if isinstance(action_contracts.get(str(ability_id)), dict)
        ),
        None,
    )
    add_action_contract("ability", ability_contract)
    action_configuration_templates["ABILITY"] = {
        "requiredFields": ["action"],
        "optionalFields": ["selectable"],
        "note": "Use ability_action_contracts[action] for ability-specific fields.",
    }
    for ability_id in sorted(action_ability_ids):
        contract = action_contracts.get(str(ability_id))
        if not isinstance(contract, dict):
            continue
        movement_config = bool(contract.get("movementConfig"))
        coordinate_target = bool(contract.get("coordinateTarget"))
        location_target = bool(contract.get("locationTarget"))
        orientation_config = bool(contract.get("orientationConfig"))
        target_mode = contract.get("targetMode")
        allowed_fields = ["action"]
        if contract.get("usesTarget") or movement_config or location_target:
            allowed_fields.append("selectable")
        if movement_config:
            allowed_fields.extend(["movementMode", "movementDirection", "targetOffsetX", "targetOffsetY"])
            if coordinate_target:
                allowed_fields.extend(["targetX", "targetY"])
        elif coordinate_target:
            allowed_fields.extend(["targetMode", "targetX", "targetY"])
        elif target_mode is not None:
            allowed_fields.append("targetMode")
        if orientation_config:
            allowed_fields.append("phaseFacingMode")
        summary = _pick(
            contract,
            (
                "action", "head", "variableAction", "movementConfig", "coordinateTarget",
                "locationTarget", "orientationConfig", "angleTarget", "targetMode", "usesTarget",
            ),
        )
        summary["allowedFields"] = allowed_fields
        if coordinate_target and not movement_config:
            summary["targetModes"] = ["target", "coordinates"]
        elif target_mode is not None:
            summary["targetModes"] = [target_mode]
        compact_ability_action_contracts[str(ability_id)] = summary
    selectable_contracts = logic.get("selectables") or {}
    compact_selectable_contracts: dict[str, Any] = {}
    if isinstance(selectable_contracts, dict):
        for selectable_id in selectable_ids:
            contract = selectable_contracts.get(selectable_id)
            if isinstance(contract, dict):
                compact_selectable_contracts[selectable_id] = _pick(
                    contract,
                    ("id", "owner", "entityType", "runtimeType", "abilityId", "selectableIdentities"),
                )
    return {
        "common_actions": logic["commonActions"],
        "ability_actions": sorted(action_ids),
        "action_contracts": compact_action_contracts,
        "ability_action_contracts": compact_ability_action_contracts,
        "action_configuration_templates": action_configuration_templates,
        "action_configuration_note": "Each action contract uses the configuration template keyed by its head.",
        "ability_action_note": "An integer action is an ability ID. Use the ABILITY template; only add target or movement fields when the ability summary or contract calls for them.",
        "selectable_ids": sorted(selectable_ids),
        "selectable_contracts": compact_selectable_contracts,
        "variable_contract_defaults": {
            "scope": "SELECTABLE",
            "supportsSelectable": True,
            "pairVariable": False,
            "requiresAbility": False,
            "requiresStatusEffect": False,
            "selectableOrderable": True,
            "angle": False,
            "circularAngle": False,
            "boundedRelativeBearing": False,
            "relativeBearingMaximum": 360.0,
            "allowsNegativeInteger": False,
            "nonNegativeTime": False,
            "durationSeconds": False,
            "tenthSecondStep": False,
        },
        "variables": compact_variables,
        "status_effects": logic["statusEffects"],
        "selectable_orders": logic["selectableOrders"],
        "movement_modes": logic["movementModes"],
        "absolute_directions": logic["absoluteDirections"],
        "numeric_comparators": logic["numericComparators"],
        "boolean_comparators": logic["booleanComparators"],
        "condition_types": logic["conditionTypes"],
        "condition_joins": logic["conditionJoins"],
        "custom_variable_operations": logic["customVariableOperations"],
    }


def build_model_context(context: MatchContext, prompt_mode: str = "compact") -> dict[str, Any]:
    """Build a prompt snapshot from canonical exported registries.

    Compact mode keeps the exact decision-relevant contract while omitting
    verbose visual/entity metadata. Full mode remains available for debugging
    and contract audits.
    """
    if prompt_mode not in {"compact", "full"}:
        raise ValueError("prompt_mode must be 'compact' or 'full'")
    knowledge = load_game_knowledge()
    standard = {int(value) for value in knowledge["standardAbilities"]}
    selected = set(context.self.selected_abilities)
    known_opponent = set(context.opponent.known_abilities)
    relevant = sorted(standard | selected | known_opponent)

    names = knowledge["abilityNames"]
    definitions = knowledge["abilityDefinitions"]
    contracts = knowledge["abilityContracts"]
    logic = knowledge["botLogic"]
    unknown = [ability_id for ability_id in relevant if str(ability_id) not in names]
    if unknown:
        raise ValueError(f"match context contains unknown ability IDs: {unknown}")
    abilities: list[dict[str, Any]] = []
    for ability_id in relevant:
        key = str(ability_id)
        if key not in definitions or key not in contracts:
            continue
        ability = {
            "id": ability_id,
            "name": names.get(key),
            "available_to_self": ability_id in standard or ability_id in selected,
            "known_on_opponent": ability_id in known_opponent,
        }
        if prompt_mode == "compact":
            ability["ability_rules"] = _ability_rules_summary(
                ability_id,
                definitions[key],
                contracts[key],
                (logic.get("actionContracts") or {}).get(key),
            )
        else:
            ability["definition"] = definitions[key]
            ability["behavior"] = contracts[key]
        abilities.append(ability)

    context_payload = {
        "versions": {
            "context": context.schema_version,
            "ruleset": knowledge["rulesetVersion"],
            "brain_schema": knowledge["brainSchemaVersion"],
            "validator": knowledge["validatorVersion"],
            "game_knowledge": knowledge["contractVersion"],
            "game_source": knowledge["source"],
        },
        "arena": {
            **knowledge["arena"],
            "coordinate_system": {
                "x_increases": "east",
                "y_increases": "south",
                "compass_degrees": {"north": 0, "east": 90, "south": 180, "west": 270},
            },
            "duel_spawn_convention": {
                "team_1": {"y": knowledge["arena"]["spawnEdgeMargin"], "facing_degrees": 180},
                "team_2": {"y": knowledge["arena"]["height"] - knowledge["arena"]["spawnEdgeMargin"], "facing_degrees": 0},
            },
        },
        "game_config": knowledge["gameConfig"],
        "closing_zone": knowledge["closingZone"],
        "limits": knowledge["limits"],
        "available_self_ability_ids": sorted(standard | selected),
        "abilities": abilities,
        "logic": _compact_logic(logic, standard | selected, standard | selected | known_opponent)
        if prompt_mode == "compact" else {
            "common_actions": logic["commonActions"],
            "action_contracts": logic.get("actionContracts", {}),
            "selectable_ids": list(logic["selectables"].keys()),
            "selectable_contracts": logic["selectables"],
            "variables": logic["variables"],
            "variable_contracts": logic.get("variableContracts", logic["variables"]),
            "status_effects": logic["statusEffects"],
            "selectable_orders": logic["selectableOrders"],
            "movement_modes": logic["movementModes"],
            "absolute_directions": logic["absoluteDirections"],
            "numeric_comparators": logic["numericComparators"],
            "boolean_comparators": logic["booleanComparators"],
            "condition_types": logic["conditionTypes"],
            "condition_joins": logic["conditionJoins"],
            "custom_variable_operations": logic["customVariableOperations"],
        },
        "match": context.model_dump(mode="json"),
    }
    if prompt_mode == "compact":
        context_payload["prompt_mode"] = "compact"
    return context_payload
