from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from history.app.api.dependencies import get_snapshot_service
from history.app.core.config import Settings
from history.app.main import create_app
from history.app.schemas.snapshot import (
    AircraftPosition,
    HeatmapPoint,
    LatestSnapshot,
    SnapshotHistoryItem,
    TimelineSnapshot,
)
from history.app.services.snapshot_service import SnapshotNotFoundError

COLLECTED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class FakePool:
    def acquire(self) -> "FakeConnection":
        return FakeConnection()

    async def close(self) -> None:
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        assert ex > 0
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class FakeConnection:
    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, *args: object) -> None:
        _ = args
        return None

    async def fetchval(self, query: str) -> int:
        assert query == "SELECT 1"
        return 1


class FakeSnapshotService:
    async def history(self, limit: int) -> list[SnapshotHistoryItem]:
        assert 1 <= limit <= 500
        return [
            SnapshotHistoryItem(
                id=1,
                collected_at=COLLECTED_AT,
                total_airborne=1,
                average_speed_mps=220.5,
                average_altitude_m=9500,
                max_altitude_m=10000,
                top_flight_callsign="FLT123",
                saved_at=COLLECTED_AT,
            )
        ]

    async def latest(self) -> LatestSnapshot:
        return LatestSnapshot(
            id=1,
            collected_at=COLLECTED_AT,
            total_airborne=1,
            average_speed_mps=220.5,
            average_altitude_m=9500,
            max_altitude_m=10000,
            top_flight_callsign="FLT123",
            saved_at=COLLECTED_AT,
            aircraft=[
                AircraftPosition(
                    icao24="abc123",
                    callsign="FLT123",
                    country="Poland",
                    longitude=19.0,
                    latitude=51.75,
                    altitude_m=-15.24,
                    speed_mps=220.5,
                    heading_deg=90,
                )
            ],
        )

    async def timeline(self, minutes: int, limit: int) -> list[TimelineSnapshot]:
        assert 1 <= minutes <= 120
        assert 1 <= limit <= 500
        return [
            TimelineSnapshot(
                id=1,
                collected_at=COLLECTED_AT,
                total_airborne=1,
                average_speed_mps=220.5,
                average_altitude_m=9500,
                max_altitude_m=10000,
                top_flight_callsign="FLT123",
                saved_at=COLLECTED_AT,
                aircraft=[
                    AircraftPosition(
                        icao24="abc123",
                        callsign="FLT123",
                        country="Poland",
                        longitude=19.0,
                        latitude=51.75,
                        altitude_m=9500,
                        speed_mps=220.5,
                        heading_deg=90,
                        aircraft_type="A320",
                        category="A3",
                        squawk="1200",
                        vertical_rate_mps=0.0,
                    )
                ],
            )
        ]

    async def heatmap(self, hours: int) -> list[HeatmapPoint]:
        assert hours in {1, 24}
        return [HeatmapPoint(latitude=51.8, longitude=19.0, intensity=1.0)]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    fake_redis = FakeRedis()

    async def create_fake_pool(settings: Settings) -> FakePool:
        assert settings.db_pool_min_size <= settings.db_pool_max_size
        return FakePool()

    def create_fake_cache(_settings: Settings, _pool: FakePool) -> FakeRedis:
        return fake_redis

    monkeypatch.setattr("history.app.main.create_pool", create_fake_pool)
    monkeypatch.setattr("history.app.main.create_cache", create_fake_cache)
    app = create_app(
        Settings(
            _env_file=None,
            serve_frontend=True,
            frontend_directory=Path(__file__).resolve().parents[2] / "frontend",
        )
    )
    app.dependency_overrides[get_snapshot_service] = FakeSnapshotService

    @asynccontextmanager
    async def test_lifespan(_app: object):
        _app.state.pool = await create_fake_pool(app.state.settings)
        _app.state.session_store = fake_redis
        try:
            yield
        finally:
            await _app.state.pool.close()

    app.router.lifespan_context = test_lifespan
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoints_are_available(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ok"}
    assert client.get("/health").json() == {"status": "ok"}


def test_local_frontend_is_served_in_english(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert '<html lang="en">' in response.text
    assert '<link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">' in response.text
    assert '<link rel="stylesheet" href="/assets/css/app.css">' in response.text
    assert '<script defer src="/assets/js/app.js"></script>' in response.text
    assert "<style>" not in response.text
    assert "<script>" not in response.text


def test_local_frontend_assets_are_served(client: TestClient) -> None:
    favicon_response = client.get("/assets/favicon.svg")
    css_response = client.get("/assets/css/app.css")
    js_response = client.get("/assets/js/app.js")

    assert favicon_response.status_code == 200
    assert css_response.status_code == 200
    assert ".metrics" in css_response.text
    assert js_response.status_code == 200
    assert 'fetch("/api/history?limit=500"' in js_response.text


def test_history_returns_validated_snapshots(client: TestClient) -> None:
    response = client.get("/api/history?limit=25")

    assert response.status_code == 200
    assert response.json()[0]["top_flight_callsign"] == "FLT123"


def test_history_rejects_out_of_range_limit(client: TestClient) -> None:
    assert client.get("/api/history?limit=0").status_code == 422
    assert client.get("/api/history?limit=501").status_code == 422


def test_timeline_returns_aircraft_positions_and_telemetry(client: TestClient) -> None:
    response = client.get("/api/timeline?minutes=60&limit=120")

    assert response.status_code == 200
    assert response.json()[0]["aircraft"][0]["aircraft_type"] == "A320"
    assert response.json()[0]["aircraft"][0]["vertical_rate_mps"] == 0.0


def test_timeline_rejects_out_of_range_parameters(client: TestClient) -> None:
    assert client.get("/api/timeline?minutes=0").status_code == 422
    assert client.get("/api/timeline?minutes=121").status_code == 422
    assert client.get("/api/timeline?limit=501").status_code == 422


def test_heatmap_returns_aggregated_traffic_points(client: TestClient) -> None:
    response = client.get("/api/heatmap?hours=24")

    assert response.status_code == 200
    assert response.json() == [{"latitude": 51.8, "longitude": 19.0, "intensity": 1.0}]


def test_heatmap_accepts_only_supported_intervals(client: TestClient) -> None:
    assert client.get("/api/heatmap?hours=6").status_code == 422


def test_latest_includes_aircraft_positions(client: TestClient) -> None:
    response = client.get("/api/latest")

    assert response.status_code == 200
    assert response.json()["aircraft"][0]["icao24"] == "abc123"
    assert response.json()["aircraft"][0]["altitude_m"] == -15.24


def test_latest_returns_not_found_when_no_snapshot_exists(
    client: TestClient,
) -> None:
    class EmptySnapshotService(FakeSnapshotService):
        async def latest(self) -> LatestSnapshot:
            raise SnapshotNotFoundError

    client.app.dependency_overrides[get_snapshot_service] = EmptySnapshotService
    response = client.get("/api/latest")

    assert response.status_code == 404
    assert response.json()["detail"] == "no flight snapshots collected yet"


def test_session_preferences_are_stored_server_side(client: TestClient) -> None:
    initial_response = client.get("/api/session")

    assert initial_response.status_code == 200
    assert initial_response.json() == {"theme": "dark"}
    cookie = initial_response.headers["set-cookie"]
    assert "flight_tracker_session=" in cookie
    assert "httponly" in cookie.lower()
    assert "dark" not in cookie

    update_response = client.put("/api/session", json={"theme": "light"})
    assert update_response.status_code == 200
    assert update_response.json() == {"theme": "light"}

    restored_response = client.get("/api/session")
    assert restored_response.status_code == 200
    assert restored_response.json() == {"theme": "light"}

def test_session_rejects_unknown_theme(client: TestClient) -> None:
    assert client.put("/api/session", json={"theme": "blue"}).status_code == 422
