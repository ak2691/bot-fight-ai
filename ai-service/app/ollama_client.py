import json
from dataclasses import dataclass
from typing import Any

import httpx


class OllamaError(RuntimeError):
    """Raised when the local Ollama API cannot satisfy a request."""


@dataclass(frozen=True)
class OllamaReply:
    model: str
    content: str
    parsed: Any | None
    parse_error: str | None
    metadata: dict[str, Any]


class OllamaClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_seconds)

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(f"Ollama health check failed: {exc}") from exc

        return payload

    async def chat(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        response_schema: dict[str, Any] | None = None,
        context_window: int | None = None,
        max_output_tokens: int | None = None,
        keep_alive: str | int | None = None,
    ) -> OllamaReply:
        request_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": response_schema or "json",
            "think": False,
            **({"keep_alive": keep_alive} if keep_alive is not None else {}),
            "options": {
                "temperature": temperature,
                **({"num_ctx": context_window} if context_window is not None else {}),
                **({"num_predict": max_output_tokens} if max_output_tokens is not None else {}),
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=request_payload,
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:1000]
            raise OllamaError(
                f"Ollama returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(f"Ollama request failed: {exc}") from exc

        message = payload.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise OllamaError("Ollama response did not contain message.content")

        parsed: Any | None = None
        parse_error: str | None = None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

        metadata = {
            key: payload[key]
            for key in (
                "created_at",
                "done",
                "done_reason",
                "total_duration",
                "load_duration",
                "prompt_eval_count",
                "prompt_eval_cached_count",
                "prompt_eval_duration",
                "eval_count",
                "eval_duration",
            )
            if key in payload
        }
        return OllamaReply(
            model=str(payload.get("model", model)),
            content=content,
            parsed=parsed,
            parse_error=parse_error,
            metadata=metadata,
        )
