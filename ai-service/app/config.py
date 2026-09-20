from functools import lru_cache

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the local test service.

    These defaults are intentionally local-only. Authentication, production
    service discovery, and secret management belong in a later integration.
    """

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_seconds: float = 300.0
    ollama_context_window: int = 16384
    ollama_max_output_tokens: int = 2048
    ollama_keep_alive: str = "10m"
    prompt_mode: Literal["compact", "full"] = "compact"
    botfight_server_root: str = r"C:\dev\botfight\server"
    simulator_timeout_seconds: float = 180.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
