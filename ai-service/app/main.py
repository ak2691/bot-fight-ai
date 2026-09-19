from fastapi import FastAPI, HTTPException

from .config import get_settings
from .models import GenerateRequest, GenerateResponse
from .ollama_client import OllamaClient, OllamaError
from .prompting import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt


settings = get_settings()
ollama = OllamaClient(
    base_url=settings.ollama_base_url,
    timeout_seconds=settings.ollama_timeout_seconds,
)

app = FastAPI(
    title="Bot Fight AI",
    version="0.1.0-local",
    description=(
        "Local Ollama test harness for structured Bot Fight strategy generation. "
        "Game validation and simulation are not connected yet."
    ),
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/ollama/health")
async def ollama_health() -> dict[str, object]:
    try:
        payload = await ollama.health()
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    models = payload.get("models", [])
    return {
        "status": "ok",
        "base_url": settings.ollama_base_url,
        "configured_model": settings.ollama_model,
        "installed_models": models,
    }


@app.post("/v1/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    model = request.model or settings.ollama_model
    user_prompt = build_user_prompt(
        context=request.context,
        candidate_count=request.candidate_count,
        instructions=request.instructions,
    )

    try:
        reply = await ollama.chat(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=request.temperature,
        )
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return GenerateResponse(
        model=reply.model,
        prompt_version=PROMPT_VERSION,
        candidate_count=request.candidate_count,
        raw_response=reply.content,
        parsed_response=reply.parsed,
        parse_error=reply.parse_error,
        ollama_metadata=reply.metadata,
    )
