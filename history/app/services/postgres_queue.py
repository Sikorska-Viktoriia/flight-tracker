import asyncio
import json
import uuid

import asyncpg

from history.app.interfaces.message_queue import MessageQueue
from history.app.schemas.snapshot import FetcherSnapshot
from history.app.services.queue_errors import FetcherRequestError
from history.app.services.rabbitmq_queue import (
    TASK_QUEUE_MESSAGE_TTL_MS,
    parse_fetcher_response,
)


class PostgresQueue(MessageQueue):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def request_snapshot(self, timeout_sec: float) -> FetcherSnapshot:
        correlation_id = str(uuid.uuid4())
        await self.pool.execute(
            """
            INSERT INTO fetcher_tasks (correlation_id, payload, expires_at)
            VALUES ($1, $2::jsonb, NOW() + $3::int * INTERVAL '1 second')
            """,
            correlation_id,
            {"action": "fetch_snapshot"},
            TASK_QUEUE_MESSAGE_TTL_MS // 1000,
        )
        try:
            response = await asyncio.wait_for(
                self._wait_for_response(correlation_id),
                timeout=timeout_sec,
            )
        finally:
            await self.pool.execute(
                "DELETE FROM fetcher_tasks WHERE correlation_id = $1",
                correlation_id,
            )

        try:
            payload = json.loads(response)
            if not isinstance(payload, dict):
                raise ValueError("Fetcher response must be a JSON object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise FetcherRequestError(f"invalid Fetcher response: {error}") from error
        return parse_fetcher_response(payload)

    async def _wait_for_response(self, correlation_id: str) -> str:
        connection = await self.pool.acquire()
        notified = asyncio.Event()

        def on_response(
            _connection: asyncpg.Connection,
            _pid: int,
            _channel: str,
            payload: str,
        ) -> None:
            if payload == correlation_id:
                notified.set()

        try:
            await connection.add_listener("fetcher_responses", on_response)
            while True:
                notified.clear()
                response = await connection.fetchval(
                    """
                    SELECT response::text
                    FROM fetcher_tasks
                    WHERE correlation_id = $1 AND expires_at > NOW()
                    """,
                    correlation_id,
                )
                if response is not None:
                    return response
                await notified.wait()
        finally:
            await connection.remove_listener("fetcher_responses", on_response)
            await self.pool.release(connection)

    async def aclose(self) -> None:
        return None
