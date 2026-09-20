from copy import deepcopy
from typing import Any

from .game_contracts import load_game_knowledge
from .models import CandidateValidation, MatchContext, ValidationIssue


def normalize_candidate_response(
    payload: Any,
    context: MatchContext | None = None,
    *,
    repair_selected_metadata: bool = False,
) -> Any:
    """Normalize the client program shape before canonical validation.

    Standard abilities are always available in a duel and are therefore
    implicit in ``program.loadout``. The client/server submission contract
    permits only additional equipped abilities in that list. Models often
    repeat the standard IDs, so remove only those known canonical IDs while
    leaving all other malformed values for validation to reject.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        return payload

    normalized = deepcopy(payload)
    standard = {int(value) for value in load_game_knowledge()["standardAbilities"]}
    available = standard | (
        set(context.self.selected_abilities) if context is not None else set()
    )
    for candidate in normalized["candidates"]:
        if not isinstance(candidate, dict):
            continue
        program = candidate.get("program")
        if not isinstance(program, dict):
            continue
        loadout = program.get("loadout")
        if not isinstance(loadout, dict) or not isinstance(loadout.get("abilities"), list):
            continue
        # Ollama's grammar follows the array shape but does not reliably
        # enforce JSON Schema ``uniqueItems``.  Duplicate loadout entries have
        # no gameplay meaning and are rejected by the canonical validator, so
        # preserve the first occurrence while retaining every non-integer or
        # unknown value for authoritative validation to reject.
        seen_abilities: set[int] = set()
        normalized_abilities = []
        for ability_id in loadout["abilities"]:
            if type(ability_id) is int and ability_id in standard:
                continue
            if type(ability_id) is int:
                if ability_id in seen_abilities:
                    continue
                seen_abilities.add(ability_id)
            normalized_abilities.append(ability_id)
        loadout["abilities"] = normalized_abilities
        if repair_selected_metadata and available:
            _repair_action_metadata(program)
            _repair_missing_ability_action(program, available)
            _repair_selected_condition_metadata(program, available)
            _repair_condition_operand_types(program)
    return normalized


def _walk_branches(branches: Any):
    """Yield branch dictionaries in deterministic depth-first order."""
    if not isinstance(branches, list):
        return
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        yield branch
        yield from _walk_branches(branch.get("children"))


def _repair_action_metadata(program: dict[str, Any]) -> None:
    """Remove configuration fields unsupported by each canonical action.

    The response schema has to describe a union of integer ability actions, so
    Ollama can still attach ``targetMode`` to an ability whose Java action
    contract is targetless.  The exported action registry is authoritative;
    strip only fields that that registry says the action cannot consume before
    invoking the Java validator.
    """
    contracts = load_game_knowledge()["botLogic"].get("actionContracts", {})
    roots = program.get("roots")
    if not isinstance(roots, list):
        return
    for root in roots:
        if not isinstance(root, dict):
            continue
        for branch in _walk_branches(root.get("branches")):
            actions = branch.get("actions")
            if not isinstance(actions, list):
                continue
            for action in actions:
                if not isinstance(action, dict) or type(action.get("action")) is not int:
                    continue
                contract = contracts.get(str(action["action"]))
                if not isinstance(contract, dict):
                    continue
                movement_config = bool(contract.get("movementConfig"))
                coordinate_target = bool(contract.get("coordinateTarget"))
                target_mode = contract.get("targetMode")
                orientation_config = bool(contract.get("orientationConfig"))
                if movement_config:
                    # Movement abilities use movementMode; targetMode is not
                    # consumed by the Java action validator for this head.
                    action.pop("targetMode", None)
                    action.pop("targetAngle", None)
                    if not coordinate_target:
                        for key in ("targetX", "targetY", "targetAngle"):
                            action.pop(key, None)
                elif coordinate_target:
                    # Location-target abilities support target/coordinates;
                    # angle is only legal when their contract explicitly says
                    # so (none of the current duel location abilities do).
                    if action.get("targetMode") not in {None, "target", "coordinates"}:
                        for key in ("targetMode", "targetX", "targetY", "targetAngle"):
                            action.pop(key, None)
                elif target_mode is None:
                    for key in (
                        "targetMode", "targetX", "targetY", "targetAngle",
                        "targetOffsetX", "targetOffsetY", "movementMode", "movementDirection",
                    ):
                        action.pop(key, None)
                else:
                    # Target-only abilities may carry their one canonical mode,
                    # but cannot carry coordinate/angle payloads.
                    if action.get("targetMode") not in {None, target_mode}:
                        action.pop("targetMode", None)
                    for key in ("targetX", "targetY", "targetAngle", "targetOffsetX", "targetOffsetY", "movementMode", "movementDirection"):
                        action.pop(key, None)
                if not orientation_config:
                    action.pop("phaseFacingMode", None)


def _repair_condition_operand_types(program: dict[str, Any]) -> None:
    """Align built-in expression operands with the Java variable contract.

    The generic operand schema cannot express the type of every possible
    custom variable.  For canonical variables, repair an obvious JSON-type
    mismatch (for example a boolean literal emitted with ``type: number``).
    If a model compares a boolean to a variable/number operand, no equivalent
    Java operand exists, so replace that condition with ``always`` and let the
    candidate continue through authoritative validation rather than losing the
    entire batch.
    """
    variables = load_game_knowledge()["botLogic"]["variables"]
    custom_types = {
        item.get("id"): item.get("valueType")
        for item in program.get("customVariables", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    roots = program.get("roots")
    if not isinstance(roots, list):
        return
    for root in roots:
        if not isinstance(root, dict):
            continue
        for branch in _walk_branches(root.get("branches")):
            conditions = branch.get("conditions")
            if not isinstance(conditions, list):
                continue
            for index, condition in enumerate(conditions):
                if not isinstance(condition, dict) or condition.get("type") != "expression":
                    continue
                left = condition.get("left")
                contract = variables.get(left) if isinstance(left, str) else None
                expected = (
                    str(contract.get("valueType", "")).lower()
                    if isinstance(contract, dict)
                    else str(custom_types.get(left, "")).lower()
                )
                if expected not in {"boolean", "number"}:
                    continue
                right = condition.get("right")
                if not isinstance(right, dict):
                    continue
                right_type = right.get("type")
                value = right.get("value")
                if expected == "boolean":
                    if isinstance(value, bool):
                        right["type"] = "boolean"
                    else:
                        conditions[index] = {"type": "always"}
                elif expected == "number":
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        right["type"] = "number"
                    elif right_type == "variable":
                        referenced = right.get("value")
                        referenced_contract = variables.get(referenced) if isinstance(referenced, str) else None
                        referenced_type = (
                            str(referenced_contract.get("valueType", "")).lower()
                            if isinstance(referenced_contract, dict)
                            else str(custom_types.get(referenced, "")).lower()
                        )
                        if referenced_type != "number":
                            conditions[index] = {"type": "always"}
                    else:
                        conditions[index] = {"type": "always"}


def _repair_missing_ability_action(program: dict[str, Any], available: set[int]) -> None:
    """Ensure a model's executable tree contains a legal combat action.

    The JSON grammar cannot express the cross-tree invariant that a candidate
    must contain an integer ability action.  Qwen occasionally returns a
    rotation-only or movement-only branch even when the prompt and schema
    describe that requirement.  Adding the first allowed ability to the first
    executable branch is semantics-preserving for the existing actions and
    gives the canonical validator a real combat program to evaluate.
    """
    if not available:
        return

    def branches_have_ability(branches: Any) -> bool:
        if not isinstance(branches, list):
            return False
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            actions = branch.get("actions")
            if isinstance(actions, list) and any(
                isinstance(action, dict)
                and type(action.get("action")) is int
                and action.get("action") in available
                for action in actions
            ):
                return True
            if branches_have_ability(branch.get("children")):
                return True
        return False

    def first_branch(branches: Any) -> dict[str, Any] | None:
        if not isinstance(branches, list):
            return None
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            return branch
        return None

    roots = program.get("roots")
    if not isinstance(roots, list) or any(
        branches_have_ability(root.get("branches"))
        for root in roots
        if isinstance(root, dict)
    ):
        return

    target_branch: dict[str, Any] | None = None
    for root in roots:
        if not isinstance(root, dict):
            continue
        target_branch = first_branch(root.get("branches"))
        if target_branch is not None:
            break
    if target_branch is None:
        if not roots:
            roots.append({
                "id": "ai-fallback-root",
                "branches": [{
                    "conditions": [{"type": "always"}],
                    "actions": [],
                    "children": [],
                }],
            })
            target_branch = roots[0]["branches"][0]
        else:
            return

    actions = target_branch.get("actions")
    if not isinstance(actions, list):
        actions = []
        target_branch["actions"] = actions
    # `none` cannot be combined with executable actions under the Java rules.
    actions[:] = [
        action for action in actions
        if not (isinstance(action, dict) and action.get("action") == "none")
    ]
    actions.append({"action": min(available), "selectable": "opponent_1"})


def _repair_selected_condition_metadata(program: dict[str, Any], available: set[int]) -> None:
    """Repair one common model omission without changing game semantics.

    Qwen frequently emits ``bot.selectedAbilityReady`` but omits the required
    ability selector.  The branch's integer ability action is the least
    surprising intended selector; when there is no such action, use the first
    allowed equipped ability.  The repaired program is still passed through
    the complete Python and authoritative Java validators.
    """
    variables = load_game_knowledge()["botLogic"]["variables"]

    def walk(branches: Any) -> None:
        if not isinstance(branches, list):
            return
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            actions = branch.get("actions")
            branch_abilities = []
            if isinstance(actions, list):
                branch_abilities = [
                    action.get("action")
                    for action in actions
                    if isinstance(action, dict)
                    and type(action.get("action")) is int
                    and action.get("action") in available
                ]
            fallback = branch_abilities[0] if branch_abilities else min(available)
            conditions = branch.get("conditions")
            if isinstance(conditions, list):
                for condition in conditions:
                    if not isinstance(condition, dict):
                        continue
                    references = []
                    left = condition.get("left")
                    if isinstance(left, str):
                        references.append(left)
                    right = condition.get("right")
                    if isinstance(right, dict) and right.get("type") == "variable":
                        value = right.get("value")
                        if isinstance(value, str):
                            references.append(value)
                    if any(
                        isinstance(variables.get(variable_id), dict)
                        and str(variables[variable_id].get("source", "")).startswith("SELECTED_ABILITY_")
                        for variable_id in references
                    ):
                        ability = condition.get("ability")
                        if type(ability) is not int or ability not in available:
                            condition["ability"] = fallback
                    _repair_condition_target_metadata(condition, variables)
            walk(branch.get("children"))

    roots = program.get("roots")
    if isinstance(roots, list):
        for root in roots:
            if isinstance(root, dict):
                walk(root.get("branches"))


def _repair_condition_target_metadata(condition: dict[str, Any], variables: dict[str, Any]) -> None:
    """Drop target fields when the referenced left variable cannot target.

    The structured model schema permits target metadata on every expression,
    but the authoritative contract permits it only for variables with target
    modes.  Removing unsupported fields is semantics-preserving and prevents a
    harmless model decoration such as ``targetMode: target`` from invalidating
    an otherwise executable condition.
    """
    left = condition.get("left")
    contract = variables.get(left) if isinstance(left, str) else None
    target_modes = contract.get("targetModes", []) if isinstance(contract, dict) else []
    requested_mode = condition.get("targetMode")
    if not target_modes:
        for key in ("targetMode", "targetX", "targetY", "targetAngle"):
            condition.pop(key, None)
    elif requested_mode is not None and requested_mode not in target_modes:
        for key in ("targetMode", "targetX", "targetY", "targetAngle"):
            condition.pop(key, None)


def validate_candidate_response(payload: Any, context: MatchContext) -> list[CandidateValidation]:
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        return [CandidateValidation(candidate_id=None, valid=False, issues=[
            _issue("invalid_envelope", "$", "response must contain a candidates array")
        ])]
    return [validate_candidate(value, context, index) for index, value in enumerate(payload["candidates"])]


def merge_authoritative_validation(
    prevalidation: list[CandidateValidation], authoritative: dict[str, Any]
) -> list[CandidateValidation]:
    by_index = {item.get("index"): item for item in authoritative.get("results", [])}
    merged: list[CandidateValidation] = []
    for index, candidate in enumerate(prevalidation):
        issues = list(candidate.issues)
        result = by_index.get(index)
        if result is None:
            issues.append(_issue("authoritative_validation_missing", f"$.candidates[{index}].program", "authoritative validation returned no result"))
        else:
            for message in result.get("errors", []):
                issues.append(_issue("authoritative_validation", f"$.candidates[{index}].program", str(message)))
            if result.get("valid") is False and not result.get("errors"):
                issues.append(_issue(
                    "authoritative_validation",
                    f"$.candidates[{index}].program",
                    "authoritative validation rejected the program",
                ))
        merged.append(CandidateValidation(
            candidate_id=candidate.candidate_id,
            valid=not issues,
            issues=issues,
        ))
    return merged


def validate_candidate(candidate: Any, context: MatchContext, index: int = 0) -> CandidateValidation:
    base = f"$.candidates[{index}]"
    issues: list[ValidationIssue] = []
    if not isinstance(candidate, dict):
        return CandidateValidation(candidate_id=None, valid=False, issues=[
            _issue("invalid_candidate", base, "candidate must be an object")
        ])
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        issues.append(_issue("candidate_id_required", f"{base}.candidate_id", "candidate_id must be a non-empty string"))
        candidate_id = None
    program = candidate.get("program")
    if not isinstance(program, dict):
        issues.append(_issue("program_required", f"{base}.program", "program must be an object"))
        return CandidateValidation(candidate_id=candidate_id, valid=False, issues=issues)
    if program.get("version") != "bot-logic-tree-v1":
        issues.append(_issue("wrong_brain_version", f"{base}.program.version", "version must be bot-logic-tree-v1"))

    roots = program.get("roots")
    if not isinstance(roots, list):
        issues.append(_issue("roots_required", f"{base}.program.roots", "roots must be an array"))
        roots = []
    knowledge = load_game_knowledge()
    limits = knowledge["limits"]
    standard = {int(value) for value in knowledge["standardAbilities"]}
    equipped = set(context.self.selected_abilities) - standard
    available = standard | equipped
    known_actions = set(knowledge["botLogic"]["commonActions"])
    known_selectables = set(knowledge["botLogic"]["selectables"])
    variable_contracts = knowledge["botLogic"]["variables"]
    known_variables = set(variable_contracts)
    known_status_effects = set(knowledge["botLogic"]["statusEffects"])

    loadout = program.get("loadout", {})
    loadout_abilities = loadout.get("abilities", []) if isinstance(loadout, dict) else []
    if not isinstance(loadout_abilities, list) or any(not isinstance(value, int) for value in loadout_abilities):
        issues.append(_issue("invalid_loadout", f"{base}.program.loadout.abilities", "abilities must be an array of integer IDs"))
        loadout_abilities = []
    unavailable = sorted(set(loadout_abilities) - equipped)
    if unavailable:
        issues.append(_issue("unavailable_ability", f"{base}.program.loadout.abilities", f"abilities are unavailable: {unavailable}"))

    counters = {"actions": 0, "conditions": 0}
    if len(roots) > limits["maxRoots"]:
        issues.append(_issue("root_limit", f"{base}.program.roots", "root count exceeds the canonical limit"))
    for root_index, root in enumerate(roots):
        if not isinstance(root, dict) or not isinstance(root.get("branches"), list):
            issues.append(_issue("invalid_root", f"{base}.program.roots[{root_index}]", "root must contain a branches array"))
            continue
        _validate_branches(root["branches"], f"{base}.program.roots[{root_index}].branches",
                           available, known_actions, known_selectables, variable_contracts,
                           known_variables, known_status_effects, counters, issues)
    if not any(
        isinstance(root, dict) and _contains_integer_ability_action(root.get("branches"))
        for root in roots
    ):
        issues.append(_issue(
            "ability_action_required",
            f"{base}.program.roots",
            "candidate must contain at least one available integer ability action; rotation or movement alone cannot fight",
        ))
    if counters["actions"] > limits["maxActionNodes"]:
        issues.append(_issue("action_limit", f"{base}.program.roots", "action node count exceeds the canonical limit"))
    if counters["conditions"] > limits["maxTotalConditions"]:
        issues.append(_issue("condition_limit", f"{base}.program.roots", "condition count exceeds the canonical limit"))
    return CandidateValidation(candidate_id=candidate_id, valid=not issues, issues=issues)


def _contains_integer_ability_action(branches: Any) -> bool:
    if not isinstance(branches, list):
        return False
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        actions = branch.get("actions")
        if isinstance(actions, list) and any(
            isinstance(action, dict)
            and type(action.get("action")) is int
            for action in actions
        ):
            return True
        if _contains_integer_ability_action(branch.get("children")):
            return True
    return False


def _validate_branches(branches: list[Any], path: str, available: set[int], known_actions: set[str],
                       known_selectables: set[str], variable_contracts: dict[str, Any],
                       known_variables: set[str], known_status_effects: set[str],
                       counters: dict[str, int], issues: list[ValidationIssue]) -> None:
    for index, branch in enumerate(branches):
        branch_path = f"{path}[{index}]"
        if not isinstance(branch, dict):
            issues.append(_issue("invalid_branch", branch_path, "branch must be an object"))
            continue
        conditions, actions, children = (branch.get("conditions", []), branch.get("actions", []), branch.get("children", []))
        if not all(isinstance(value, list) for value in (conditions, actions, children)):
            issues.append(_issue("invalid_branch_arrays", branch_path, "conditions, actions, and children must be arrays"))
            continue
        counters["conditions"] += len(conditions)
        counters["actions"] += len(actions)
        for action_index, action in enumerate(actions):
            action_path = f"{branch_path}.actions[{action_index}]"
            if not isinstance(action, dict):
                issues.append(_issue("invalid_action", action_path, "action must be an object"))
                continue
            action_id = action.get("action")
            if isinstance(action_id, int) and action_id not in available:
                issues.append(_issue("unavailable_action", f"{action_path}.action", f"ability {action_id} is unavailable"))
            elif isinstance(action_id, str) and action_id not in known_actions:
                issues.append(_issue("unknown_action", f"{action_path}.action", f"unknown action: {action_id}"))
            elif not isinstance(action_id, (str, int)):
                issues.append(_issue("invalid_action_id", f"{action_path}.action", "action must be a string or integer"))
            selectable = action.get("selectable")
            if isinstance(selectable, str) and selectable.split(":", 1)[0] not in known_selectables:
                issues.append(_issue("unknown_selectable", f"{action_path}.selectable", f"unknown selectable: {selectable}"))
        for condition_index, condition in enumerate(conditions):
            condition_path = f"{branch_path}.conditions[{condition_index}]"
            if not isinstance(condition, dict):
                issues.append(_issue("invalid_condition", condition_path, "condition must be an object"))
                continue
            left = condition.get("left")
            if isinstance(left, str) and not left.startswith("custom.") and left not in known_variables:
                issues.append(_issue("unknown_variable", f"{condition_path}.left", f"unknown variable: {left}"))
            referenced_variables: list[str] = []
            if isinstance(left, str):
                referenced_variables.append(left)
            right = condition.get("right")
            if isinstance(right, dict) and right.get("type") == "variable" and isinstance(right.get("value"), str):
                referenced_variables.append(right["value"])
            for variable_id in referenced_variables:
                contract = variable_contracts.get(variable_id)
                source = contract.get("source") if isinstance(contract, dict) else None
                if isinstance(source, str) and source.startswith("SELECTED_ABILITY_"):
                    ability = condition.get("ability")
                    if type(ability) is not int or ability not in available:
                        issues.append(_issue(
                            "ability_required",
                            f"{condition_path}.ability",
                            f"{variable_id} requires an allowed equipped ability ID",
                        ))
                if isinstance(source, str) and source.startswith("SELECTED_STATUS_EFFECT_"):
                    status_effect = condition.get("statusEffect")
                    if not isinstance(status_effect, str) or status_effect not in known_status_effects:
                        issues.append(_issue(
                            "status_effect_required",
                            f"{condition_path}.statusEffect",
                            f"{variable_id} requires an allowed status effect",
                        ))
        _validate_branches(children, f"{branch_path}.children", available, known_actions,
                           known_selectables, variable_contracts, known_variables,
                           known_status_effects, counters, issues)


def _issue(code: str, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, path=path, message=message)
