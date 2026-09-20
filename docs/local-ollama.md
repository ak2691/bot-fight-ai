# Local Ollama test path

## Purpose

The current implementation is a local match-decision slice. It uses canonical
game knowledge exported from Bot Fight Online, schema-constrained Ollama
generation, authoritative Java validation, and seeded authoritative simulation.
The `/v1/decide` route selects one final program per player; persistence and
live Bot Fight Online submission remain development-only.

## Current flow

```text
JSON request
  → FastAPI `/v1/decide` (or `/v1/generate` for diagnostics)
  → per-player candidate generation and ranking
  → prompt builder
  → compact filtered canonical duel-v1 context
  → Ollama `/api/chat` with a candidate JSON Schema
  → parsed candidates + authoritative Java validation/simulation
```

The request accepts `bot-fight-ai-match-context-v1`. The prompt contains only
the standard abilities, self-selected abilities, legally known opponent
abilities, logic grammar, arena rules, and supplied observations.

## Local model configuration

Configuration is read from `ai-service/.env` or environment variables:

```text
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_TIMEOUT_SECONDS=300
OLLAMA_CONTEXT_WINDOW=16384
OLLAMA_MAX_OUTPUT_TOKENS=2048
OLLAMA_KEEP_ALIVE=10m
PROMPT_MODE=compact
```

Compact mode includes the relevant ability definitions and the decision-making
grammar while omitting verbose entity/visual registries. Set
`PROMPT_MODE=full` when auditing the complete exported contract.
Full mode should be paired with a larger `OLLAMA_CONTEXT_WINDOW` if the
exported registry exceeds the compact prompt budget.

The FastAPI `OLLAMA_KEEP_ALIVE` setting keeps the model warm between sequential
requests. It is not a RAM limit. For lower-memory local Ollama runs, set these
before starting Ollama (or set them as Windows user environment variables and
restart the Ollama application):

```powershell
$env:OLLAMA_NUM_PARALLEL="1"
$env:OLLAMA_MAX_LOADED_MODELS="1"
$env:OLLAMA_FLASH_ATTENTION="1"
$env:OLLAMA_KV_CACHE_TYPE="q8_0"
ollama serve
```

The server settings control concurrent loaded copies and KV-cache size; the
FastAPI `.env` controls the request's model, context window, output budget, and
keep-alive duration.

## Running it

From `ai-service/`:

```powershell
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

Useful checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
Invoke-RestMethod http://127.0.0.1:8000/v1/ollama/health
```

To test generation from the repository root:

```powershell
$body = Get-Content .\ai-service\examples\request.json -Raw
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/v1/generate `
  -ContentType application/json `
  -Body $body
```

The response includes:

- The model actually used.
- Prompt version.
- Raw model content.
- Parsed JSON, if parsing succeeds.
- A parse error, if the model still returns invalid JSON.
- Machine-readable prevalidation and authoritative validation issues per candidate.
- Ollama timing/token metadata when available, including prompt-cache hits.

## Next integration work

1. Define authenticated live match-context and program-submission APIs.
2. Replace the local source/classpath bridge with a bounded simulator service.
3. Add managed opponent pools and replay fixtures.
4. Persist prompts, candidates, validation, simulations, outcomes, and versions.

The current endpoint should remain a small adapter so the local Ollama model can later be swapped for another open-weight runtime without changing the orchestration layer.
