# Bot Fight AI project context

Last updated: 2026-09-12

## Mission

Build an autonomous backend player for Bot Fight Online. The AI receives a match and round context, produces structured Bot Fight programs, validates them, evaluates them against opponent pools with the real deterministic simulator, selects the strongest candidate, and submits it before the build phase ends.

## Current state

This repository contains the architecture/context scaffold and a minimal local Ollama/FastAPI test harness. The Bot Fight Online website and its authoritative game implementation are external to this repository and have not yet been provided. No simulator semantics or production program contract should be invented until the canonical program model, abilities, rules, and match lifecycle are available.

## Current working assumptions (not yet confirmed as an implementation setup)

- The AI remains a separate backend application and communicates with Bot Fight Online through APIs.
- The first evaluator is the real simulator, not a learned score model.
- The reusable simulator is a pure Java library; a Java REST service wraps it for batch requests.
- The orchestration service is Python/FastAPI.
- Candidate output is strict, versioned JSON.
- Candidate generation starts with a small configurable set, normally 10–20 programs.
- The opponent pool can contain self-play programs, older AI versions, scripted bots, and later historical human strategies.
- Each experiment stores enough information to reproduce the decision: context, model/prompt versions, generated candidates, validation, simulation inputs/results, selection, and eventual real-match outcome.
- Future model training uses immutable model versions and an evaluation gate before promotion.
- Round-to-round context includes previous telemetry and observed opponent behavior whenever the game can provide it.
- The current `/v1/generate` endpoint is diagnostic only: it accepts a generic context, asks Ollama for JSON, and returns the raw/parsed response without claiming game validity.

## Intended boundaries if the proposal is confirmed

If a shared simulator is adopted, it should be authoritative for game execution. The Python service may rank results and decide which candidates to submit, but it must not duplicate combat, targeting, threshold, timing, or ability semantics. Rendering, WebSockets, persistence, and wall-clock delays should not belong in that engine.

No shared contract files are currently committed. The eventual service envelopes and game-specific schema must be chosen after the existing Bot Fight Online domain model and API are inspected.

The local test harness uses Ollama through its localhost HTTP API. Its prompt and request model are intentionally replaceable once the real game contract is known.

## Open questions to resolve before implementation

- Where is the Bot Fight Online source repository and which module currently owns simulation logic?
- What is the exact program AST/graph format, including root types, condition operators, action parameters, thresholds, target selectors, and node limits?
- Which ability and rules definitions are versioned, and can the AI receive a self-contained rules snapshot per match?
- What is the build-phase deadline and API authentication/idempotency contract for program submission?
- What telemetry is available after each round and what data is safe to retain for training?
- Which Java version, build system, deployment environment, and model-serving hardware are supported?
- Should the simulator and shared contracts live in this repository at all, or in/alongside the existing Bot Fight Online project?

## Next safe implementation slice

Obtain the canonical game models and confirm the repository/module split first. Then replace the generic local context/prompt with the confirmed contract, decide the simulator location, obtain deterministic replay fixtures, and only then connect validation, simulation, and persistence.

See [AGENTS.md](AGENTS.md) for repository rules and [docs/requirements.md](docs/requirements.md) for the phased roadmap.
