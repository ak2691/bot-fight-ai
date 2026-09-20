import json
from typing import Any

from .game_contracts import build_model_context, load_game_knowledge
from .models import MatchContext

PROMPT_VERSION = "bot-fight-candidate-generation-v22-rules-contracts"


GAME_RULES = """BOT FIGHT PROGRAMMING RULES

The output is a `bot-logic-tree-v1` JSON program executed by a real-time,
tick-based behavior-tree engine. It is data, not free-form code. The bot can
only perform actions represented by its selected branch.

Execution rules:
- Roots and branches are evaluated in priority order. Conditions choose the
  branch; an `else` branch is the fallback when its sibling `if` branch does
  not run. Child branches are evaluated within their parent branch.
- A selected branch may contain at most one rotation action, one movement
  action, and one integer ability action. Those action slots can be dispatched
  in the same tick. `none` does nothing and `variable` changes a declared
  custom variable.
- `rotate_toward_enemy` changes facing only. It never deals damage or applies
  an ability effect. An executable candidate must contain an integer ability
  action; rotation or movement alone is not enough.
- An integer action is an ability ID from the supplied ability rules. The
  ability name, effect list, hitbox, target mode, facing requirement, timing,
  cooldown, charges, and resource model are authoritative. Do not infer a
  different effect from the number. Use the per-ID `ability_action_contracts`
  entry for the fields that action accepts; the shared ability template is
  not permission to add every optional field.
- An ability can be unavailable while cooling down, preparing, or active. The
  supplied selected-ability variables expose those states. The global ability
  lock and phase timing still apply; a condition does not bypass them.

Targeting and movement rules:
- `my_bot` is the generated bot and `opponent_1` is its opponent. Use only
  selectable IDs and variable IDs present in the supplied logic contract.
- With `movementMode: target`, movement is relative to the vector from the
  acting bot to the selected target, not relative to current facing. Direction
  `0` points toward the target, `180` points away, `90` is clockwise/right,
  and `-90` is counterclockwise/left.
- With `movementMode: absolute`, use a permitted compass direction or degree
  value from the contract. Coordinate and angle modes require their matching
  target fields. Use each mode only with the fields its action contract allows.
- Directional hitboxes use the bot's facing and the ability's hitbox/arc. A
  target selector alone does not change facing unless the ability contract
  says it does.

Condition and data rules:
- An `always` condition has only `type: "always"`. An expression condition
  requires `left`, a canonical comparator, a typed `right`, and integer
  `ability` metadata. Selected-ability variables use that field to identify
  the inspected ability; selected-status variables use `statusEffect`.
- The `right` operand type must match the variable's `valueType`. Boolean
  variables accept a boolean literal only; numeric variables accept a numeric
  literal or a numeric variable. Do not compare a boolean variable to a number
  or to a variable operand.
- Custom variables must be declared with the supplied type and initial value.
  They may be changed only through the listed variable operations and operand
  forms.
- Output JSON only. Follow the supplied response schema exactly, use only
  fields and enum values present in the context, and keep within all supplied
  node, condition, action, coordinate, and value limits.
"""


SYSTEM_PROMPT = """You generate Bot Fight `bot-logic-tree-v1` JSON programs.

Translate the supplied match-specific ability rules and logic contract into
executable JSON. Ability IDs are references to the named mechanical ability
definitions in the context; they are not standalone numeric instructions.
Use the schema and canonical game snapshot as the source of truth. Do not
write an explanation or invent behavior that is not described by the context.

Hard requirements:
1. Return JSON only: `{\"candidates\":[...]}` and no commentary.
2. Every candidate has at least one integer ability action. A candidate with
   only `rotate_toward_enemy`, only `move_walk`, only `none`, or empty roots
   is invalid and must not be returned.
3. Rotation changes facing only. Put it beside an integer ability action only
   when the program requires both actions in the same branch.
4. A branch may contain at most one rotation, one movement, and one integer
   ability action. Do not use movement or rotation as the only program action.
5. Use `opponent_1` for the opponent and `my_bot` for the generated bot. Use
   the target-relative movement and direction semantics in the supplied rules.
6. Use only ability IDs, action names, variables, selectables, comparators,
   status effects, and fields present in the supplied context/contracts. Every
   expression condition includes an integer `ability` field; selected-ability
   variables use it to identify the ability being inspected.
The response schema and canonical game snapshot are authoritative. Do not
repeat the context, invent fields, or return candidate/ranking metadata outside
the schema.
"""


def build_user_prompt(
    context: MatchContext,
    candidate_count: int,
    instructions: str | None,
    prompt_mode: str = "compact",
) -> str:
    knowledge = load_game_knowledge()
    standard_abilities = {int(value) for value in knowledge["standardAbilities"]}
    payload: dict[str, Any] = {
        "task": (
            "Generate exactly candidate_count executable programs for this duel. "
            "Use opponent_1 as the opponent and my_bot as the generated bot."
        ),
        "candidate_count": candidate_count,
        "game_rules": GAME_RULES,
        "game_and_match_context": build_model_context(context, prompt_mode=prompt_mode),
        "output_contract": {
            "notes": [
                "Return exactly candidate_count candidates.",
                "Every candidate_id must be a unique newly generated string.",
                "program.loadout.abilities contains only self selected non-standard IDs; omit the standard ability IDs "
                + ", ".join(str(value) for value in sorted(standard_abilities))
                + ".",
                "Every candidate must contain at least one integer ability action. A rotate-only, walk-only, none-only, or empty-root candidate is invalid.",
                "One branch may contain one rotation, one movement, and one integer ability action; do not add a second action of the same slot.",
                "Use canonical comparators lt, lte, eq, neq, gte, or gt. An always condition contains only type=always.",
                "Every expression condition requires left, comparator, typed right, and integer ability. For non-selected-ability variables, ability is still required by the output schema.",
                "Match each condition right operand to the left variable valueType. Boolean variables use right={type:boolean,value:true|false}; numeric variables use a number literal or numeric variable.",
                "Use bot.selectedAbilityReady/Active/OnCooldown/Preparing only with ability set to the specific available ability being checked.",
                "Use target-relative movement with the supplied direction semantics; absolute movement uses permitted fixed coordinate-system directions.",
                "Use an ability's ability_rules, name, effects, hitbox, and timing as mechanical facts. Do not infer an effect or target mode from the numeric ID.",
                "For integer actions, follow ability_action_contracts[action].allowedFields exactly; the shared ABILITY template is only a field-shape overview.",
                "Configuration dependencies are strict: coordinates need targetX and targetY; absolute movement needs movementDirection; coordinate/angle target modes need their matching target fields.",
                "Custom variables must match the supplied schema and may only be modified through the listed variable operations.",
                "Keep programs within the supplied limits.",
            ],
        },
    }
    if instructions:
        payload["additional_instructions"] = instructions

    return json.dumps(payload, indent=2, sort_keys=True)
