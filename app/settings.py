import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str:
    """Pick `.env.{APP_ENV}` if present, otherwise fall back to `.env`."""
    env = os.getenv("APP_ENV", "dev").lower()
    candidate = f".env.{env}"
    return candidate if os.path.exists(candidate) else ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Resolution order: per-env file (.env.dev / .env.prod), then plain .env,
    then process environment variables (which take precedence).
    """

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/metadata_db",
        alias="DATABASE_URL",
    )
    environment: str = Field(default="dev", alias="APP_ENV")
    db_wait_max_attempts: int = Field(default=10, alias="DB_WAIT_MAX_ATTEMPTS")
    db_wait_delay_seconds: int = Field(default=2, alias="DB_WAIT_DELAY_SECONDS")

    # Tunable knobs that differ between dev and prod.
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    sql_echo: bool = Field(default=False, alias="SQL_ECHO")
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")

    @property
    def is_dev(self) -> bool:
        return self.environment.lower() == "dev"

    @property
    def is_prod(self) -> bool:
        return self.environment.lower() in {"prod", "production"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
