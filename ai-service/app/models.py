from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GenerateRequest(BaseModel):
    """Local test request; the real Bot Fight context is not defined yet."""

    model_config = ConfigDict(extra="forbid")

    context: dict[str, Any] = Field(
        description="Match/round context supplied to the model. The shape is provisional."
    )
    candidate_count: int = Field(default=10, ge=1, le=20)
    instructions: str | None = Field(default=None, max_length=8000)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class GenerateResponse(BaseModel):
    model: str
    prompt_version: str
    candidate_count: int
    raw_response: str
    parsed_response: Any | None
    parse_error: str | None
    ollama_metadata: dict[str, Any]
