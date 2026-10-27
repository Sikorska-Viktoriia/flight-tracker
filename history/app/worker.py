import asyncio
import logging

from history.app.config.settings import get_settings
from history.app.core.logging_config import configure_logging
from history.app.db.pool import create_pool
from history.app.factories.queue_factory import create_queue
from history.app.repositories.snapshot_repository import SnapshotRepository
from history.app.services.collector import poll_fetcher

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    pool = await create_pool(settings)
    try:
        repository = SnapshotRepository(pool)
        last_saved_at = await repository.latest_collected_at()
        queue = await create_queue(settings, pool)
        if settings.uses_pgmq:
            logger.info("collector started; using pgmq task queue")
        elif settings.uses_postgres_queue:
            logger.info("collector started; using PostgreSQL task queue")
        else:
            logger.info("collector started; using RabbitMQ task queue")
        try:
            await poll_fetcher(queue, repository, settings, last_saved_at)
        finally:
            await queue.aclose()
    finally:
        await pool.close()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(run_worker())
