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
    qgroundcontrol_log_import: bool
    mavsdk_available: bool
    drone_telemetry_read: bool
    drone_mission_read: bool
    drone_commands_enabled: bool
    nodeodm_configured: bool


@dataclass(frozen=True, slots=True)
class CreateMissionRequest:
    mission_id: str
    name: str
    drone_ids: tuple[str, str, str]
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
