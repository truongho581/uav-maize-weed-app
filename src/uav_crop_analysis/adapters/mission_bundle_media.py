"""Read media placed into an exported GreenEye mission bundle."""

from __future__ import annotations

import json
from pathlib import Path

from uav_crop_analysis.application import DroneImportSource, MissionImportRequest
from uav_crop_analysis.domain import CaptureMode, FlightProfile, SurveyMission
from uav_crop_analysis.errors import ImportDataError
from uav_crop_analysis.planning.serialization import plan_from_dict


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def has_greeneye_bundle_media(directory: Path) -> bool:
    """Return whether a mission folder has images in its expected media folders."""
    try:
        request = load_greeneye_bundle_media(directory)
    except ImportDataError:
        return False
    return any(
        any(
            path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            for path in source.image_dir.iterdir()
        )
        for source in request.sources
        if source.image_dir.is_dir()
    )


def load_greeneye_bundle_media(directory: Path) -> MissionImportRequest:
    """Build an import request from ``mission.json`` and ``media/<drone-id>``."""
    root = Path(directory).expanduser().resolve()
    mission_path = root / "mission.json"
    if not mission_path.is_file():
        raise ImportDataError(f"GreenEye mission.json was not found: {mission_path}")
    try:
        payload = json.loads(mission_path.read_text(encoding="utf-8"))
        plan = plan_from_dict(payload)
    except Exception as exc:
        raise ImportDataError(f"invalid GreenEye mission bundle: {root}") from exc

    drone_ids = tuple(route.drone_id for route in plan.routes)
    mission = SurveyMission.create(
        mission_id=plan.mission_id,
        name=plan.mission_id,
        drone_ids=drone_ids,
        flight_profile=FlightProfile(
            altitude_m=plan.profile.altitude_agl_m,
            gimbal_pitch_deg=plan.profile.gimbal_pitch_deg,
            forward_overlap=plan.profile.forward_overlap,
            side_overlap=plan.profile.side_overlap,
            capture_mode=CaptureMode.STOP_AND_CAPTURE,
        ),
    )
    sources = tuple(
        DroneImportSource(
            drone_id=assignment.drone_id,
            image_dir=root / "media" / assignment.drone_id.value,
            telemetry_file=_telemetry_path(root / "media" / assignment.drone_id.value),
        )
        for assignment in mission.assignments
    )
    return MissionImportRequest(mission=mission, sources=sources)


def _telemetry_path(media_directory: Path) -> Path | None:
    for name in ("telemetry.csv", "flight-log.csv"):
        candidate = media_directory / name
        if candidate.is_file():
            return candidate
    return None
