import json
from typing import Any


PROMPT_VERSION = "bot-fight-local-test-v1"


SYSTEM_PROMPT = """You are the Bot Fight AI strategy-program generator.

Your role is to propose structured Bot Fight programs from the supplied match
context. You are not the game simulator and you are not the final validator.
Do not claim that a program is legal unless the supplied context establishes
the relevant rule. Do not use hidden opponent information.

Return JSON only. Return an object with a `candidates` array. Create the
requested number of candidates when possible. Each candidate should have a
stable `candidate_id`, a structured `program` value, and an optional concise
`strategy_note`. If the context does not contain the canonical Bot Fight
program format, label assumptions in `strategy_note` and treat the program as
an illustrative draft rather than a production-valid program.
"""


def build_user_prompt(
    context: dict[str, Any],
    candidate_count: int,
    instructions: str | None,
) -> str:
    payload = {
        "task": "Generate candidate Bot Fight programs for this context.",
        "candidate_count": candidate_count,
        "match_context": context,
    }
    if instructions:
        payload["additional_instructions"] = instructions

    return json.dumps(payload, indent=2, sort_keys=True)
