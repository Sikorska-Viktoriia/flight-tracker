import logging
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from history.app.api.dependencies import get_snapshot_service
from history.app.schemas.snapshot import (
    HeatmapPoint,
    LatestSnapshot,
    SnapshotHistoryItem,
    TimelineSnapshot,
)
from history.app.services.snapshot_service import (
    SnapshotNotFoundError,
    SnapshotService,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["flight snapshots"])


@router.get(
    "/history",
    response_model=list[SnapshotHistoryItem],
    summary="List recent flight snapshots",
)
async def history(
    service: Annotated[SnapshotService, Depends(get_snapshot_service)],
    limit: Annotated[int, Query(ge=1, le=500)] = 25,
) -> list[SnapshotHistoryItem]:
    try:
        return await service.history(limit)
    except asyncpg.PostgresError as error:
        logger.exception("could not read flight history")
        raise HTTPException(status_code=503, detail="flight history is unavailable") from error


@router.get(
    "/latest",
    response_model=LatestSnapshot,
    summary="Get the latest flight snapshot and aircraft positions",
)
async def latest(
    service: Annotated[SnapshotService, Depends(get_snapshot_service)],
) -> LatestSnapshot:
    try:
        return await service.latest()
    except SnapshotNotFoundError as error:
        raise HTTPException(status_code=404, detail="no flight snapshots collected yet") from error
    except asyncpg.PostgresError as error:
        logger.exception("could not read latest flight snapshot")
        raise HTTPException(
            status_code=503, detail="latest flight snapshot is unavailable"
        ) from error


@router.get(
    "/timeline",
    response_model=list[TimelineSnapshot],
    summary="List aircraft snapshots for recent playback",
)
async def timeline(
    service: Annotated[SnapshotService, Depends(get_snapshot_service)],
    minutes: Annotated[int, Query(ge=1, le=120)] = 60,
    limit: Annotated[int, Query(ge=1, le=500)] = 120,
) -> list[TimelineSnapshot]:
    try:
        return await service.timeline(minutes, limit)
    except asyncpg.PostgresError as error:
        logger.exception("could not read flight playback timeline")
        raise HTTPException(
            status_code=503, detail="flight playback timeline is unavailable"
        ) from error


@router.get(
    "/heatmap",
    response_model=list[HeatmapPoint],
    summary="Get aggregated aircraft traffic density",
)
async def heatmap(
    service: Annotated[SnapshotService, Depends(get_snapshot_service)],
    hours: Annotated[int, Query(ge=1, le=24)] = 1,
) -> list[HeatmapPoint]:
    if hours not in {1, 24}:
        raise HTTPException(status_code=422, detail="hours must be 1 or 24")
    try:
        return await service.heatmap(hours)
    except asyncpg.PostgresError as error:
        logger.exception("could not read aircraft traffic density")
        raise HTTPException(
            status_code=503, detail="aircraft traffic density is unavailable"
        ) from error
