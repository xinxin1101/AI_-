from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Guilin Tourism AI Assistant"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    cors_origins: str = "*"

    llm_mock_mode: bool = True
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_temperature: float = Field(default=0.3, ge=0, le=2)
    llm_max_tokens: int = Field(default=800, gt=0)

    session_max_messages: int = Field(default=20, ge=2, le=200)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
