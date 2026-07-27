"""Mission data import, validation, telemetry synchronization, and persistence."""

from __future__ import annotations

from bisect import bisect_left
from datetime import datetime
import hashlib
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from uav_crop_analysis.application.import_models import (
    ImportIssue,
    ImportReport,
    IssueSeverity,
    MetadataCoverage,
    MissionImportRequest,
)
from uav_crop_analysis.application.ports import (
    ImageMetadataReader,
    MissionDataRepository,
    TelemetryReader,
)
from uav_crop_analysis.domain import (
    MAX_ALTITUDE_M,
    MIN_ALTITUDE_M,
    CameraProfile,
    DroneId,
    ImageAsset,
    TelemetrySample,
)
from uav_crop_analysis.errors import DomainValidationError, ImportDataError


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


class ImportMissionData:
    def __init__(
        self,
        repository: MissionDataRepository,
        image_reader: ImageMetadataReader,
        telemetry_reader: TelemetryReader,
    ) -> None:
        self._repository = repository
        self._image_reader = image_reader
        self._telemetry_reader = telemetry_reader

    def execute(self, request: MissionImportRequest) -> ImportReport:
        mission = request.mission
        assigned_ids = {item.drone_id.value for item in mission.assignments}
        issues: list[ImportIssue] = []
        source_by_drone = {}
        for source in request.sources:
            drone_value = source.drone_id.value
            if drone_value in source_by_drone:
                issues.append(
                    self._issue(
                        "duplicate_drone_source",
                        f"multiple import sources for {drone_value}",
                        drone_id=drone_value,
                    )
                )
                continue
            source_by_drone[drone_value] = source

        for drone_id in sorted(assigned_ids - set(source_by_drone)):
            issues.append(
                self._issue(
                    "missing_drone_source",
                    f"no import source for assigned drone {drone_id}",
                    drone_id=drone_id,
                )
            )
        for drone_id in sorted(set(source_by_drone) - assigned_ids):
            issues.append(
                self._issue(
                    "unexpected_drone_source",
                    f"source drone is not assigned to mission: {drone_id}",
                    drone_id=drone_id,
                )
            )

        telemetry_by_drone: dict[str, tuple[TelemetrySample, ...]] = {}
        all_telemetry: list[TelemetrySample] = []
        camera_profiles: dict[str, CameraProfile] = {}
        for drone_id in sorted(assigned_ids):
            drone_source = source_by_drone.get(drone_id)
            if drone_source is None:
                continue
            if drone_source.camera_profile is not None:
                existing = camera_profiles.get(drone_source.camera_profile.profile_id)
                if existing is not None and existing != drone_source.camera_profile:
                    issues.append(
                        self._issue(
                            "camera_profile_conflict",
                            f"camera profile ID has conflicting definitions: {existing.profile_id}",
                            drone_id=drone_id,
                        )
                    )
                else:
                    camera_profiles[drone_source.camera_profile.profile_id] = (
                        drone_source.camera_profile
                    )

            if drone_source.telemetry_file is None:
                issues.append(
                    self._issue(
                        "telemetry_file_not_provided",
                        "telemetry file was not provided; image metadata must contain GPS and altitude",
                        severity=IssueSeverity.WARNING,
                        drone_id=drone_id,
                    )
                )
                telemetry_by_drone[drone_id] = ()
                continue

            result = self._telemetry_reader.read(
                drone_source.telemetry_file,
                drone_source.telemetry_mapping,
                mission.mission_id,
                drone_source.drone_id,
            )
            sorted_samples = tuple(sorted(result.samples, key=lambda item: item.recorded_at))
            telemetry_by_drone[drone_id] = sorted_samples
            all_telemetry.extend(sorted_samples)
            issues.extend(result.issues)

        images: list[ImageAsset] = []
        image_counts = {drone_id: 0 for drone_id in sorted(assigned_ids)}
        seen_checksums: dict[str, str] = {}
        for assignment in mission.assignments:
            drone_id = assignment.drone_id.value
            drone_source = source_by_drone.get(drone_id)
            if drone_source is None:
                continue
            image_files = self._image_files(drone_source.image_dir)
            if image_files is None:
                issues.append(
                    self._issue(
                        "image_directory_missing",
                        f"image directory does not exist: {drone_source.image_dir}",
                        drone_id=drone_id,
                        source=str(drone_source.image_dir),
                    )
                )
                continue
            if not image_files:
                issues.append(
                    self._issue(
                        "missing_drone_images",
                        f"no supported images for {drone_id}",
                        drone_id=drone_id,
                        source=str(drone_source.image_dir),
                    )
                )
                continue

            previous_capture = None
            samples = telemetry_by_drone.get(drone_id, ())
            for image_path in image_files:
                try:
                    probe = self._image_reader.read(image_path)
                    checksum = self._sha256(image_path)
                except (ImportDataError, OSError) as exc:
                    issues.append(
                        self._issue(
                            "image_metadata_unreadable",
                            str(exc),
                            drone_id=drone_id,
                            source=str(image_path),
                        )
                    )
                    continue

                if previous_capture is not None and probe.captured_at < previous_capture:
                    issues.append(
                        self._issue(
                            "non_monotonic_image_sequence",
                            "filename order does not match capture timestamp order",
                            severity=IssueSeverity.WARNING,
                            drone_id=drone_id,
                            source=str(image_path),
                        )
                    )
                previous_capture = probe.captured_at

                duplicate_source = seen_checksums.get(checksum)
                if duplicate_source is not None:
                    issues.append(
                        self._issue(
                            "duplicate_image",
                            f"image duplicates {duplicate_source}",
                            drone_id=drone_id,
                            source=str(image_path),
                        )
                    )
                    continue
                seen_checksums[checksum] = str(image_path)

                nearest, offset_ms = self._nearest_sample(probe.captured_at, samples)
                within_skew = (
                    offset_ms is not None
                    and offset_ms <= round(request.max_telemetry_skew_seconds * 1000)
                )
                position = probe.position
                relative_altitude = probe.relative_altitude_m
                if nearest is not None and within_skew:
                    position = position or nearest.position
                    if relative_altitude is None:
                        relative_altitude = nearest.relative_altitude_m
                elif samples:
                    severity = (
                        IssueSeverity.WARNING
                        if position is not None and relative_altitude is not None
                        else IssueSeverity.ERROR
                    )
                    issues.append(
                        self._issue(
                            "telemetry_time_skew",
                            f"nearest telemetry exceeds {request.max_telemetry_skew_seconds:g} s",
                            severity=severity,
                            drone_id=drone_id,
                            source=str(image_path),
                        )
                    )

                if position is None:
                    issues.append(
                        self._issue(
                            "missing_gps",
                            "image has no GPS after telemetry synchronization",
                            drone_id=drone_id,
                            source=str(image_path),
                        )
                    )
                if relative_altitude is None:
                    issues.append(
                        self._issue(
                            "missing_relative_altitude",
                            "image has no relative altitude after telemetry synchronization",
                            drone_id=drone_id,
                            source=str(image_path),
                        )
                    )
                elif not MIN_ALTITUDE_M <= relative_altitude <= MAX_ALTITUDE_M:
                    issues.append(
                        self._issue(
                            "altitude_out_of_range",
                            f"relative altitude is outside {MIN_ALTITUDE_M:g}-{MAX_ALTITUDE_M:g} m",
                            severity=IssueSeverity.WARNING,
                            drone_id=drone_id,
                            source=str(image_path),
                        )
                    )

                camera = drone_source.camera_profile
                if camera is not None and (
                    (
                        camera.image_width_px is not None
                        and camera.image_width_px != probe.width_px
                    )
                    or (
                        camera.image_height_px is not None
                        and camera.image_height_px != probe.height_px
                    )
                ):
                    issues.append(
                        self._issue(
                            "camera_resolution_mismatch",
                            "image dimensions do not match the assigned camera profile",
                            severity=IssueSeverity.WARNING,
                            drone_id=drone_id,
                            source=str(image_path),
                        )
                    )

                sequence_index = image_counts[drone_id]
                profile_id = (
                    drone_source.camera_profile.profile_id if drone_source.camera_profile else None
                )
                asset_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        f"uav-crop-analysis:{mission.mission_id}:{drone_id}:{checksum}",
                    )
                )
                try:
                    asset = ImageAsset(
                        asset_id=asset_id,
                        mission_id=mission.mission_id,
                        drone_id=DroneId(drone_id),
                        source_path=image_path.resolve(),
                        sha256=checksum,
                        size_bytes=image_path.stat().st_size,
                        captured_at=probe.captured_at,
                        width_px=probe.width_px,
                        height_px=probe.height_px,
                        sequence_index=sequence_index,
                        position=position,
                        absolute_altitude_m=probe.absolute_altitude_m,
                        relative_altitude_m=relative_altitude,
                        telemetry_offset_ms=offset_ms if within_skew else None,
                        camera_profile_id=profile_id,
                    )
                except DomainValidationError as exc:
                    issues.append(
                        self._issue(
                            "invalid_image_metadata",
                            str(exc),
                            drone_id=drone_id,
                            source=str(image_path),
                        )
                    )
                    continue
                images.append(asset)
                image_counts[drone_id] += 1

        coverage = MetadataCoverage(
            image_count=len(images),
            timestamp_count=len(images),
            gps_count=sum(item.position is not None for item in images),
            altitude_count=sum(item.relative_altitude_m is not None for item in images),
        )
        issue_tuple = tuple(issues)
        has_errors = any(issue.severity is IssueSeverity.ERROR for issue in issue_tuple)
        persisted = False
        if not has_errors:
            self._repository.save_bundle(
                mission,
                tuple(sorted(camera_profiles.values(), key=lambda item: item.profile_id)),
                tuple(images),
                tuple(all_telemetry),
            )
            persisted = True

        return ImportReport(
            mission_id=mission.mission_id.value,
            images=tuple(images),
            telemetry_samples=tuple(all_telemetry),
            camera_profiles=tuple(
                sorted(camera_profiles.values(), key=lambda item: item.profile_id)
            ),
            issues=issue_tuple,
            image_counts_by_drone=image_counts,
            metadata_coverage=coverage,
            persisted=persisted,
        )

    @staticmethod
    def _image_files(image_dir: Path) -> tuple[Path, ...] | None:
        directory = Path(image_dir).expanduser().resolve()
        if not directory.is_dir():
            return None
        return tuple(
            sorted(
                (
                    path
                    for path in directory.iterdir()
                    if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
                ),
                key=lambda path: path.name.casefold(),
            )
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _nearest_sample(
        captured_at: datetime,
        samples: tuple[TelemetrySample, ...],
    ) -> tuple[TelemetrySample | None, int | None]:
        if not samples:
            return None, None
        timestamps = [item.recorded_at for item in samples]
        index = bisect_left(timestamps, captured_at)
        candidates = []
        if index < len(samples):
            candidates.append(samples[index])
        if index > 0:
            candidates.append(samples[index - 1])
        nearest = min(
            candidates,
            key=lambda item: abs((item.recorded_at - captured_at).total_seconds()),
        )
        offset_ms = round(abs((nearest.recorded_at - captured_at).total_seconds()) * 1000)
        return nearest, offset_ms

    @staticmethod
    def _issue(
        code: str,
        message: str,
        *,
        severity: IssueSeverity = IssueSeverity.ERROR,
        drone_id: str | None = None,
        source: str | None = None,
    ) -> ImportIssue:
        return ImportIssue(
            code=code,
            message=message,
            severity=severity,
            drone_id=drone_id,
            source=source,
        )
