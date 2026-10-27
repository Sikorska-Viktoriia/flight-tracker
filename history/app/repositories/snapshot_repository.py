from datetime import datetime

import asyncpg

from history.app.schemas.snapshot import (
    FetcherSnapshot,
    HeatmapPoint,
    LatestSnapshot,
    SnapshotHistoryItem,
    TimelineSnapshot,
)

INSERT_SNAPSHOT_QUERY = """
INSERT INTO flight_snapshots (
    collected_at,
    total_airborne,
    average_speed_mps,
    max_altitude_m,
    top_flight_callsign,
    aircraft
) VALUES ($1, $2, $3, $4, $5, $6)
"""

SELECT_HISTORY_QUERY = """
SELECT id, collected_at, total_airborne, average_speed_mps,
       COALESCE((
           SELECT AVG((position->>'altitude_m')::double precision)
           FROM jsonb_array_elements(aircraft) AS aircraft_positions(position)
       ), 0) AS average_altitude_m,
       max_altitude_m, top_flight_callsign, saved_at
FROM flight_snapshots
ORDER BY collected_at DESC, id DESC
LIMIT $1
"""

SELECT_TIMELINE_QUERY = """
WITH recent AS (
    SELECT id, collected_at, total_airborne, average_speed_mps,
           COALESCE((
               SELECT AVG((position->>'altitude_m')::double precision)
               FROM jsonb_array_elements(aircraft) AS aircraft_positions(position)
           ), 0) AS average_altitude_m,
           max_altitude_m, top_flight_callsign, aircraft, saved_at
    FROM flight_snapshots
    WHERE collected_at >= $1
    ORDER BY collected_at DESC, id DESC
    LIMIT $2
)
SELECT *
FROM recent
ORDER BY collected_at ASC, id ASC
"""

SELECT_LATEST_QUERY = """
SELECT id, collected_at, total_airborne, average_speed_mps,
       COALESCE((
           SELECT AVG((position->>'altitude_m')::double precision)
           FROM jsonb_array_elements(aircraft) AS aircraft_positions(position)
       ), 0) AS average_altitude_m,
       max_altitude_m, top_flight_callsign, aircraft, saved_at
FROM flight_snapshots
ORDER BY collected_at DESC, id DESC
LIMIT 1
"""

SELECT_HEATMAP_QUERY = """
WITH traffic_cells AS (
    SELECT ROUND((position->>'latitude')::numeric, 1) AS latitude,
           ROUND((position->>'longitude')::numeric, 1) AS longitude,
           COUNT(*) AS observations
    FROM flight_snapshots AS snapshot
    CROSS JOIN LATERAL jsonb_array_elements(snapshot.aircraft) AS aircraft_positions(position)
    WHERE snapshot.collected_at >= $1
    GROUP BY latitude, longitude
)
SELECT latitude, longitude,
       observations::double precision / MAX(observations) OVER () AS intensity
FROM traffic_cells
ORDER BY observations DESC
"""


class SnapshotRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def latest_collected_at(self) -> datetime | None:
        async with self._pool.acquire() as connection:
            return await connection.fetchval("SELECT MAX(collected_at) FROM flight_snapshots")

    async def save(self, snapshot: FetcherSnapshot) -> None:
        aircraft_payload = [aircraft.model_dump(mode="json") for aircraft in snapshot.aircraft]
        async with self._pool.acquire() as connection:
            await connection.execute(
                INSERT_SNAPSHOT_QUERY,
                snapshot.collected_at,
                snapshot.total_airborne,
                snapshot.average_speed_mps,
                snapshot.max_altitude_m,
                snapshot.top_flight_callsign,
                aircraft_payload,
            )

    async def list_recent(self, limit: int) -> list[SnapshotHistoryItem]:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(SELECT_HISTORY_QUERY, limit)
        return [SnapshotHistoryItem.model_validate(dict(row)) for row in rows]

    async def list_timeline(
        self,
        collected_after: datetime,
        limit: int,
    ) -> list[TimelineSnapshot]:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(SELECT_TIMELINE_QUERY, collected_after, limit)
        return [TimelineSnapshot.model_validate(dict(row)) for row in rows]

    async def heatmap(self, collected_after: datetime) -> list[HeatmapPoint]:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(SELECT_HEATMAP_QUERY, collected_after)
            return [HeatmapPoint.model_validate(dict(row)) for row in rows]

    async def get_latest(self) -> LatestSnapshot | None:
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(SELECT_LATEST_QUERY)
        if row is None:
            return None
        return LatestSnapshot.model_validate(dict(row))