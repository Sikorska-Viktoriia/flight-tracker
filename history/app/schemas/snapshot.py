from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
AltitudeMeters = Annotated[float, Field(allow_inf_nan=False)]


class AircraftPosition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    icao24: str
    callsign: str = ""
    country: str = ""
    longitude: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    latitude: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    altitude_m: AltitudeMeters
    speed_mps: NonNegativeFloat
    heading_deg: Annotated[float, Field(ge=0, le=360, allow_inf_nan=False)]
    aircraft_type: str = ""
    category: str = ""
    squawk: str = ""
    vertical_rate_mps: Annotated[float | None, Field(allow_inf_nan=False)] = None


class FetcherSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    collected_at: datetime
    total_airborne: Annotated[int, Field(ge=0)]
    average_speed_mps: NonNegativeFloat
    max_altitude_m: NonNegativeFloat
    top_flight_callsign: str = ""
    aircraft: list[AircraftPosition] = Field(default_factory=list)


class SnapshotHistoryItem(BaseModel):
    id: int
    collected_at: datetime
    total_airborne: int
    average_speed_mps: float
    average_altitude_m: float
    max_altitude_m: float
    top_flight_callsign: str
    saved_at: datetime


class LatestSnapshot(SnapshotHistoryItem):
    aircraft: list[AircraftPosition]


class TimelineSnapshot(SnapshotHistoryItem):
    aircraft: list[AircraftPosition]


class HeatmapPoint(BaseModel):
    latitude: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    intensity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
