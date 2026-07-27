"""Ports implemented by persistence and external-system adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from uav_crop_analysis.application.import_models import (
    ImageProbe,
    TelemetryCsvMapping,
    TelemetryReadResult,
)
from uav_crop_analysis.domain import (
    CameraProfile,
    DroneId,
    ImageAsset,
    MissionId,
    SurveyMission,
    TelemetrySample,
)


class MissionRepository(Protocol):
    def add(self, mission: SurveyMission) -> None: ...

    def get(self, mission_id: MissionId) -> SurveyMission | None: ...

    def list_missions(self) -> tuple[SurveyMission, ...]: ...


class MissionDataRepository(MissionRepository, Protocol):
    @property
    def schema_version(self) -> int: ...

    def save_bundle(
        self,
        mission: SurveyMission,
        camera_profiles: tuple[CameraProfile, ...],
        images: tuple[ImageAsset, ...],
        telemetry_samples: tuple[TelemetrySample, ...],
    ) -> None: ...

    def list_camera_profiles(self, mission_id: MissionId) -> tuple[CameraProfile, ...]: ...

    def list_image_assets(self, mission_id: MissionId) -> tuple[ImageAsset, ...]: ...

    def list_telemetry_samples(self, mission_id: MissionId) -> tuple[TelemetrySample, ...]: ...


class ImageMetadataReader(Protocol):
    def read(self, image_path: Path) -> ImageProbe: ...


class TelemetryReader(Protocol):
    def read(
        self,
        telemetry_path: Path,
        mapping: TelemetryCsvMapping,
        mission_id: MissionId,
        drone_id: DroneId,
    ) -> TelemetryReadResult: ...
