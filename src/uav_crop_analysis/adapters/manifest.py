"""Canonical mission.json serialization independent of real folder conventions."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from uav_crop_analysis.application.import_models import (
    DroneImportSource,
    MissionImportRequest,
    TelemetryCsvMapping,
    TimestampFormat,
)
from uav_crop_analysis.domain import (
    MAX_DRONE_COUNT,
    MIN_DRONE_COUNT,
    CameraProfile,
    CaptureMode,
    DroneId,
    FlightProfile,
    SurveyMission,
)
from uav_crop_analysis.errors import ImportDataError


MANIFEST_SCHEMA_VERSION = 1


def write_mission_manifest(request: MissionImportRequest, output_path: Path) -> None:
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    base = path.parent
    mission = request.mission
    lane_by_drone = {
        assignment.drone_id.value: assignment.lane_index
        for assignment in mission.assignments
    }
    source_ids = {source.drone_id.value for source in request.sources}
    if source_ids != set(lane_by_drone):
        raise ImportDataError(
            "manifest sources must match the assigned mission drones",
            context={"source_ids": sorted(source_ids)},
        )
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "mission": {
            "mission_id": mission.mission_id.value,
            "name": mission.name,
            "created_at": mission.created_at.isoformat(),
            "flight_profile": {
                "altitude_m": mission.flight_profile.altitude_m,
                "gimbal_pitch_deg": mission.flight_profile.gimbal_pitch_deg,
                "forward_overlap": mission.flight_profile.forward_overlap,
                "side_overlap": mission.flight_profile.side_overlap,
                "capture_mode": mission.flight_profile.capture_mode.value,
            },
        },
        "max_telemetry_skew_seconds": request.max_telemetry_skew_seconds,
        "drones": [
            _source_to_dict(source, base, lane_by_drone[source.drone_id.value])
            for source in request.sources
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_mission_manifest(manifest_path: Path) -> MissionImportRequest:
    path = Path(manifest_path).expanduser().resolve()
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if payload["schema_version"] != MANIFEST_SCHEMA_VERSION:
            raise ImportDataError(
                f"unsupported mission manifest schema: {payload['schema_version']}",
                context={"source": str(path)},
            )
        mission_data = payload["mission"]
        profile_data = mission_data["flight_profile"]
        drone_rows = payload["drones"]
        if not isinstance(drone_rows, list):
            raise ImportDataError("mission manifest drones must be a list")
        drone_count = len(drone_rows)
        if not MIN_DRONE_COUNT <= drone_count <= MAX_DRONE_COUNT:
            raise ImportDataError(
                f"mission manifest must define {MIN_DRONE_COUNT} to "
                f"{MAX_DRONE_COUNT} drones"
            )
        sorted_rows = sorted(drone_rows, key=lambda row: row["lane_index"])
        lane_indices = [row["lane_index"] for row in sorted_rows]
        if lane_indices != list(range(drone_count)):
            raise ImportDataError(
                f"mission manifest lane indices must be 0..{drone_count - 1}"
            )
        drone_ids = tuple(row["drone_id"] for row in sorted_rows)
        mission = SurveyMission.create(
            mission_id=mission_data["mission_id"],
            name=mission_data["name"],
            drone_ids=drone_ids,
            flight_profile=FlightProfile(
                altitude_m=profile_data["altitude_m"],
                gimbal_pitch_deg=profile_data["gimbal_pitch_deg"],
                forward_overlap=profile_data["forward_overlap"],
                side_overlap=profile_data["side_overlap"],
                capture_mode=CaptureMode(profile_data["capture_mode"]),
            ),
            created_at=datetime.fromisoformat(mission_data["created_at"]),
        )
        sources = tuple(_source_from_dict(row, path.parent) for row in drone_rows)
        return MissionImportRequest(
            mission=mission,
            sources=sources,
            max_telemetry_skew_seconds=float(payload.get("max_telemetry_skew_seconds", 2.0)),
        )
    except ImportDataError:
        raise
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ImportDataError(
            f"invalid mission manifest: {path}",
            context={"source": str(path)},
        ) from exc


def _portable_path(path: Path, base: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(base))
    except ValueError:
        return str(resolved)


def _source_to_dict(
    source: DroneImportSource,
    base: Path,
    lane_index: int,
) -> dict[str, Any]:
    mapping = source.telemetry_mapping
    return {
        "drone_id": source.drone_id.value,
        "lane_index": lane_index,
        "image_dir": _portable_path(source.image_dir, base),
        "telemetry_file": (
            _portable_path(source.telemetry_file, base) if source.telemetry_file else None
        ),
        "telemetry_mapping": {
            "timestamp_column": mapping.timestamp_column,
            "latitude_column": mapping.latitude_column,
            "longitude_column": mapping.longitude_column,
            "relative_altitude_column": mapping.relative_altitude_column,
            "timestamp_format": mapping.timestamp_format.value,
        },
        "camera_profile": _camera_to_dict(source.camera_profile),
    }


def _source_from_dict(row: dict[str, Any], base: Path) -> DroneImportSource:
    mapping = row.get("telemetry_mapping", {})
    telemetry_value = row.get("telemetry_file")
    camera_value = row.get("camera_profile")
    image_dir = Path(row["image_dir"])
    telemetry_file = Path(telemetry_value) if telemetry_value else None
    return DroneImportSource(
        drone_id=DroneId(row["drone_id"]),
        image_dir=image_dir if image_dir.is_absolute() else base / image_dir,
        telemetry_file=(
            telemetry_file
            if telemetry_file is None or telemetry_file.is_absolute()
            else base / telemetry_file
        ),
        telemetry_mapping=TelemetryCsvMapping(
            timestamp_column=mapping.get("timestamp_column", "timestamp"),
            latitude_column=mapping.get("latitude_column", "latitude"),
            longitude_column=mapping.get("longitude_column", "longitude"),
            relative_altitude_column=mapping.get(
                "relative_altitude_column", "relative_altitude_m"
            ),
            timestamp_format=TimestampFormat(mapping.get("timestamp_format", "iso8601")),
        ),
        camera_profile=_camera_from_dict(camera_value) if camera_value else None,
    )


def _camera_to_dict(profile: CameraProfile | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    return {
        "profile_id": profile.profile_id,
        "name": profile.name,
        "make": profile.make,
        "model": profile.model,
        "image_width_px": profile.image_width_px,
        "image_height_px": profile.image_height_px,
        "focal_length_mm": profile.focal_length_mm,
        "horizontal_fov_deg": profile.horizontal_fov_deg,
        "vertical_fov_deg": profile.vertical_fov_deg,
        "distortion_coefficients": list(profile.distortion_coefficients),
    }


def _camera_from_dict(value: dict[str, Any]) -> CameraProfile:
    return CameraProfile(
        profile_id=value["profile_id"],
        name=value["name"],
        make=value.get("make"),
        model=value.get("model"),
        image_width_px=value.get("image_width_px"),
        image_height_px=value.get("image_height_px"),
        focal_length_mm=value.get("focal_length_mm"),
        horizontal_fov_deg=value.get("horizontal_fov_deg"),
        vertical_fov_deg=value.get("vertical_fov_deg"),
        distortion_coefficients=tuple(value.get("distortion_coefficients", ())),
    )
