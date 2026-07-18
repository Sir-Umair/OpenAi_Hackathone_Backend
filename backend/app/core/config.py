"""Typed configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import API_V1_PREFIX


class Settings(BaseSettings):
    """Application settings with production safety checks."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", enable_decoding=False
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    app_name: str = "O2N Engine API"
    api_v1_prefix: str = API_V1_PREFIX
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=list)

    mongodb_uri: str | None = None
    mongodb_database: str = "o2n_engine"
    mongodb_connect_timeout_ms: int = Field(default=5000, ge=100, le=60000)

    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=90)

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    embedding_provider: Literal["sentence_transformers", "openai_compatible"] = "sentence_transformers"
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_path: str = "./data/chroma"
    semgrep_binary: str = "semgrep"
    max_upload_size_bytes: int = Field(default=524288000, ge=1048576)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Accept either JSON arrays or a comma-separated environment value."""
        if isinstance(value, list):
            return value
        return [origin.strip() for origin in value.strip("[]").replace('"', "").split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.environment == "production":
            if not self.mongodb_uri or not self.jwt_secret_key:
                raise ValueError("MONGODB_URI and JWT_SECRET_KEY are required in production.")
            if len(self.jwt_secret_key.get_secret_value()) < 32:
                raise ValueError("JWT_SECRET_KEY must contain at least 32 characters.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the singleton immutable settings instance."""
    return Settings()
