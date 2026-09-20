"""Validate Bot Fight demonstration records and emit trainer JSONL files.

This tool intentionally uses only the Python standard library. It validates
the data contract and provenance metadata, but it does not replace the
authoritative game validator or simulator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ALLOWED_SPLITS = {"train", "validation", "test"}
ALLOWED_SOURCES = {"human", "codex", "ollama", "simulator", "other"}
REQUIRED_QUALITY_FIELDS = {
    "authoritative_valid",
    "ruleset_version",
    "brain_schema_version",
    "validator_version",
    "simulator_version",
}
EXPECTED_ROLES = ["system", "user", "assistant"]


class DatasetError(ValueError):
    """Raised when a source record is not safe to train on."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Raw source JSONL")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for generated trainer JSONL and manifest",
    )
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Allow records without authoritative_valid=true (for draft checks only)",
    )
    return parser.parse_args()


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise DatasetError(f"input file does not exist: {path}")

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"line {line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise DatasetError(f"line {line_number}: record must be a JSON object")
        value["_line_number"] = line_number
        records.append(value)
    if not records:
        raise DatasetError("input contains no records")
    return records


def require_string(value: Any, field: str, record_label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasetError(f"{record_label}: {field} must be a non-empty string")
    return value


def validate_messages(value: Any, record_label: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) != len(EXPECTED_ROLES):
        raise DatasetError(
            f"{record_label}: messages must contain exactly system, user, assistant"
        )

    messages: list[dict[str, str]] = []
    for index, (message, expected_role) in enumerate(zip(value, EXPECTED_ROLES)):
        if not isinstance(message, dict):
            raise DatasetError(f"{record_label}: messages[{index}] must be an object")
        role = message.get("role")
        if role != expected_role:
            raise DatasetError(
                f"{record_label}: messages[{index}].role must be {expected_role!r}"
            )
        content = require_string(
            message.get("content"), f"messages[{index}].content", record_label
        )
        messages.append({"role": role, "content": content})

    try:
        response = json.loads(messages[-1]["content"])
    except json.JSONDecodeError as exc:
        raise DatasetError(f"{record_label}: assistant content must be JSON: {exc}") from exc
    if not isinstance(response, dict) or not isinstance(response.get("candidates"), list):
        raise DatasetError(f"{record_label}: assistant JSON must contain candidates[]")
    if not response["candidates"]:
        raise DatasetError(f"{record_label}: candidates[] cannot be empty")
    for candidate_index, candidate in enumerate(response["candidates"]):
        if not isinstance(candidate, dict):
            raise DatasetError(f"{record_label}: candidate {candidate_index} must be an object")
        if not isinstance(candidate.get("candidate_id"), str) or not candidate["candidate_id"].strip():
            raise DatasetError(f"{record_label}: candidate {candidate_index} needs candidate_id")
        if not isinstance(candidate.get("program"), dict):
            raise DatasetError(f"{record_label}: candidate {candidate_index} needs program object")
    return messages


def validate_record(
    record: dict[str, Any],
    *,
    allow_unverified: bool,
    ids: set[str],
    prompts: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    line_number = record.get("_line_number", "?")
    example_id = require_string(record.get("example_id"), "example_id", f"line {line_number}")
    if example_id in ids:
        raise DatasetError(f"line {line_number}: duplicate example_id {example_id!r}")
    ids.add(example_id)

    split = require_string(record.get("split"), "split", example_id)
    if split not in ALLOWED_SPLITS:
        raise DatasetError(f"{example_id}: split must be one of {sorted(ALLOWED_SPLITS)}")
    source = require_string(record.get("source"), "source", example_id)
    if source not in ALLOWED_SOURCES:
        raise DatasetError(f"{example_id}: source must be one of {sorted(ALLOWED_SOURCES)}")

    messages = validate_messages(record.get("messages"), example_id)
    prompt_hash = hashlib.sha256(messages[1]["content"].encode("utf-8")).hexdigest()
    prior_split = prompts.get(prompt_hash)
    if prior_split is not None and prior_split != split:
        raise DatasetError(
            f"{example_id}: identical user prompt appears in both {prior_split!r} and {split!r}"
        )
    prompts[prompt_hash] = split

    quality = record.get("quality")
    if not isinstance(quality, dict):
        raise DatasetError(f"{example_id}: quality must be an object")
    missing = sorted(REQUIRED_QUALITY_FIELDS - quality.keys())
    if missing:
        raise DatasetError(f"{example_id}: quality missing {', '.join(missing)}")
    if not isinstance(quality["authoritative_valid"], bool):
        raise DatasetError(f"{example_id}: quality.authoritative_valid must be boolean")
    if not allow_unverified and quality["authoritative_valid"] is not True:
        raise DatasetError(f"{example_id}: authoritative_valid must be true")
    for field in REQUIRED_QUALITY_FIELDS - {"authoritative_valid"}:
        require_string(quality[field], f"quality.{field}", example_id)

    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        raise DatasetError(f"{example_id}: provenance must be an object")
    require_string(provenance.get("experiment_id"), "provenance.experiment_id", example_id)

    return split, {"messages": messages}


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    path.write_text(payload, encoding="utf-8", newline="\n")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    args = parse_args()
    try:
        records = load_records(args.input)
        ids: set[str] = set()
        prompts: dict[str, str] = {}
        by_split: dict[str, list[dict[str, Any]]] = {split: [] for split in ALLOWED_SPLITS}
        for record in records:
            split, output = validate_record(
                record,
                allow_unverified=args.allow_unverified,
                ids=ids,
                prompts=prompts,
            )
            by_split[split].append(output)
    except DatasetError as exc:
        print(f"dataset rejected: {exc}")
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    counts: dict[str, int] = {}
    for split in ("train", "validation", "test"):
        split_records = by_split[split]
        counts[split] = len(split_records)
        if split_records:
            hashes[split] = write_jsonl(args.output_dir / f"{split}.jsonl", split_records)

    source_bytes = args.input.read_bytes()
    manifest = {
        "format_version": "bot-fight-sft-manifest-v1",
        "source_file": str(args.input),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "record_count": len(records),
        "counts": counts,
        "generated_sha256": hashes,
        "allow_unverified": args.allow_unverified,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {"status": "ok", "counts": counts, "output_dir": str(args.output_dir)},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
