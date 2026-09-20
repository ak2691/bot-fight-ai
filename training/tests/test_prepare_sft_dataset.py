import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "tools" / "prepare_sft_dataset.py"


def record(example_id: str, split: str = "train") -> dict:
    return {
        "example_id": example_id,
        "split": split,
        "source": "human",
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": f"prompt-{example_id}"},
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "candidates": [
                            {"candidate_id": example_id, "program": {"roots": []}}
                        ]
                    }
                ),
            },
        ],
        "quality": {
            "authoritative_valid": True,
            "ruleset_version": "duel-v1",
            "brain_schema_version": "bot-logic-tree-v1",
            "validator_version": "validator-v1",
            "simulator_version": "simulator-v1",
        },
        "provenance": {"experiment_id": f"experiment-{example_id}"},
    }


def run_tool(
    tmp_path: Path, records: list[dict], *extra: str
) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "records.jsonl"
    source.write_text(
        "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
    )
    output = tmp_path / "generated"
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(source),
            "--output-dir",
            str(output),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_prepares_trainer_files_and_manifest(tmp_path: Path):
    result = run_tool(tmp_path, [record("one"), record("two", "validation")])

    assert result.returncode == 0, result.stdout + result.stderr
    train = (tmp_path / "generated" / "train.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    validation = (tmp_path / "generated" / "validation.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    manifest = json.loads(
        (tmp_path / "generated" / "manifest.json").read_text(encoding="utf-8")
    )
    assert len(train) == 1
    assert len(validation) == 1
    assert manifest["counts"] == {"test": 0, "train": 1, "validation": 1}
    assert "quality" not in json.loads(train[0])


def test_rejects_unverified_records_by_default(tmp_path: Path):
    item = record("unverified")
    item["quality"]["authoritative_valid"] = False

    result = run_tool(tmp_path, [item])

    assert result.returncode == 2
    assert "authoritative_valid must be true" in result.stdout


def test_rejects_prompt_leakage_across_splits(tmp_path: Path):
    first = record("one", "train")
    second = record("two", "validation")
    second["messages"][1]["content"] = first["messages"][1]["content"]

    result = run_tool(tmp_path, [first, second])

    assert result.returncode == 2
    assert "identical user prompt" in result.stdout
