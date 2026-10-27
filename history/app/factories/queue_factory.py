import asyncpg

from history.app.config.settings import Settings
from history.app.interfaces.message_queue import MessageQueue
from history.app.services.pgmq_queue import PgmqQueue
from history.app.services.postgres_queue import PostgresQueue
from history.app.services.rabbitmq_queue import RabbitMQQueue


async def create_queue(settings: Settings, pool: asyncpg.Pool) -> MessageQueue:
    if settings.uses_pgmq:
        return PgmqQueue(pool)
    if settings.uses_postgres_queue:
        return PostgresQueue(pool)
    return await RabbitMQQueue.create(settings.amqp_url)
