"""Read-only contracts for ground-control and telemetry integrations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from uav_crop_analysis.domain import GeoPoint, TelemetrySample
from uav_crop_analysis.errors import IntegrationError


@dataclass(frozen=True, slots=True)
class QgcWaypoint:
    sequence: int
    command: int
    frame: int
    latitude: float
    longitude: float
    altitude_m: float
    auto_continue: bool
    source_type: str


@dataclass(frozen=True, slots=True)
class QgcSurveyArea:
    sequence: int
    polygon: tuple[GeoPoint, ...]
    visual_transect_points: tuple[GeoPoint, ...]
    hover_and_capture: bool
    frontal_overlap_percent: float | None
    side_overlap_percent: float | None


@dataclass(frozen=True, slots=True)
class QgcPlan:
    source_path: Path
    plan_version: int
    mission_version: int
    ground_station: str
    firmware_type: int
    vehicle_type: int
    planned_home: GeoPoint
    planned_home_altitude_m: float
    waypoints: tuple[QgcWaypoint, ...]
    survey_areas: tuple[QgcSurveyArea, ...]


@dataclass(frozen=True, slots=True)
class TelemetryLogImport:
    source_path: Path
    samples: tuple[TelemetrySample, ...]
    dropped_duplicate_count: int
    dropped_out_of_order_count: int
    system_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SystemMapping:
    system_id: int
    drone_id: str

    def __post_init__(self) -> None:
        if not 1 <= self.system_id <= 255:
            raise IntegrationError("MAVLink system_id must be in 1..255")
        if not self.drone_id.strip():
            raise IntegrationError("drone_id must not be empty")


@dataclass(frozen=True, slots=True)
class MavsdkEndpoint:
    system_id: int
    drone_id: str
    system_address: str

    def __post_init__(self) -> None:
        SystemMapping(self.system_id, self.drone_id)
        if not self.system_address.strip():
            raise IntegrationError("MAVSDK system_address must not be empty")


@dataclass(frozen=True, slots=True)
class TelemetryFrame:
    system_id: int
    drone_id: str
    sequence: int
    recorded_at: datetime
    position: GeoPoint
    relative_altitude_m: float
    reconnect_count: int = 0

    def __post_init__(self) -> None:
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise IntegrationError("telemetry timestamp must be timezone-aware")
        if self.sequence < 0 or self.reconnect_count < 0:
            raise IntegrationError("telemetry counters must be non-negative")
        if self.relative_altitude_m < 0:
            raise IntegrationError("relative altitude must be non-negative")


@dataclass(frozen=True, slots=True)
class MavsdkMissionItem:
    sequence: int
    command: int
    frame: int
    latitude: float | None
    longitude: float | None
    altitude_m: float | None
