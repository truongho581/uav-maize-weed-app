"""Core value objects for a three-drone crop survey mission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from uav_crop_analysis.errors import DomainValidationError


EXPECTED_DRONE_COUNT = 3
MIN_ALTITUDE_M = 10.0
MAX_ALTITUDE_M = 20.0


def _required_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise DomainValidationError(
            f"{field} must not be empty",
            context={"field": field},
        )
    return normalized


@dataclass(frozen=True, slots=True)
class MissionId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _required_text(self.value, "mission_id"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DroneId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _required_text(self.value, "drone_id"))

    def __str__(self) -> str:
        return self.value


class CaptureMode(str, Enum):
    STOP_AND_CAPTURE = "stop_and_capture"


@dataclass(frozen=True, slots=True)
class FlightProfile:
    altitude_m: float = 10.0
    gimbal_pitch_deg: float = -90.0
    forward_overlap: float = 0.75
    side_overlap: float = 0.65
    capture_mode: CaptureMode = CaptureMode.STOP_AND_CAPTURE

    def __post_init__(self) -> None:
        if not MIN_ALTITUDE_M <= self.altitude_m <= MAX_ALTITUDE_M:
            raise DomainValidationError(
                f"altitude_m must be between {MIN_ALTITUDE_M:g} and {MAX_ALTITUDE_M:g}",
                context={"field": "altitude_m", "value": self.altitude_m},
            )
        if not -90.0 <= self.gimbal_pitch_deg <= 0.0:
            raise DomainValidationError(
                "gimbal_pitch_deg must be between -90 and 0",
                context={"field": "gimbal_pitch_deg", "value": self.gimbal_pitch_deg},
            )
        for field, value in (
            ("forward_overlap", self.forward_overlap),
            ("side_overlap", self.side_overlap),
        ):
            if not 0.0 <= value < 1.0:
                raise DomainValidationError(
                    f"{field} must be in [0, 1)",
                    context={"field": field, "value": value},
                )

    @property
    def is_nadir(self) -> bool:
        return self.gimbal_pitch_deg == -90.0


@dataclass(frozen=True, slots=True)
class DroneAssignment:
    drone_id: DroneId
    lane_index: int

    def __post_init__(self) -> None:
        if self.lane_index < 0:
            raise DomainValidationError(
                "lane_index must be non-negative",
                context={"field": "lane_index", "value": self.lane_index},
            )


@dataclass(frozen=True, slots=True)
class SurveyMission:
    mission_id: MissionId
    name: str
    assignments: tuple[DroneAssignment, ...]
    flight_profile: FlightProfile
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        object.__setattr__(self, "assignments", tuple(self.assignments))
        if len(self.assignments) != EXPECTED_DRONE_COUNT:
            raise DomainValidationError(
                f"survey mission requires exactly {EXPECTED_DRONE_COUNT} drones",
                context={"field": "assignments", "count": len(self.assignments)},
            )

        drone_ids = [assignment.drone_id.value for assignment in self.assignments]
        if len(drone_ids) != len(set(drone_ids)):
            raise DomainValidationError(
                "drone assignments must use unique drone IDs",
                context={"field": "assignments"},
            )

        lane_indices = [assignment.lane_index for assignment in self.assignments]
        if set(lane_indices) != set(range(EXPECTED_DRONE_COUNT)):
            raise DomainValidationError(
                f"lane indices must be 0..{EXPECTED_DRONE_COUNT - 1}",
                context={"field": "assignments", "lane_indices": lane_indices},
            )

        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise DomainValidationError(
                "created_at must be timezone-aware",
                context={"field": "created_at"},
            )

    @classmethod
    def create(
        cls,
        mission_id: str,
        name: str,
        drone_ids: tuple[str, str, str],
        *,
        flight_profile: FlightProfile | None = None,
        created_at: datetime | None = None,
    ) -> SurveyMission:
        assignments = tuple(
            DroneAssignment(DroneId(drone_id), lane_index)
            for lane_index, drone_id in enumerate(drone_ids)
        )
        return cls(
            mission_id=MissionId(mission_id),
            name=name,
            assignments=assignments,
            flight_profile=flight_profile or FlightProfile(),
            created_at=created_at or datetime.now(timezone.utc),
        )


@dataclass(frozen=True, slots=True)
class GeoPoint:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise DomainValidationError(
                "latitude must be between -90 and 90",
                context={"field": "latitude", "value": self.latitude},
            )
        if not -180.0 <= self.longitude <= 180.0:
            raise DomainValidationError(
                "longitude must be between -180 and 180",
                context={"field": "longitude", "value": self.longitude},
            )


@dataclass(frozen=True, slots=True)
class CameraProfile:
    profile_id: str
    name: str
    make: str | None = None
    model: str | None = None
    image_width_px: int | None = None
    image_height_px: int | None = None
    focal_length_mm: float | None = None
    horizontal_fov_deg: float | None = None
    vertical_fov_deg: float | None = None
    distortion_coefficients: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _required_text(self.profile_id, "profile_id"))
        object.__setattr__(self, "name", _required_text(self.name, "camera_name"))
        for field, value in (
            ("image_width_px", self.image_width_px),
            ("image_height_px", self.image_height_px),
            ("focal_length_mm", self.focal_length_mm),
            ("horizontal_fov_deg", self.horizontal_fov_deg),
            ("vertical_fov_deg", self.vertical_fov_deg),
        ):
            if value is not None and value <= 0:
                raise DomainValidationError(
                    f"{field} must be positive",
                    context={"field": field, "value": value},
                )
        for field, value in (
            ("horizontal_fov_deg", self.horizontal_fov_deg),
            ("vertical_fov_deg", self.vertical_fov_deg),
        ):
            if value is not None and value >= 180:
                raise DomainValidationError(
                    f"{field} must be below 180",
                    context={"field": field, "value": value},
                )
        object.__setattr__(self, "distortion_coefficients", tuple(self.distortion_coefficients))


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    mission_id: MissionId
    drone_id: DroneId
    recorded_at: datetime
    position: GeoPoint
    relative_altitude_m: float

    def __post_init__(self) -> None:
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise DomainValidationError(
                "recorded_at must be timezone-aware",
                context={"field": "recorded_at"},
            )
        if self.relative_altitude_m < 0:
            raise DomainValidationError(
                "relative_altitude_m must be non-negative",
                context={"field": "relative_altitude_m", "value": self.relative_altitude_m},
            )


@dataclass(frozen=True, slots=True)
class ImageAsset:
    asset_id: str
    mission_id: MissionId
    drone_id: DroneId
    source_path: Path
    sha256: str
    size_bytes: int
    captured_at: datetime
    width_px: int
    height_px: int
    sequence_index: int
    position: GeoPoint | None = None
    absolute_altitude_m: float | None = None
    relative_altitude_m: float | None = None
    telemetry_offset_ms: int | None = None
    camera_profile_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _required_text(self.asset_id, "asset_id"))
        object.__setattr__(self, "source_path", Path(self.source_path))
        checksum = self.sha256.lower()
        if len(checksum) != 64:
            raise DomainValidationError(
                "sha256 must contain 64 hexadecimal characters",
                context={"field": "sha256"},
            )
        try:
            int(checksum, 16)
        except ValueError as exc:
            raise DomainValidationError(
                "sha256 must contain 64 hexadecimal characters",
                context={"field": "sha256"},
            ) from exc
        object.__setattr__(self, "sha256", checksum)
        if self.size_bytes <= 0:
            raise DomainValidationError("size_bytes must be positive")
        if self.width_px <= 0 or self.height_px <= 0:
            raise DomainValidationError("image dimensions must be positive")
        if self.sequence_index < 0:
            raise DomainValidationError("sequence_index must be non-negative")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise DomainValidationError(
                "captured_at must be timezone-aware",
                context={"field": "captured_at"},
            )
        if self.relative_altitude_m is not None and self.relative_altitude_m < 0:
            raise DomainValidationError("relative_altitude_m must be non-negative")
