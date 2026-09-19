# Local Ollama test path

## Purpose

The current implementation is an inference smoke test, not the Bot Fight decision engine. It answers one narrow question first: can a local open-weight model receive a provisional context and return structured JSON that we can inspect?

No fine-tuning, validation against real game rules, simulation, persistence, or Bot Fight Online submission happens yet.

## Current flow

```text
JSON request
  → FastAPI `/v1/generate`
  → prompt builder
  → Ollama `/api/chat` with JSON mode
  → raw response + parsed JSON
```

The request accepts a generic `context` object because the canonical Bot Fight Online context and program schema have not been confirmed. The prompt explicitly tells the model to label assumptions rather than present invented rules as authoritative.

## Local model configuration

Configuration is read from `ai-service/.env` or environment variables:

```text
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_TIMEOUT_SECONDS=300
```

The model name is configurable. The default is a practical local starting point for the available development hardware, not a final model decision.

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
- Ollama timing/token metadata when available.

## What happens after the real game model is confirmed

1. Replace the generic request model with the canonical match-context contract.
2. Supply the exact program schema and game limits to the prompt.
3. Validate the returned candidate JSON and semantic game rules before accepting it.
4. Add candidate mutation and simulator evaluation.
5. Persist prompts, candidates, outcomes, and model versions.

The current endpoint should remain a small adapter so the local Ollama model can later be swapped for another open-weight runtime without changing the orchestration layer.
