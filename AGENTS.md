# AGENTS.md

These instructions apply to the entire Bot Fight AI repository. Read this file and [context.md](context.md) before changing code or contracts. Read the relevant document in `docs/` before implementing a component.

## Current repository state

This is a planning and architecture scaffold with a small local Ollama/FastAPI inference harness. The authoritative Bot Fight Online implementation is not present here. The Java simulator and shared-contract directories were intentionally removed because that setup has not been confirmed; they are not permission to recreate the game from assumptions.

## Non-negotiable architecture boundaries

- Bot Fight AI is a separate backend. Production game integration happens through authenticated, versioned APIs.
- If a simulator is introduced, its engine must remain a pure Java library. It may contain domain, rules, validation, execution, randomness, and telemetry code, but no Spring Boot, HTTP, WebSocket, database, rendering, filesystem, or real-time-delay dependencies.
- If a simulator service is introduced, it should be the only REST-facing Java module. It should map the confirmed contract to engine types, run bounded batches, and map results back to the API format.
- `ai-service` owns orchestration, LLM prompting/inference, candidate ranking, experiment persistence, and calls to the simulation service. It must not reimplement authoritative game rules.
- The simulator is the initial source of truth for candidate quality. Do not add a learned/neural candidate evaluator to the first implementation.
- Any confirmed contract and game-rule versions must be persisted with every generated candidate and simulation result.

## Rules for future implementation

- Treat the existing Bot Fight Online code and published API definitions as canonical. If a rule is unknown, record a TODO or an explicit compatibility decision; do not silently guess.
- Keep structured program generation JSON-only at the service boundary. Free-form LLM text is not an accepted candidate.
- Run schema validation and semantic/game-rule validation before simulation. Invalid candidates must be rejected with actionable, machine-readable issues.
- Make every simulation reproducible from an explicit seed, rules snapshot, match configuration, both programs, and simulator version.
- Keep simulation batches bounded and isolated. A malformed candidate must not abort unrelated candidates in the same request.
- Preserve telemetry and failure details needed to replay an experiment. Do not store only aggregate win rate.
- Add deterministic replay, validation, and contract tests before optimizing throughput.
- Keep model versions immutable once used in an experiment. Promotion requires the evaluation gate described in [docs/llm-training.md](docs/llm-training.md).
- Keep secrets, production credentials, and real user data out of source control and fixtures.
- Prefer small interfaces and adapters so the initial model runtime can be replaced by vLLM or another self-hosted open-weight runtime later.

## What belongs where

- Root docs: durable project decisions and instructions that apply across services.
- Future shared contracts: externally exchanged payloads; choose a versioning format only after the integration setup is confirmed.
- Future simulator engine: authoritative deterministic match execution and game semantics.
- Future simulator service: HTTP concerns, request limits, authentication, serialization, and batch orchestration.
- `ai-service`: context normalization, prompt assembly, LLM adapter, candidate validation orchestration, opponent-pool selection, experiment records, and Bot Fight Online API adapters.
- `docs/`: design notes and acceptance criteria; update them when an architectural decision changes.

## Definition of done for a future feature

A feature is not complete until its contract and failure behavior are documented, tests cover the relevant deterministic or integration behavior, version information is recorded, and the change preserves the engine/service boundary. For production-facing changes, include observability and authentication considerations.
