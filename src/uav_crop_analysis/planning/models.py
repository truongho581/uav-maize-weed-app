"""Framework-neutral contracts for deterministic crop-survey planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from uav_crop_analysis.domain import (
    MAX_ALTITUDE_M,
    MAX_DRONE_COUNT,
    MIN_ALTITUDE_M,
    MIN_DRONE_COUNT,
    CameraProfile,
    GeoPoint,
)
from uav_crop_analysis.errors import MissionPlanningError


PLANNER_GENERATOR_VERSION = "1.0"
MISSION_PLAN_SCHEMA_VERSION = 1


def _required_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise MissionPlanningError(f"{field} must not be empty", context={"field": field})
    return normalized


@dataclass(frozen=True, slots=True)
class SurveyArea:
    polygon_wgs84: tuple[GeoPoint, ...]
    projected_crs: str | None = None

    def __post_init__(self) -> None:
        points = tuple(self.polygon_wgs84)
        if len(points) > 1 and points[0] == points[-1]:
            points = points[:-1]
        if len(points) < 3 or len(set(points)) < 3:
            raise MissionPlanningError("survey polygon requires at least three unique points")
        object.__setattr__(self, "polygon_wgs84", points)
        if self.projected_crs is not None:
            object.__setattr__(
                self,
                "projected_crs",
                _required_text(self.projected_crs, "projected_crs"),
            )


@dataclass(frozen=True, slots=True)
class MissionPlanningProfile:
    drone_count: int = 1
    altitude_agl_m: float = 10.0
    gimbal_pitch_deg: float = -90.0
    forward_overlap: float = 0.75
    side_overlap: float = 0.65
    flight_speed_mps: float = 3.0
    capture_pause_seconds: float = 1.0
    sweep_heading_deg: float | None = None
    minimum_route_separation_m: float = 2.0

    def __post_init__(self) -> None:
        if not MIN_DRONE_COUNT <= self.drone_count <= MAX_DRONE_COUNT:
            raise MissionPlanningError(
                f"drone_count must be between {MIN_DRONE_COUNT} and {MAX_DRONE_COUNT}"
            )
        if not MIN_ALTITUDE_M <= self.altitude_agl_m <= MAX_ALTITUDE_M:
            raise MissionPlanningError(
                f"altitude_agl_m must be between {MIN_ALTITUDE_M:g} and "
                f"{MAX_ALTITUDE_M:g}"
            )
        if abs(self.gimbal_pitch_deg + 90.0) > 1e-6:
            raise MissionPlanningError("mission planner currently requires nadir gimbal -90 deg")
        for field, value in (
            ("forward_overlap", self.forward_overlap),
            ("side_overlap", self.side_overlap),
        ):
            if not 0.0 <= value < 1.0:
                raise MissionPlanningError(f"{field} must be in [0, 1)")
        if self.flight_speed_mps <= 0:
            raise MissionPlanningError("flight_speed_mps must be positive")
        if self.capture_pause_seconds < 0:
            raise MissionPlanningError("capture_pause_seconds must be non-negative")
        if self.sweep_heading_deg is not None and not 0 <= self.sweep_heading_deg < 180:
            raise MissionPlanningError("sweep_heading_deg must be in [0, 180)")
        if self.minimum_route_separation_m < 0:
            raise MissionPlanningError("minimum_route_separation_m must be non-negative")


@dataclass(frozen=True, slots=True)
class CameraFootprint:
    horizontal_fov_deg: float
    vertical_fov_deg: float
    ground_width_m: float
    ground_height_m: float
    lane_spacing_m: float
    capture_spacing_m: float
    gsd_x_cm_px: float | None = None
    gsd_y_cm_px: float | None = None

    @property
    def area_m2(self) -> float:
        return self.ground_width_m * self.ground_height_m


class CaptureAction(str, Enum):
    STOP_AND_CAPTURE = "stop_and_capture"


@dataclass(frozen=True, slots=True)
class CaptureWaypoint:
    sequence: int
    position: GeoPoint
    altitude_agl_m: float
    hold_seconds: float
    lane_index: int
    action: CaptureAction = CaptureAction.STOP_AND_CAPTURE

    def __post_init__(self) -> None:
        if self.sequence < 0 or self.lane_index < 0:
            raise MissionPlanningError("waypoint sequence and lane_index must be non-negative")
        if self.altitude_agl_m <= 0 or self.hold_seconds < 0:
            raise MissionPlanningError("waypoint altitude/hold values are invalid")


@dataclass(frozen=True, slots=True)
class DroneRoute:
    drone_id: str
    home: GeoPoint | None
    lane_indices: tuple[int, ...]
    waypoints: tuple[CaptureWaypoint, ...]
    estimated_distance_m: float
    estimated_duration_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "drone_id", _required_text(self.drone_id, "drone_id"))
        object.__setattr__(self, "lane_indices", tuple(self.lane_indices))
        object.__setattr__(self, "waypoints", tuple(self.waypoints))
        if not self.lane_indices or not self.waypoints:
            raise MissionPlanningError("each planned drone route requires lanes and waypoints")
        if self.estimated_distance_m < 0 or self.estimated_duration_seconds < 0:
            raise MissionPlanningError("route estimates must be non-negative")


@dataclass(frozen=True, slots=True)
class PlanningWarning:
    code: str
    message: str
    drone_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _required_text(self.code, "warning_code"))
        object.__setattr__(self, "message", _required_text(self.message, "warning_message"))


@dataclass(frozen=True, slots=True)
class MissionPlanningRequest:
    mission_id: str
    survey_area: SurveyArea
    profile: MissionPlanningProfile
    camera: CameraProfile
    drone_ids: tuple[str, ...]
    homes: tuple[GeoPoint | None, ...] = ()
    image_size_px: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mission_id", _required_text(self.mission_id, "mission_id"))
        drone_ids = tuple(_required_text(value, "drone_id") for value in self.drone_ids)
        object.__setattr__(self, "drone_ids", drone_ids)
        if len(drone_ids) != self.profile.drone_count:
            raise MissionPlanningError("drone_ids count must match profile.drone_count")
        if len(set(drone_ids)) != len(drone_ids):
            raise MissionPlanningError("drone_ids must be unique")
        homes = tuple(self.homes) if self.homes else (None,) * len(drone_ids)
        if len(homes) != len(drone_ids):
            raise MissionPlanningError("homes count must match drone_ids count")
        object.__setattr__(self, "homes", homes)
        if self.image_size_px is not None:
            width, height = self.image_size_px
            if width <= 0 or height <= 0:
                raise MissionPlanningError("image_size_px values must be positive")


@dataclass(frozen=True, slots=True)
class PlannedMission:
    mission_id: str
    survey_area: SurveyArea
    profile: MissionPlanningProfile
    camera_profile_id: str
    camera_profile_sha256: str
    camera_footprint: CameraFootprint
    effective_sweep_heading_deg: float
    area_m2: float
    coverage_ratio: float
    routes: tuple[DroneRoute, ...]
    warnings: tuple[PlanningWarning, ...]
    generator_version: str = PLANNER_GENERATOR_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "mission_id", _required_text(self.mission_id, "mission_id"))
        object.__setattr__(
            self,
            "camera_profile_id",
            _required_text(self.camera_profile_id, "camera_profile_id"),
        )
        digest = self.camera_profile_sha256.lower()
        if len(digest) != 64:
            raise MissionPlanningError("camera_profile_sha256 must be a SHA-256 digest")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise MissionPlanningError(
                "camera_profile_sha256 must be a SHA-256 digest"
            ) from exc
        object.__setattr__(self, "camera_profile_sha256", digest)
        object.__setattr__(self, "routes", tuple(self.routes))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if not self.routes:
            raise MissionPlanningError("planned mission requires at least one drone route")
        if self.area_m2 <= 0 or not 0 <= self.coverage_ratio <= 1.000001:
            raise MissionPlanningError("planned mission area/coverage values are invalid")

    @property
    def capture_count(self) -> int:
        return sum(len(route.waypoints) for route in self.routes)

    @property
    def export_ready(self) -> bool:
        # Launch and return locations belong to the flight-control system.  A
        # GreenEye route is exportable once its survey waypoints are complete.
        return all(route.waypoints for route in self.routes)


@dataclass(frozen=True, slots=True)
class MissionPlanExport:
    directory: Path
    mission_json: Path
    route_jsons: tuple[Path, ...]
    qgroundcontrol_plans: tuple[Path, ...]
    checksums_file: Path
    checksums: tuple[tuple[str, str], ...]
