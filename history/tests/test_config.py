import pytest
from pydantic import ValidationError

from history.app.core.config import Settings


def test_settings_accept_valid_poll_and_pool_configuration() -> None:
    settings = Settings(
        _env_file=None,
        poll_interval_sec=60,
        db_pool_min_size=2,
        db_pool_max_size=4,
    )

    assert settings.poll_interval_sec == 60
    assert settings.amqp_url == "amqp://guest:guest@localhost:5672/"
    assert settings.redis_url == "redis://localhost:6379/0"


def test_settings_reject_non_positive_poll_interval() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, poll_interval_sec=0)


def test_settings_reject_minimum_pool_larger_than_maximum() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        Settings(_env_file=None, db_pool_min_size=3, db_pool_max_size=2)


def test_settings_validate_runtime_storage_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "postgres_native")

    settings = Settings(_env_file=None)

    assert settings.storage_backend == "postgres_native"
    assert settings.uses_postgres_queue
    assert settings.uses_postgres_cache


def test_settings_require_database_url_when_postgres_backend_is_enabled() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL is required"):
        Settings(_env_file=None, storage_backend="postgres_native", database_url=" ")
