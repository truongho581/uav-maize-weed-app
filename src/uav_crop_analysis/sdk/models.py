"""Versioned DTOs for host applications and the local API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SDK_SCHEMA_VERSION = 1
API_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class Capabilities:
    sdk_schema_version: int
    api_versions: tuple[str, ...]
    mission_management: bool
    analysis_jobs: bool
    report_export: bool
    geospatial_results: bool
    qgroundcontrol_plan_import: bool
    mission_planning: bool
    mission_plan_export: bool
    qgroundcontrol_plan_export: bool
    qgroundcontrol_log_import: bool
    mavsdk_available: bool
    drone_telemetry_read: bool
    drone_mission_read: bool
    drone_commands_enabled: bool
    orthomosaic_engine_configured: bool
    orthomosaic_engine_name: str


@dataclass(frozen=True, slots=True)
class CreateMissionRequest:
    mission_id: str
    name: str
    drone_ids: tuple[str, ...]
    altitude_m: float = 10.0
    gimbal_pitch_deg: float = -90.0
    forward_overlap: float = 0.75
    side_overlap: float = 0.65


@dataclass(frozen=True, slots=True)
class DroneAssignmentView:
    drone_id: str
    lane_index: int


@dataclass(frozen=True, slots=True)
class MissionView:
    mission_id: str
    name: str
    created_at: datetime
    drones: tuple[DroneAssignmentView, ...]
    altitude_m: float
    gimbal_pitch_deg: float
    forward_overlap: float
    side_overlap: float
    capture_mode: str
    image_count: int
    gps_coverage: float
    data_status: str


@dataclass(frozen=True, slots=True)
class SubmitAnalysisRequest:
    mission_id: str
    model_id: str
    artifact_role: str = "best"
    device: str = "cpu"
    tile_size: int = 640
    overlap: int = 64
    weed_threshold: float = 0.5
    selected_image_ids: tuple[str, ...] = ()
    auto_start: bool = True


@dataclass(frozen=True, slots=True)
class JobView:
    job_id: str
    mission_id: str
    status: str
    stage: str
    progress: float
    attempt: int
    model_id: str
    artifact_role: str
    image_count: int
    created_at: datetime
    updated_at: datetime
    error_code: str | None
    error_message: str | None
    artifact_dir: Path | None
    result_manifest_sha256: str | None


@dataclass(frozen=True, slots=True)
class SpatialResultView:
    product_id: str
    mission_id: str
    kind: str
    accuracy: str
    path: Path
    preview_path: Path
    created_at: datetime
    crs: str | None
    source_product_id: str | None
    source_job_id: str | None


@dataclass(frozen=True, slots=True)
class ImportMissionView:
    mission_id: str
    persisted: bool
    image_count: int
    telemetry_count: int
    issue_count: int
    error_count: int


@dataclass(frozen=True, slots=True)
class PlanMissionRequest:
    mission_id: str
    camera_profile_id: str
    polygon_wgs84: tuple[tuple[float, float], ...]
    homes_wgs84: tuple[tuple[float, float] | None, ...] = ()
    projected_crs: str | None = None
    altitude_agl_m: float | None = None
    gimbal_pitch_deg: float = -90.0
    forward_overlap: float | None = None
    side_overlap: float | None = None
    flight_speed_mps: float = 3.0
    capture_pause_seconds: float = 1.0
    sweep_heading_deg: float | None = None
    minimum_route_separation_m: float = 2.0
    image_size_px: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class PlannedWaypointView:
    sequence: int
    latitude: float
    longitude: float
    altitude_agl_m: float
    hold_seconds: float
    lane_index: int
    action: str


@dataclass(frozen=True, slots=True)
class PlannedRouteView:
    drone_id: str
    home_wgs84: tuple[float, float] | None
    lane_indices: tuple[int, ...]
    waypoints: tuple[PlannedWaypointView, ...]
    estimated_distance_m: float
    estimated_duration_seconds: float


@dataclass(frozen=True, slots=True)
class PlanningWarningView:
    code: str
    message: str
    drone_id: str | None


@dataclass(frozen=True, slots=True)
class MissionPlanView:
    mission_id: str
    generator_version: str
    projected_crs: str | None
    polygon_wgs84: tuple[tuple[float, float], ...]
    camera_profile_id: str
    camera_profile_sha256: str
    altitude_agl_m: float
    forward_overlap: float
    side_overlap: float
    flight_speed_mps: float
    capture_pause_seconds: float
    effective_sweep_heading_deg: float
    ground_footprint_m: tuple[float, float]
    gsd_cm_px: tuple[float | None, float | None]
    lane_spacing_m: float
    capture_spacing_m: float
    area_m2: float
    coverage_ratio: float
    capture_count: int
    export_ready: bool
    routes: tuple[PlannedRouteView, ...]
    warnings: tuple[PlanningWarningView, ...]
