# AI service

This is the first local test harness for Bot Fight AI. It is a small Python/FastAPI service that accepts a generic match-context JSON object, asks a local Ollama model for JSON candidates, and returns the model response for inspection.

It is deliberately not connected to Bot Fight Online, a simulator, a database, or fine-tuning yet. The game-specific program schema is still unconfirmed, so this endpoint does not claim that generated programs are valid for the real game.

## Local setup

Use Python 3.12 for the development environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Ollama should be running locally at `http://127.0.0.1:11434`. Set `OLLAMA_MODEL` in `.env` to a model that is installed locally.

Start the API from this directory:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

Then open `http://127.0.0.1:8000/docs` or call `POST /v1/generate` with a JSON context. An example request is in `examples/request.json`.

## Current endpoint behavior

- `GET /healthz` checks that FastAPI is alive without requiring Ollama.
- `GET /v1/ollama/health` checks the local Ollama API and lists installed models.
- `POST /v1/generate` sends the context to Ollama with JSON mode enabled and returns both the raw model content and any parsed JSON.

The parsed response is diagnostic output only. Once the real Bot Fight program model is confirmed, add versioned schema validation and semantic validation before treating a candidate as executable.

Future responsibilities:

- Receive and persist match context.
- Assemble versioned LLM requests and parse strict JSON output.
- Validate candidates before simulation.
- Maintain the opponent pool and build simulation batches.
- Rank simulator results and select a candidate.
- Submit the selected program to Bot Fight Online.
- Record live results and produce offline training examples.

Current/future layout:

```text
ai-service/
  app/               Minimal API, Ollama adapter, and prompt builder (now)
  examples/          Local request examples (now)
  tests/             Offline unit tests (now)
  app/api/            Future routes and authentication adapters
  app/application/    Future match-decision orchestration
  app/domain/         Future candidate, experiment, and ranking types
  app/llm/            Future provider/model adapters and prompt templates
  app/game_api/       Future Bot Fight Online client
  app/persistence/    Future PostgreSQL repositories and migrations
  app/validation/     Future schema and game-rule validation orchestration
```

Read [AGENTS.md](../AGENTS.md), [context.md](../context.md), and [docs/llm-training.md](../docs/llm-training.md) before adding code here.
