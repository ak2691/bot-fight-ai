# Bot Fight AI

Bot Fight AI is a separate backend application that generates and evaluates programs for Bot Fight Online. It communicates with the existing game through APIs; it does not become part of the production game server.

This repository contains the architecture/context scaffold plus a small local Ollama/FastAPI test harness. It intentionally does not contain Bot Fight Online integration, a simulator, a database, or fine-tuning yet.

Start with these files:

1. [AGENTS.md](AGENTS.md) — rules for future implementation work and coding agents.
2. [context.md](context.md) — the short, canonical project context.
3. [docs/architecture.md](docs/architecture.md) — component boundaries and data flow.
4. [docs/requirements.md](docs/requirements.md) — functional requirements, quality requirements, and phased scope.
5. [docs/local-ollama.md](docs/local-ollama.md) — how the current no-fine-tuning model test works.

## Repository layout

```text
ai-service/                 Python/FastAPI + Ollama local test harness
docs/                       Architecture, requirements, and future-design notes
```

The existing Bot Fight Online source code is external to this repository. The Java simulator split and shared contract format are intentionally not scaffolded until the setup is confirmed. The current `ai-service` endpoint accepts a generic provisional context and is for local model inspection only; it does not produce game-authoritative programs yet.

## Intended first implementation sequence

1. Confirm the canonical program, ability, and rules models from Bot Fight Online.
2. Confirm the desired repository split, API ownership, and contract format.
3. Replace the local generic prompt/context with the confirmed Bot Fight model.
4. Extract deterministic game logic into the confirmed simulator location and lock it down with replay tests.
5. Add experiment storage, real-match callbacks, and offline training only after the simulation loop is reproducible.
