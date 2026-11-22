"""Application configuration loaded from environment variables / .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SST_", extra="ignore", case_sensitive=False
    )

    app_name: str = "Smart Survey Tool"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False

    data_dir: Path = BASE_DIR / "data"
    database_url: str = ""
    sql_echo: bool = False

    admin_api_key: str = "dev-insecure-key"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    public_base_url: str = "http://localhost:8000"

    nlp_backend: Literal["classic", "transformer"] = "classic"
    nlp_max_topics: int = 5
    nlp_summary_sentences: int = 3
    nlp_cache_size: int = 256

    log_level: str = "INFO"
    log_json: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("database_url", mode="after")
    @classmethod
    def _default_database_url(cls, value: str) -> str:
        if value:
            return value
        return f"sqlite:///{(BASE_DIR / 'data' / 'smart_survey.db').as_posix()}"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
