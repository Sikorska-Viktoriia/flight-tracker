from fastapi import Request

from history.app.repositories.snapshot_repository import SnapshotRepository
from history.app.services.snapshot_service import SnapshotService


def get_snapshot_service(request: Request) -> SnapshotService:
    return SnapshotService(SnapshotRepository(request.app.state.pool))
