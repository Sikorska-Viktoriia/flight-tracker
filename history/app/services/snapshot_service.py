from datetime import datetime, timedelta, timezone

from history.app.repositories.snapshot_repository import SnapshotRepository
from history.app.schemas.snapshot import (
    HeatmapPoint,
    LatestSnapshot,
    SnapshotHistoryItem,
    TimelineSnapshot,
)


class SnapshotNotFoundError(Exception):
    """Raised when no flight snapshot has been collected yet."""


class SnapshotService:
    def __init__(self, repository: SnapshotRepository) -> None:
        self._repository = repository

    async def history(self, limit: int) -> list[SnapshotHistoryItem]:
        return await self._repository.list_recent(limit)

    async def timeline(self, minutes: int, limit: int) -> list[TimelineSnapshot]:
        collected_after = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return await self._repository.list_timeline(collected_after, limit)

    async def heatmap(self, hours: int) -> list[HeatmapPoint]:
        collected_after = datetime.now(timezone.utc) - timedelta(hours=hours)
        return await self._repository.heatmap(collected_after)

    async def latest(self) -> LatestSnapshot:
        snapshot = await self._repository.get_latest()
        if snapshot is None:
            raise SnapshotNotFoundError
        return snapshot
