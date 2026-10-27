from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://localhost:5432/flightdb"
    amqp_url: str = "amqp://guest:guest@localhost:5672/"
    redis_url: str = "redis://localhost:6379/0"
    storage_backend: Literal["standalone", "postgres_native", "postgres_extensions"] = "standalone"
    poll_interval_sec: float = Field(default=300, gt=0)
    fetcher_timeout_sec: float = Field(default=30, gt=0)
    session_ttl_sec: int = Field(default=2592000, gt=0)
    db_pool_min_size: int = Field(default=1, ge=1)
    db_pool_max_size: int = Field(default=5, ge=1)
    serve_frontend: bool = False
    frontend_directory: Path = PROJECT_ROOT / "frontend"

    @model_validator(mode="after")
    def validate_backend_configuration(self) -> "Settings":
        if self.db_pool_min_size > self.db_pool_max_size:
            raise ValueError("DB_POOL_MIN_SIZE cannot exceed DB_POOL_MAX_SIZE")
        if (self.uses_postgres_queue or self.uses_postgres_cache) and not self.database_url.strip():
            raise ValueError("DATABASE_URL is required when a PostgreSQL backend is enabled")
        return self

    @property
    def selected_storage_backend(self) -> str:
        return self.storage_backend

    @property
    def uses_postgres_queue(self) -> bool:
        return self.storage_backend != "standalone"

    @property
    def uses_postgres_cache(self) -> bool:
        return self.storage_backend != "standalone"

    @property
    def uses_pgmq(self) -> bool:
        return self.selected_storage_backend == "postgres_extensions"

@lru_cache
def get_settings() -> Settings:
    return Settings()
