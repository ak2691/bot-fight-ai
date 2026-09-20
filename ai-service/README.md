# AI service

This local service accepts a versioned match context, builds a compact prompt
from the canonical Bot Fight Online Java registries, asks Ollama for JSON
candidates, and performs fast candidate prechecks. Development endpoints also
invoke the live server's authoritative brain validator and `duel-v1` simulator
through a local Java bridge.

The bridge requires the Bot Fight Online server checkout. It is not the future
production network boundary and does not duplicate gameplay rules in Python.

## Local setup

Use Python 3.12 for the development environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Ollama should be running locally at `http://127.0.0.1:11434`. The local
defaults use `qwen3:4b`, a compact prompt, a 16k context window, and a
10-minute model keep-alive. Set `OLLAMA_MODEL` in `.env` to a model that is
installed locally. Set `BOTFIGHT_SERVER_ROOT` if the canonical server is not
at `C:\dev\botfight\server`.

Start the API from this directory:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

For lower-memory local inference, keep `PROMPT_MODE=compact` and use
`OLLAMA_CONTEXT_WINDOW=16384`. `PROMPT_MODE=full` remains available for
contract audits and debugging, but should be paired with a larger context
window such as `OLLAMA_CONTEXT_WINDOW=32768`. `OLLAMA_KEEP_ALIVE` keeps the
model loaded between sequential requests so it does not reload for every round.

For a lower-memory Ollama process, configure these before starting Ollama (or
as Windows user environment variables, followed by a full Ollama restart):

```powershell
$env:OLLAMA_NUM_PARALLEL="1"
$env:OLLAMA_MAX_LOADED_MODELS="1"
$env:OLLAMA_FLASH_ATTENTION="1"
$env:OLLAMA_KV_CACHE_TYPE="q8_0"
ollama serve
```

These limit concurrent model copies and reduce KV-cache memory. They are
Ollama-server settings, not FastAPI settings. `OLLAMA_KEEP_ALIVE` controls how
long the loaded model remains warm; it does not cap peak memory.

Then open `http://127.0.0.1:8000/docs` or call `POST /v1/generate` using
`examples/request.json`.

## Current endpoint behavior

- `GET /healthz` checks that FastAPI is alive without requiring Ollama.
- `GET /v1/ollama/health` checks the local Ollama API and lists installed models.
- `GET /v1/contracts` reports the active exported contract versions.
- `POST /v1/generate` sends filtered rules and match context to Ollama, parses
  the candidate envelope, and returns machine-readable prevalidation issues.
- `POST /v1/validate` runs the canonical Java submission validator.
- `POST /v1/simulate` validates two brains and runs one seeded authoritative duel.
- `POST /v1/evaluate` expands candidates across opponents and seeds (up to 200
  scenarios), isolates per-scenario failures, and returns deterministic rankings.
- `POST /v1/decide` is the single orchestration endpoint for Bot Fight Online:
  it generates, authoritatively validates, simulates, ranks, and returns one
  final program for each requested player. Candidate arrays never cross this
  boundary.

Examples are in `examples/`; JSON Schemas are in `contracts/v1/`. Candidate
prevalidation is advisory. A candidate must pass `/v1/validate` before it is
sent to `/v1/simulate` or used elsewhere.

After an ability, hitbox, logic, or arena contract changes in Bot Fight Online,
refresh the checked-in prompt snapshot from the repository root:

```powershell
.\tools\sync-game-contracts.ps1 -BotFightServerRoot C:\dev\botfight\server
```

Remaining responsibilities:

- Receive and persist match context.
- Maintain versioned scripted, historical, and self-play opponent pools.
- Apply a minimum-validity policy and select a final candidate from rankings.
- Submit the selected program to Bot Fight Online.
- Record live results and produce offline training examples.
- Replace the local Java bridge with an authenticated production boundary.

Current/future layout:

```text
ai-service/
  app/               API, prompt context, validation, and local Java bridge
  app/data/          Generated canonical duel-v1 prompt knowledge
  contracts/v1/      Versioned JSON boundary schemas
  examples/          Generation, brain, and simulation request examples
  tests/             Offline unit tests
  app/api/            Future routes and authentication adapters
  app/application/    Future match-decision orchestration
  app/domain/         Future candidate, experiment, and ranking types
  app/llm/            Future provider/model adapters and prompt templates
  app/game_api/       Future Bot Fight Online client
  app/persistence/    Future PostgreSQL repositories and migrations
  app/validation/     Future schema and game-rule validation orchestration
```

Read [AGENTS.md](../AGENTS.md), [context.md](../context.md), and [docs/llm-training.md](../docs/llm-training.md) before adding code here.
