import os
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_provider: str = "gemini"
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY", "gemini_api_key"),
    )
    gemini_model: str = "gemini-flash-lite-latest"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    serper_api_key: str = ""

    request_timeout_seconds: float = 15.0
    llm_timeout_seconds: float = 45.0
    cache_ttl_seconds: int = 3600
    max_content_chars: int = 12000
    port: int = 4000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("gemini_api_key", mode="before")
    @classmethod
    def clean_key(cls, val: object) -> str:
        raw = str(val or "").strip().strip("\"'")
        if raw.startswith("GEMINI_API_KEY="):
            raw = raw.split("=", 1)[1].strip()
        return raw


def get_settings() -> Settings:
    settings = Settings()
    if not settings.gemini_api_key:
        env_val = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        if env_val.strip():
            settings.gemini_api_key = env_val.strip()
    return settings
