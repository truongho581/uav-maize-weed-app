"""Framework-neutral read models for mission reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping


REPORT_SCHEMA_VERSION = 1
REPORT_TEMPLATE_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ReportCamera:
    profile_id: str
    name: str
    make: str | None
    model: str | None
    image_width_px: int | None
    image_height_px: int | None
    horizontal_fov_deg: float | None
    estimated_gsd_cm_px: float | None
    gsd_method: str


@dataclass(frozen=True, slots=True)
class ReportImageRecord:
    mission_id: str
    drone_id: str
    lane_index: int
    image_id: str
    sequence_index: int
    captured_at: datetime
    source_path: Path
    latitude: float | None
    longitude: float | None
    relative_altitude_m: float | None
    camera_profile_id: str | None
    estimated_gsd_cm_px: float | None
    quality_status: str
    issue_codes: tuple[str, ...]
    analysis_job_id: str | None
    model_id: str | None
    model_version: str | None
    weed_coverage_percent: float | None
    estimated_weed_area_m2: float | None
    maize_status: str = "unavailable_instance_checkpoint"
    maize_instance_count: int | None = None
    maize_density_plants_m2: float | None = None
    maize_canopy_area_m2: float | None = None
    class_coverage_percent: Mapping[str, float] | None = None
    class_area_m2: Mapping[str, float] | None = None


@dataclass(frozen=True, slots=True)
class ReportDroneSummary:
    drone_id: str
    lane_index: int
    image_count: int
    valid_image_count: int
    issue_image_count: int
    analyzed_image_count: int
    telemetry_count: int
    gps_coverage: float
    altitude_coverage: float
    mean_weed_coverage_percent: float | None


@dataclass(frozen=True, slots=True)
class ReportAnalysis:
    job_id: str
    status: str
    model_id: str
    model_version: str | None
    artifact_role: str
    image_count: int
    weed_threshold: float
    updated_at: datetime
    manifest_sha256: str | None


@dataclass(frozen=True, slots=True)
class ReportSpatialProduct:
    product_id: str
    kind: str
    accuracy: str
    path: Path
    preview_path: Path
    crs: str | None
    resolution: tuple[float, float] | None
    bounds: tuple[float, float, float, float] | None
    source_product_id: str | None
    source_job_id: str | None


@dataclass(frozen=True, slots=True)
class MissionReport:
    schema_version: int
    template_version: str
    generated_at: datetime
    mission_id: str
    mission_name: str
    mission_created_at: datetime
    drone_count: int
    altitude_m: float
    gimbal_pitch_deg: float
    forward_overlap: float
    side_overlap: float
    capture_mode: str
    cameras: tuple[ReportCamera, ...]
    drones: tuple[ReportDroneSummary, ...]
    images: tuple[ReportImageRecord, ...]
    analyses: tuple[ReportAnalysis, ...]
    spatial_products: tuple[ReportSpatialProduct, ...]
    limitations: tuple[str, ...]

    @property
    def image_count(self) -> int:
        return len(self.images)

    @property
    def valid_image_count(self) -> int:
        return sum(item.quality_status == "valid" for item in self.images)

    @property
    def issue_image_count(self) -> int:
        return self.image_count - self.valid_image_count

    @property
    def analyzed_image_count(self) -> int:
        return sum(item.analysis_job_id is not None for item in self.images)

    @property
    def mean_weed_coverage_percent(self) -> float | None:
        values = [
            item.weed_coverage_percent
            for item in self.images
            if item.weed_coverage_percent is not None
        ]
        return sum(values) / len(values) if values else None

    @property
    def mean_crop_coverage_percent(self) -> float | None:
        values = [
            float(item.class_coverage_percent["crop"])
            for item in self.images
            if item.class_coverage_percent is not None
            and isinstance(item.class_coverage_percent.get("crop"), (int, float))
        ]
        return sum(values) / len(values) if values else None


@dataclass(frozen=True, slots=True)
class ReportExport:
    directory: Path
    report_json: Path
    image_csv: Path
    report_html: Path
    manifest_json: Path
    checksums: tuple[tuple[str, str], ...]
