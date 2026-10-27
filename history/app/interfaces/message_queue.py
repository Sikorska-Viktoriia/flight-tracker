from typing import Protocol

from history.app.schemas.snapshot import FetcherSnapshot


class MessageQueue(Protocol):
    """Request/reply queue contract used by the flight snapshot collector."""

    async def request_snapshot(self, timeout_sec: float) -> FetcherSnapshot: ...

    async def aclose(self) -> None: ...
