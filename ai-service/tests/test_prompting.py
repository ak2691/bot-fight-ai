import json

from app.prompting import PROMPT_VERSION, build_user_prompt


def test_user_prompt_contains_context_and_candidate_count() -> None:
    prompt = build_user_prompt(
        context={"round": 1, "abilities": ["example-ability"]},
        candidate_count=3,
        instructions="Prefer defensive variations.",
    )

    payload = json.loads(prompt)
    assert PROMPT_VERSION == "bot-fight-local-test-v1"
    assert payload["candidate_count"] == 3
    assert payload["match_context"]["round"] == 1
    assert payload["additional_instructions"] == "Prefer defensive variations."
