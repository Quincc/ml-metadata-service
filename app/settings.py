from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/metadata_db",
        alias="DATABASE_URL",
    )
    environment: str = Field(default="dev", alias="APP_ENV")
    db_wait_max_attempts: int = Field(default=10, alias="DB_WAIT_MAX_ATTEMPTS")
    db_wait_delay_seconds: int = Field(default=2, alias="DB_WAIT_DELAY_SECONDS")

    @property
    def is_dev(self) -> bool:
        return self.environment.lower() == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
