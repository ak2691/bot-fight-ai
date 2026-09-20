# Bot Fight AI project context

Last updated: 2026-09-19

## Mission

Build an autonomous backend player for Bot Fight Online. The AI receives a match and round context, produces structured Bot Fight programs, validates them, evaluates them against opponent pools with the real deterministic simulator, selects the strongest candidate, and submits it before the build phase ends.

## Current state

This repository contains the architecture/context scaffold and a local
Ollama/FastAPI candidate-generation path. The canonical Bot Fight Online server
is available locally at `C:\dev\botfight\server`. Its `duel-v1` registries,
`bot-logic-tree-v1` validation, and authoritative simulator are accessed through
a development Java bridge; they are not reimplemented in Python.

The checked-in game-knowledge snapshot contains canonical ability timing,
effects, entities, hitboxes, logic variables/selectables, arena data, and limits.
The prompt builder filters that snapshot to the current match's known abilities.
Fast Python candidate checks are advisory; the Java validator remains authoritative.

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
- `/v1/generate` accepts a versioned internal match context and returns raw/parsed
  model output plus machine-readable candidate prechecks.
- `/v1/validate` and `/v1/simulate` use the canonical server implementation via
  a local compilation bridge. This bridge is a development mechanism, not the
  production authenticated simulator-service contract.

## Intended boundaries if the proposal is confirmed

If a shared simulator is adopted, it should be authoritative for game execution. The Python service may rank results and decide which candidates to submit, but it must not duplicate combat, targeting, threshold, timing, or ability semantics. Rendering, WebSockets, persistence, and wall-clock delays should not belong in that engine.

Internal v1 JSON schemas are committed under `ai-service/contracts/v1`. The
eventual live Bot Fight Online match-context, submission, and simulator-service
envelopes still require explicit production API decisions.

The local test harness uses Ollama through its localhost HTTP API. Its prompt and request model are intentionally replaceable once the real game contract is known.

## Open questions to resolve before implementation

- How will the canonical simulator be exposed as an authenticated, bounded,
  versioned production service rather than a local source/classpath bridge?
- What exact live match-context and submission APIs will Bot Fight Online expose?
- What is the build-phase deadline and API authentication/idempotency contract for program submission?
- What telemetry is available after each round and what data is safe to retain for training?
- Which Java version, build system, deployment environment, and model-serving hardware are supported?
- Should the simulator and shared contracts live in this repository at all, or in/alongside the existing Bot Fight Online project?

## Next safe implementation slice

Add a versioned scripted opponent pool, deterministic replay fixtures, minimum
validity/selection policy, and experiment persistence around the existing
bounded evaluator. In parallel, define the authenticated production API between
Bot Fight Online and this service and harden the canonical validator with an
explicit hostile-JSON depth limit.

See [AGENTS.md](AGENTS.md) for repository rules and [docs/requirements.md](docs/requirements.md) for the phased roadmap.
