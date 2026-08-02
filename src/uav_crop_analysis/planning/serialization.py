"""Versioned JSON contract for persisted and exported GreenEye mission plans."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from uav_crop_analysis.domain import GeoPoint
from uav_crop_analysis.errors import MissionPlanningError
from uav_crop_analysis.planning.models import (
    MISSION_PLAN_SCHEMA_VERSION,
    CameraFootprint,
    CaptureAction,
    CaptureWaypoint,
    DroneRoute,
    MissionPlanningProfile,
    PlannedMission,
    PlanningWarning,
    SurveyArea,
)


MISSION_PLAN_KIND = "greeneye_mission_plan"


def plan_to_dict(plan: PlannedMission) -> dict[str, Any]:
    """Serialize a plan without machine-specific paths."""

    return {
        "schema_version": MISSION_PLAN_SCHEMA_VERSION,
        "kind": MISSION_PLAN_KIND,
        "mission_id": plan.mission_id,
        "generator_version": plan.generator_version,
        "survey_area": {
            "coordinate_reference_system": "EPSG:4326",
            "projected_crs": plan.survey_area.projected_crs,
            "polygon": [_point_to_dict(point) for point in plan.survey_area.polygon_wgs84],
        },
        "profile": _profile_to_dict(plan.profile),
        "camera": {
            "profile_id": plan.camera_profile_id,
            "profile_sha256": plan.camera_profile_sha256,
            "footprint": _footprint_to_dict(plan.camera_footprint),
        },
        "statistics": {
            "area_m2": plan.area_m2,
            "coverage_ratio": plan.coverage_ratio,
            "capture_count": plan.capture_count,
            "route_count": len(plan.routes),
            "effective_sweep_heading_deg": plan.effective_sweep_heading_deg,
            "export_ready": plan.export_ready,
        },
        "routes": [_route_to_dict(route) for route in plan.routes],
        "warnings": [
            {
                "code": warning.code,
                "message": warning.message,
                "drone_id": warning.drone_id,
            }
            for warning in plan.warnings
        ],
    }


def plan_from_dict(value: Mapping[str, Any]) -> PlannedMission:
    """Validate and deserialize the stable GreenEye plan contract."""

    root = _object(value, "plan")
    if _integer(root.get("schema_version"), "schema_version") != MISSION_PLAN_SCHEMA_VERSION:
        raise MissionPlanningError("unsupported GreenEye mission plan schema")
    if _text(root.get("kind"), "kind") != MISSION_PLAN_KIND:
        raise MissionPlanningError("GreenEye mission plan kind is invalid")

    area_data = _object(root.get("survey_area"), "survey_area")
    if _text(
        area_data.get("coordinate_reference_system"),
        "survey_area.coordinate_reference_system",
    ) != "EPSG:4326":
        raise MissionPlanningError("survey area coordinates must use EPSG:4326")
    polygon = tuple(
        _point(item, f"survey_area.polygon[{index}]")
        for index, item in enumerate(_array(area_data.get("polygon"), "survey_area.polygon"))
    )
    projected_value = area_data.get("projected_crs")
    projected_crs = (
        None
        if projected_value is None
        else _text(projected_value, "survey_area.projected_crs")
    )

    profile = _profile(_object(root.get("profile"), "profile"))
    camera = _object(root.get("camera"), "camera")
    footprint = _footprint(_object(camera.get("footprint"), "camera.footprint"))
    statistics = _object(root.get("statistics"), "statistics")
    routes = tuple(
        _route(item, f"routes[{index}]")
        for index, item in enumerate(_array(root.get("routes"), "routes"))
    )
    if len(routes) != profile.drone_count:
        raise MissionPlanningError("route count must match profile.drone_count")
    warnings = tuple(
        _warning(item, f"warnings[{index}]")
        for index, item in enumerate(_array(root.get("warnings"), "warnings"))
    )
    plan = PlannedMission(
        mission_id=_text(root.get("mission_id"), "mission_id"),
        survey_area=SurveyArea(polygon, projected_crs),
        profile=profile,
        camera_profile_id=_text(camera.get("profile_id"), "camera.profile_id"),
        camera_profile_sha256=_digest(
            camera.get("profile_sha256"), "camera.profile_sha256"
        ),
        camera_footprint=footprint,
        effective_sweep_heading_deg=_number(
            statistics.get("effective_sweep_heading_deg"),
            "statistics.effective_sweep_heading_deg",
        ),
        area_m2=_number(statistics.get("area_m2"), "statistics.area_m2"),
        coverage_ratio=_number(
            statistics.get("coverage_ratio"), "statistics.coverage_ratio"
        ),
        routes=routes,
        warnings=warnings,
        generator_version=_text(root.get("generator_version"), "generator_version"),
    )
    if _integer(statistics.get("capture_count"), "statistics.capture_count") != plan.capture_count:
        raise MissionPlanningError("stored capture_count does not match routes")
    if _integer(statistics.get("route_count"), "statistics.route_count") != len(plan.routes):
        raise MissionPlanningError("stored route_count does not match routes")
    if _boolean(statistics.get("export_ready"), "statistics.export_ready") != plan.export_ready:
        raise MissionPlanningError("stored export_ready does not match route waypoints")
    return plan


def _profile_to_dict(profile: MissionPlanningProfile) -> dict[str, Any]:
    return {
        "drone_count": profile.drone_count,
        "altitude_agl_m": profile.altitude_agl_m,
        "gimbal_pitch_deg": profile.gimbal_pitch_deg,
        "forward_overlap": profile.forward_overlap,
        "side_overlap": profile.side_overlap,
        "flight_speed_mps": profile.flight_speed_mps,
        "capture_pause_seconds": profile.capture_pause_seconds,
        "sweep_heading_deg": profile.sweep_heading_deg,
        "minimum_route_separation_m": profile.minimum_route_separation_m,
        "capture_mode": CaptureAction.STOP_AND_CAPTURE.value,
        "terrain_following": False,
    }


def _footprint_to_dict(footprint: CameraFootprint) -> dict[str, Any]:
    return {
        "horizontal_fov_deg": footprint.horizontal_fov_deg,
        "vertical_fov_deg": footprint.vertical_fov_deg,
        "ground_width_m": footprint.ground_width_m,
        "ground_height_m": footprint.ground_height_m,
        "lane_spacing_m": footprint.lane_spacing_m,
        "capture_spacing_m": footprint.capture_spacing_m,
        "gsd_x_cm_px": footprint.gsd_x_cm_px,
        "gsd_y_cm_px": footprint.gsd_y_cm_px,
    }


def _route_to_dict(route: DroneRoute) -> dict[str, Any]:
    return {
        "drone_id": route.drone_id,
        "home": None if route.home is None else _point_to_dict(route.home),
        "lane_indices": list(route.lane_indices),
        "estimated_distance_m": route.estimated_distance_m,
        "estimated_duration_seconds": route.estimated_duration_seconds,
        "waypoints": [
            {
                "sequence": waypoint.sequence,
                "position": _point_to_dict(waypoint.position),
                "altitude_agl_m": waypoint.altitude_agl_m,
                "hold_seconds": waypoint.hold_seconds,
                "lane_index": waypoint.lane_index,
                "action": waypoint.action.value,
            }
            for waypoint in route.waypoints
        ],
    }


def _point_to_dict(point: GeoPoint) -> dict[str, float]:
    return {"latitude": point.latitude, "longitude": point.longitude}


def _profile(data: Mapping[str, Any]) -> MissionPlanningProfile:
    capture_mode = _text(data.get("capture_mode"), "profile.capture_mode")
    if capture_mode != CaptureAction.STOP_AND_CAPTURE.value:
        raise MissionPlanningError("unsupported capture mode in mission plan")
    terrain_following = _boolean(
        data.get("terrain_following"), "profile.terrain_following"
    )
    if terrain_following:
        raise MissionPlanningError("terrain following is not supported by this planner")
    heading_value = data.get("sweep_heading_deg")
    return MissionPlanningProfile(
        drone_count=_integer(data.get("drone_count"), "profile.drone_count"),
        altitude_agl_m=_number(data.get("altitude_agl_m"), "profile.altitude_agl_m"),
        gimbal_pitch_deg=_number(
            data.get("gimbal_pitch_deg"), "profile.gimbal_pitch_deg"
        ),
        forward_overlap=_number(
            data.get("forward_overlap"), "profile.forward_overlap"
        ),
        side_overlap=_number(data.get("side_overlap"), "profile.side_overlap"),
        flight_speed_mps=_number(
            data.get("flight_speed_mps"), "profile.flight_speed_mps"
        ),
        capture_pause_seconds=_number(
            data.get("capture_pause_seconds"), "profile.capture_pause_seconds"
        ),
        sweep_heading_deg=(
            None
            if heading_value is None
            else _number(heading_value, "profile.sweep_heading_deg")
        ),
        minimum_route_separation_m=_number(
            data.get("minimum_route_separation_m"),
            "profile.minimum_route_separation_m",
        ),
    )


def _footprint(data: Mapping[str, Any]) -> CameraFootprint:
    return CameraFootprint(
        horizontal_fov_deg=_number(
            data.get("horizontal_fov_deg"), "camera.footprint.horizontal_fov_deg"
        ),
        vertical_fov_deg=_number(
            data.get("vertical_fov_deg"), "camera.footprint.vertical_fov_deg"
        ),
        ground_width_m=_number(
            data.get("ground_width_m"), "camera.footprint.ground_width_m"
        ),
        ground_height_m=_number(
            data.get("ground_height_m"), "camera.footprint.ground_height_m"
        ),
        lane_spacing_m=_number(
            data.get("lane_spacing_m"), "camera.footprint.lane_spacing_m"
        ),
        capture_spacing_m=_number(
            data.get("capture_spacing_m"), "camera.footprint.capture_spacing_m"
        ),
        gsd_x_cm_px=_optional_number(
            data.get("gsd_x_cm_px"), "camera.footprint.gsd_x_cm_px"
        ),
        gsd_y_cm_px=_optional_number(
            data.get("gsd_y_cm_px"), "camera.footprint.gsd_y_cm_px"
        ),
    )


def _route(value: object, field: str) -> DroneRoute:
    data = _object(value, field)
    home_value = data.get("home")
    home = None if home_value is None else _point(home_value, f"{field}.home")
    lanes = tuple(
        _integer(item, f"{field}.lane_indices[{index}]")
        for index, item in enumerate(
            _array(data.get("lane_indices"), f"{field}.lane_indices")
        )
    )
    waypoints = tuple(
        _waypoint(item, f"{field}.waypoints[{index}]")
        for index, item in enumerate(
            _array(data.get("waypoints"), f"{field}.waypoints")
        )
    )
    return DroneRoute(
        drone_id=_text(data.get("drone_id"), f"{field}.drone_id"),
        home=home,
        lane_indices=lanes,
        waypoints=waypoints,
        estimated_distance_m=_number(
            data.get("estimated_distance_m"), f"{field}.estimated_distance_m"
        ),
        estimated_duration_seconds=_number(
            data.get("estimated_duration_seconds"),
            f"{field}.estimated_duration_seconds",
        ),
    )


def _waypoint(value: object, field: str) -> CaptureWaypoint:
    data = _object(value, field)
    action = _text(data.get("action"), f"{field}.action")
    if action != CaptureAction.STOP_AND_CAPTURE.value:
        raise MissionPlanningError(f"{field}.action is unsupported")
    return CaptureWaypoint(
        sequence=_integer(data.get("sequence"), f"{field}.sequence"),
        position=_point(data.get("position"), f"{field}.position"),
        altitude_agl_m=_number(
            data.get("altitude_agl_m"), f"{field}.altitude_agl_m"
        ),
        hold_seconds=_number(data.get("hold_seconds"), f"{field}.hold_seconds"),
        lane_index=_integer(data.get("lane_index"), f"{field}.lane_index"),
    )


def _warning(value: object, field: str) -> PlanningWarning:
    data = _object(value, field)
    drone_value = data.get("drone_id")
    return PlanningWarning(
        code=_text(data.get("code"), f"{field}.code"),
        message=_text(data.get("message"), f"{field}.message"),
        drone_id=None if drone_value is None else _text(drone_value, f"{field}.drone_id"),
    )


def _point(value: object, field: str) -> GeoPoint:
    data = _object(value, field)
    return GeoPoint(
        _number(data.get("latitude"), f"{field}.latitude"),
        _number(data.get("longitude"), f"{field}.longitude"),
    )


def _object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MissionPlanningError(f"{field} must be an object")
    return value


def _array(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise MissionPlanningError(f"{field} must be an array")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MissionPlanningError(f"{field} must be a non-empty string")
    return value.strip()


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissionPlanningError(f"{field} must be a number")
    return float(value)


def _optional_number(value: object, field: str) -> float | None:
    return None if value is None else _number(value, field)


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MissionPlanningError(f"{field} must be an integer")
    return value


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise MissionPlanningError(f"{field} must be a boolean")
    return value


def _digest(value: object, field: str) -> str:
    digest = _text(value, field).lower()
    if len(digest) != 64:
        raise MissionPlanningError(f"{field} must be a SHA-256 digest")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise MissionPlanningError(f"{field} must be a SHA-256 digest") from exc
    return digest
