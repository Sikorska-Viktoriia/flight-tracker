import pytest

from history.app.config.settings import Settings
from history.app.factories.cache_factory import create_cache
from history.app.factories.queue_factory import create_queue
from history.app.interfaces.message_queue import MessageQueue
from history.app.services.pgmq_queue import PgmqQueue
from history.app.services.postgres_cache import PostgresCache
from history.app.services.postgres_queue import PostgresQueue
from history.app.services.rabbitmq_queue import RabbitMQQueue
from history.app.services.redis_cache import RedisCache


@pytest.mark.asyncio
async def test_queue_factory_selects_postgres_for_native_backend() -> None:
    pool = object()
    queue = await create_queue(Settings(_env_file=None, storage_backend="postgres_native"), pool)

    assert isinstance(queue, PostgresQueue)
    assert queue.pool is pool


@pytest.mark.asyncio
async def test_queue_factory_selects_pgmq_for_extension_backend() -> None:
    pool = object()
    queue = await create_queue(
        Settings(_env_file=None, storage_backend="postgres_extensions"),
        pool,
    )

    assert isinstance(queue, PgmqQueue)
    assert queue.pool is pool


@pytest.mark.asyncio
async def test_queue_factory_selects_rabbitmq_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeQueue(MessageQueue):
        async def request_snapshot(self, timeout_sec: float):
            raise AssertionError("not called")

        async def aclose(self) -> None:
            return None

    async def create_rabbitmq(amqp_url: str) -> FakeQueue:
        assert amqp_url == "amqp://guest:guest@localhost:5672/"
        return FakeQueue()

    monkeypatch.setattr(RabbitMQQueue, "create", staticmethod(create_rabbitmq))

    queue = await create_queue(Settings(_env_file=None), object())

    assert isinstance(queue, FakeQueue)


def test_cache_factory_selects_postgres_for_native_backend() -> None:
    pool = object()
    cache = create_cache(Settings(_env_file=None, storage_backend="postgres_native"), pool)

    assert isinstance(cache, PostgresCache)
    assert cache.pool is pool


def test_cache_factory_selects_redis_by_default() -> None:
    cache = create_cache(Settings(_env_file=None), object())

    assert isinstance(cache, RedisCache)
