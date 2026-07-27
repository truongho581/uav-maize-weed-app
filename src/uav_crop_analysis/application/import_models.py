"""DTOs shared by mission import services and external adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from uav_crop_analysis.domain import (
    CameraProfile,
    DroneId,
    GeoPoint,
    ImageAsset,
    SurveyMission,
    TelemetrySample,
)


class IssueSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


class TimestampFormat(str, Enum):
    ISO8601 = "iso8601"
    UNIX_SECONDS = "unix_s"
    UNIX_MILLISECONDS = "unix_ms"
    UNIX_MICROSECONDS = "unix_us"
    UNIX_NANOSECONDS = "unix_ns"


@dataclass(frozen=True, slots=True)
class ImportIssue:
    code: str
    message: str
    severity: IssueSeverity
    drone_id: str | None = None
    source: str | None = None
    row_number: int | None = None


@dataclass(frozen=True, slots=True)
class TelemetryCsvMapping:
    timestamp_column: str = "timestamp"
    latitude_column: str = "latitude"
    longitude_column: str = "longitude"
    relative_altitude_column: str = "relative_altitude_m"
    timestamp_format: TimestampFormat = TimestampFormat.ISO8601


@dataclass(frozen=True, slots=True)
class DroneImportSource:
    drone_id: DroneId
    image_dir: Path
    telemetry_file: Path | None = None
    telemetry_mapping: TelemetryCsvMapping = field(default_factory=TelemetryCsvMapping)
    camera_profile: CameraProfile | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "image_dir", Path(self.image_dir))
        if self.telemetry_file is not None:
            object.__setattr__(self, "telemetry_file", Path(self.telemetry_file))


@dataclass(frozen=True, slots=True)
class MissionImportRequest:
    mission: SurveyMission
    sources: tuple[DroneImportSource, ...]
    max_telemetry_skew_seconds: float = 2.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(self.sources))
        if self.max_telemetry_skew_seconds < 0:
            raise ValueError("max_telemetry_skew_seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class ImageProbe:
    source_path: Path
    captured_at: datetime
    width_px: int
    height_px: int
    position: GeoPoint | None = None
    absolute_altitude_m: float | None = None
    relative_altitude_m: float | None = None


@dataclass(frozen=True, slots=True)
class TelemetryReadResult:
    samples: tuple[TelemetrySample, ...]
    issues: tuple[ImportIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class MetadataCoverage:
    image_count: int
    timestamp_count: int
    gps_count: int
    altitude_count: int

    @property
    def gps_ratio(self) -> float:
        return self.gps_count / self.image_count if self.image_count else 0.0

    @property
    def altitude_ratio(self) -> float:
        return self.altitude_count / self.image_count if self.image_count else 0.0


@dataclass(frozen=True, slots=True)
class ImportReport:
    mission_id: str
    images: tuple[ImageAsset, ...]
    telemetry_samples: tuple[TelemetrySample, ...]
    camera_profiles: tuple[CameraProfile, ...]
    issues: tuple[ImportIssue, ...]
    image_counts_by_drone: dict[str, int]
    metadata_coverage: MetadataCoverage
    persisted: bool

    @property
    def has_errors(self) -> bool:
        return any(issue.severity is IssueSeverity.ERROR for issue in self.issues)
