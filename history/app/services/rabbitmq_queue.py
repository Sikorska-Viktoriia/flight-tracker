import asyncio
import json
import uuid

import aio_pika

from history.app.interfaces.message_queue import MessageQueue
from history.app.schemas.snapshot import FetcherSnapshot
from history.app.services.queue_errors import FetcherRequestError

TASK_QUEUE = "flight-tracker.fetcher.tasks"
TASK_QUEUE_MESSAGE_TTL_MS = 60_000


class RabbitMQQueue(MessageQueue):
    def __init__(
        self,
        connection: aio_pika.abc.AbstractRobustConnection,
        channel: aio_pika.abc.AbstractChannel,
        task_queue: aio_pika.abc.AbstractQueue,
        reply_queue: aio_pika.abc.AbstractQueue,
    ) -> None:
        self.connection = connection
        self.channel = channel
        self.task_queue = task_queue
        self.reply_queue = reply_queue
        self.pending: dict[str, asyncio.Future[dict[str, object]]] = {}

    @classmethod
    async def create(cls, amqp_url: str) -> "RabbitMQQueue":
        connection = await aio_pika.connect_robust(amqp_url)
        try:
            channel = await connection.channel()
            task_queue = await channel.declare_queue(
                TASK_QUEUE,
                durable=True,
                arguments={"x-message-ttl": TASK_QUEUE_MESSAGE_TTL_MS},
            )
            reply_queue = await channel.declare_queue(exclusive=True, auto_delete=True)
            queue = cls(connection, channel, task_queue, reply_queue)
            await reply_queue.consume(queue._handle_response, no_ack=True)
            return queue
        except Exception:
            await connection.close()
            raise

    async def _handle_response(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        future = self.pending.get(message.correlation_id or "")
        if future is None or future.done():
            return
        try:
            payload = json.loads(message.body)
            if not isinstance(payload, dict):
                raise ValueError("Fetcher response must be a JSON object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            future.set_exception(FetcherRequestError(f"invalid Fetcher response: {error}"))
            return
        future.set_result(payload)

    async def request_snapshot(self, timeout_sec: float) -> FetcherSnapshot:
        correlation_id = str(uuid.uuid4())
        future: asyncio.Future[dict[str, object]] = asyncio.get_running_loop().create_future()
        self.pending[correlation_id] = future
        try:
            await self.channel.default_exchange.publish(
                aio_pika.Message(
                    body=b'{"action":"fetch_snapshot"}',
                    content_type="application/json",
                    correlation_id=correlation_id,
                    reply_to=self.reply_queue.name,
                    expiration=TASK_QUEUE_MESSAGE_TTL_MS / 1000,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=self.task_queue.name,
            )
            response = await asyncio.wait_for(future, timeout=timeout_sec)
        finally:
            self.pending.pop(correlation_id, None)
        return parse_fetcher_response(response)

    async def aclose(self) -> None:
        await self.connection.close()


def parse_fetcher_response(response: dict[str, object]) -> FetcherSnapshot:
    status = response.get("status")
    if status != 200:
        message = response.get("error", "Fetcher returned an unsuccessful response")
        retry_after = response.get("retry_after", 0)
        if not isinstance(message, str) or not isinstance(retry_after, int | float):
            raise FetcherRequestError("Fetcher returned an invalid error response")
        raise FetcherRequestError(message, max(0, float(retry_after)))

    snapshot = response.get("snapshot")
    if not isinstance(snapshot, dict):
        raise FetcherRequestError("Fetcher response does not contain a snapshot")
    return FetcherSnapshot.model_validate(snapshot)
