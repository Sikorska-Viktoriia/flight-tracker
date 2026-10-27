import asyncio
import logging
from datetime import datetime, timezone
from typing import Protocol

import aio_pika
import asyncpg
from pydantic import ValidationError

from history.app.config.settings import Settings
from history.app.interfaces.message_queue import MessageQueue
from history.app.schemas.snapshot import FetcherSnapshot
from history.app.services.queue_errors import FetcherRequestError

logger = logging.getLogger(__name__)


class SnapshotWriter(Protocol):
    async def save(self, snapshot: FetcherSnapshot) -> None: ...


async def poll_fetcher(
    client: MessageQueue,
    repository: SnapshotWriter,
    settings: Settings,
    last_saved_at: datetime | None,
) -> None:
    while True:
        last_saved_at, next_poll_interval = await collect_once(
            client, repository, settings, last_saved_at
        )
        await asyncio.sleep(next_poll_interval)


async def collect_once(
    client: MessageQueue,
    repository: SnapshotWriter,
    settings: Settings,
    last_saved_at: datetime | None,
) -> tuple[datetime | None, float]:
    try:
        snapshot = await client.request_snapshot(settings.fetcher_timeout_sec)
        collected_at = snapshot.collected_at
        if collected_at.tzinfo is None:
            collected_at = collected_at.replace(tzinfo=timezone.utc)

        if last_saved_at is not None and collected_at <= last_saved_at:
            logger.info("no new flight snapshot; keeping existing history")
            return last_saved_at, settings.poll_interval_sec

        snapshot = snapshot.model_copy(update={"collected_at": collected_at})
        await repository.save(snapshot)
        logger.info(
            "saved flight snapshot: %s aircraft at %s",
            snapshot.total_airborne,
            collected_at.isoformat(),
        )
        return collected_at, settings.poll_interval_sec
    except FetcherRequestError as error:
        next_poll_interval = max(settings.poll_interval_sec, error.retry_after)
        logger.warning(
            "Fetcher request failed; retrying in %.0f seconds: %s",
            next_poll_interval,
            error,
        )
        return last_saved_at, next_poll_interval
    except (
        asyncio.TimeoutError,
        aio_pika.AMQPException,
        ValueError,
        ValidationError,
        asyncpg.PostgresError,
        OSError,
    ):
        logger.exception("could not fetch or save a flight snapshot")
        return last_saved_at, settings.poll_interval_sec
    except Exception:
        logger.exception("unexpected failure during flight snapshot collection")
        return last_saved_at, settings.poll_interval_sec