"""Read models for inspecting imported mission images and metadata quality."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from uav_crop_analysis.application.ports import MissionDataRepository
from uav_crop_analysis.domain import CameraProfile, MissionId, SurveyMission


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    code: str
    message: str
    severity: str
    drone_id: str
    image_id: str | None = None
    source_path: Path | None = None


@dataclass(frozen=True, slots=True)
class ImageDataRow:
    image_id: str
    drone_id: str
    sequence_index: int
    source_path: Path
    captured_at: datetime
    width_px: int
    height_px: int
    latitude: float | None
    longitude: float | None
    relative_altitude_m: float | None
    telemetry_offset_ms: int | None
    camera_profile_id: str | None
    source_exists: bool
    issue_codes: tuple[str, ...]

    @property
    def has_issues(self) -> bool:
        return bool(self.issue_codes)


@dataclass(frozen=True, slots=True)
class DroneDataGroup:
    drone_id: str
    lane_index: int
    images: tuple[ImageDataRow, ...]
    telemetry_count: int
    issue_count: int


@dataclass(frozen=True, slots=True)
class MissionDataWorkspace:
    mission: SurveyMission
    drones: tuple[DroneDataGroup, ...]
    cameras: tuple[CameraProfile, ...]
    issues: tuple[DataQualityIssue, ...]

    @property
    def image_count(self) -> int:
        return sum(len(drone.images) for drone in self.drones)


class MissionDataWorkspaceService:
    def __init__(self, repository: MissionDataRepository) -> None:
        self._repository = repository

    def get_data(self, mission_id: str) -> MissionDataWorkspace | None:
        mission = self._repository.get(MissionId(mission_id))
        if mission is None:
            return None
        assets = self._repository.list_image_assets(mission.mission_id)
        telemetry = self._repository.list_telemetry_samples(mission.mission_id)
        cameras = self._repository.list_camera_profiles(mission.mission_id)
        rows: list[ImageDataRow] = []
        issues: list[DataQualityIssue] = []
        for asset in assets:
            issue_codes: list[str] = []
            source_exists = asset.source_path.is_file()
            checks = (
                (
                    not source_exists,
                    "source_missing",
                    "Không tìm thấy tệp ảnh nguồn.",
                    "error",
                ),
                (
                    asset.position is None,
                    "missing_gps",
                    "Ảnh chưa có tọa độ GPS.",
                    "error",
                ),
                (
                    asset.relative_altitude_m is None,
                    "missing_altitude",
                    "Ảnh chưa có độ cao tương đối.",
                    "error",
                ),
                (
                    asset.telemetry_offset_ms is not None
                    and asset.telemetry_offset_ms > 2000,
                    "telemetry_skew",
                    "Độ lệch thời gian telemetry lớn hơn 2 giây.",
                    "warning",
                ),
            )
            for failed, code, message, severity in checks:
                if not failed:
                    continue
                issue_codes.append(code)
                issues.append(
                    DataQualityIssue(
                        code=code,
                        message=message,
                        severity=severity,
                        drone_id=asset.drone_id.value,
                        image_id=asset.asset_id,
                        source_path=asset.source_path,
                    )
                )
            rows.append(
                ImageDataRow(
                    image_id=asset.asset_id,
                    drone_id=asset.drone_id.value,
                    sequence_index=asset.sequence_index,
                    source_path=asset.source_path,
                    captured_at=asset.captured_at,
                    width_px=asset.width_px,
                    height_px=asset.height_px,
                    latitude=asset.position.latitude if asset.position else None,
                    longitude=asset.position.longitude if asset.position else None,
                    relative_altitude_m=asset.relative_altitude_m,
                    telemetry_offset_ms=asset.telemetry_offset_ms,
                    camera_profile_id=asset.camera_profile_id,
                    source_exists=source_exists,
                    issue_codes=tuple(issue_codes),
                )
            )
        groups = tuple(
            DroneDataGroup(
                drone_id=assignment.drone_id.value,
                lane_index=assignment.lane_index,
                images=tuple(
                    sorted(
                        (
                            row
                            for row in rows
                            if row.drone_id == assignment.drone_id.value
                        ),
                        key=lambda row: row.sequence_index,
                    )
                ),
                telemetry_count=sum(
                    sample.drone_id == assignment.drone_id for sample in telemetry
                ),
                issue_count=sum(
                    issue.drone_id == assignment.drone_id.value for issue in issues
                ),
            )
            for assignment in sorted(mission.assignments, key=lambda item: item.lane_index)
        )
        return MissionDataWorkspace(
            mission=mission,
            drones=groups,
            cameras=cameras,
            issues=tuple(issues),
        )
