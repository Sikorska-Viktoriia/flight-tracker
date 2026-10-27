import pytest
from aio_pika.message import encode_expiration

from history.app.core.config import Settings
from history.app.interfaces.message_queue import MessageQueue
from history.app.schemas.snapshot import FetcherSnapshot
from history.app.services.collector import (
    FetcherRequestError,
    collect_once,
)
from history.app.services.postgres_queue import PostgresQueue
from history.app.services.rabbitmq_queue import TASK_QUEUE_MESSAGE_TTL_MS


def test_queue_message_expiration_matches_queue_ttl() -> None:
    expiration_sec = TASK_QUEUE_MESSAGE_TTL_MS / 1000

    assert encode_expiration(expiration_sec) == str(TASK_QUEUE_MESSAGE_TTL_MS)


@pytest.mark.asyncio
async def test_postgres_queue_client_publishes_and_reads_rpc_response() -> None:
    class FakeConnection:
        async def add_listener(self, channel: str, callback: object) -> None:
            assert channel == "fetcher_responses"

        async def fetchval(self, query: str, correlation_id: str) -> str:
            assert query.lstrip().startswith("SELECT response")
            assert correlation_id == pool.inserted[0]
            return (
                '{"status":200,"snapshot":{"collected_at":"2026-10-01T12:00:00Z",'
                '"total_airborne":1,"average_speed_mps":220.5,"max_altitude_m":10000,'
                '"top_flight_callsign":"FLT123","aircraft":[]}}'
            )

        async def remove_listener(self, channel: str, callback: object) -> None:
            assert channel == "fetcher_responses"

    class FakePool:
        def __init__(self) -> None:
            self.inserted: tuple[object, ...] | None = None
            self.deleted = False
            self.connection = FakeConnection()

        async def execute(self, query: str, *args: object) -> str:
            if query.lstrip().startswith("INSERT INTO fetcher_tasks"):
                self.inserted = args
            elif query.lstrip().startswith("DELETE FROM fetcher_tasks"):
                self.deleted = True
            else:
                raise AssertionError(f"unexpected query: {query}")
            return "OK"

        async def acquire(self) -> FakeConnection:
            return self.connection

        async def release(self, connection: FakeConnection) -> None:
            assert connection is self.connection

    pool = FakePool()
    snapshot = await PostgresQueue(pool).request_snapshot(1)

    assert pool.inserted is not None
    assert pool.inserted[2] == TASK_QUEUE_MESSAGE_TTL_MS // 1000
    assert pool.deleted
    assert snapshot.total_airborne == 1


class InMemoryRepository:
    def __init__(self) -> None:
        self.snapshots: list[FetcherSnapshot] = []

    async def save(self, snapshot: FetcherSnapshot) -> None:
        self.snapshots.append(snapshot)


@pytest.mark.asyncio
async def test_collect_once_saves_a_valid_snapshot_and_skips_duplicates() -> None:
    class FakeQueueClient(MessageQueue):
        async def request_snapshot(self, _timeout_sec: float) -> FetcherSnapshot:
            return FetcherSnapshot(
                collected_at="2026-10-01T12:00:00Z",
                total_airborne=1,
                average_speed_mps=220.5,
                max_altitude_m=10000,
                top_flight_callsign="FLT123",
                aircraft=[],
            )

        async def aclose(self) -> None:
            return None

    repository = InMemoryRepository()
    settings = Settings(_env_file=None)
    client = FakeQueueClient()

    last_saved_at, delay = await collect_once(client, repository, settings, None)
    duplicate_timestamp, _ = await collect_once(
        client, repository, settings, last_saved_at
    )

    assert last_saved_at is not None
    assert duplicate_timestamp == last_saved_at
    assert len(repository.snapshots) == 1
    assert repository.snapshots[0].total_airborne == 1
    assert delay == settings.poll_interval_sec


@pytest.mark.asyncio
async def test_collect_once_respects_fetcher_retry_after() -> None:
    class FailingQueueClient(MessageQueue):
        async def request_snapshot(self, _timeout_sec: float) -> FetcherSnapshot:
            raise FetcherRequestError("upstream is rate limited", retry_after=900)

        async def aclose(self) -> None:
            return None

    settings = Settings(_env_file=None)
    repository = InMemoryRepository()

    timestamp, delay = await collect_once(
        FailingQueueClient(), repository, settings, None
    )

    assert timestamp is None
    assert delay == 900
    assert repository.snapshots == []
