"""Deterministic stop-and-capture planner for one to three adjacent drone routes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import pairwise
import json
import math

from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.validation import explain_validity

from uav_crop_analysis.domain import CameraProfile, GeoPoint
from uav_crop_analysis.errors import MissionPlanningError
from uav_crop_analysis.planning.models import (
    CameraFootprint,
    CaptureWaypoint,
    DroneRoute,
    MissionPlanningProfile,
    MissionPlanningRequest,
    PlannedMission,
    PlanningWarning,
    SurveyArea,
)


MAX_LANE_SEGMENTS = 10_000
# A 10 m nadir survey can legitimately contain far more than 100,000
# stop-and-capture positions for a large field.  Keep a guardrail for malformed
# boundaries, but do not reject normal multi-hectare surveys merely because the
# capture grid is dense.
MAX_CAPTURE_POINTS = 500_000
MIN_SURVEY_AREA_M2 = 1.0
MIN_ACCEPTED_COVERAGE_RATIO = 0.999


@dataclass(frozen=True, slots=True)
class _Lane:
    lane_index: int
    points_xy: tuple[tuple[float, float], ...]
    length_m: float


class GridMissionPlanner:
    """Create clipped parallel transects and balance contiguous lanes by workload."""

    def plan(self, request: MissionPlanningRequest) -> PlannedMission:
        polygon_wgs84 = _polygon(request.survey_area)
        projected_crs = _projected_crs(request.survey_area, polygon_wgs84.centroid)
        to_projected = Transformer.from_crs("EPSG:4326", projected_crs, always_xy=True)
        to_wgs84 = Transformer.from_crs(projected_crs, "EPSG:4326", always_xy=True)
        polygon_projected = transform(to_projected.transform, polygon_wgs84)
        if polygon_projected.area < MIN_SURVEY_AREA_M2:
            raise MissionPlanningError(
                f"survey polygon area must be at least {MIN_SURVEY_AREA_M2:g} m2",
                context={"area_m2": polygon_projected.area},
            )

        footprint = calculate_camera_footprint(
            request.camera,
            request.profile,
            image_size_px=request.image_size_px,
        )
        heading = (
            request.profile.sweep_heading_deg
            if request.profile.sweep_heading_deg is not None
            else _automatic_heading(polygon_projected)
        )
        center = (polygon_projected.centroid.x, polygon_projected.centroid.y)
        rotation_deg = heading - 90.0
        aligned = affinity.rotate(polygon_projected, rotation_deg, origin=center)
        lanes = _generate_lanes(aligned, footprint)
        if len(lanes) < request.profile.drone_count:
            raise MissionPlanningError(
                "survey area produces fewer flight lanes than selected drones",
                context={
                    "lane_count": len(lanes),
                    "drone_count": request.profile.drone_count,
                },
            )

        coverage_ratio = _coverage_ratio(aligned, lanes, footprint)
        if coverage_ratio < MIN_ACCEPTED_COVERAGE_RATIO:
            raise MissionPlanningError(
                "generated capture grid does not cover the survey polygon",
                context={"coverage_ratio": coverage_ratio},
            )

        groups = _partition_lanes(lanes, request.profile)
        routes = tuple(
            _route(
                drone_id,
                group,
                request.profile,
                center,
                -rotation_deg,
                to_projected,
                to_wgs84,
            )
            for drone_id, group in zip(
                request.drone_ids,
                groups,
                strict=True,
            )
        )
        warnings = _warnings(routes, request.profile, footprint)
        return PlannedMission(
            mission_id=request.mission_id,
            survey_area=SurveyArea(
                request.survey_area.polygon_wgs84,
                projected_crs.to_string(),
            ),
            profile=request.profile,
            camera_profile_id=request.camera.profile_id,
            camera_profile_sha256=_camera_profile_sha256(request.camera),
            camera_footprint=footprint,
            effective_sweep_heading_deg=round(heading, 6),
            area_m2=round(polygon_projected.area, 3),
            coverage_ratio=round(coverage_ratio, 9),
            routes=routes,
            warnings=warnings,
        )


def _camera_profile_sha256(camera: CameraProfile) -> str:
    payload = {
        "distortion_coefficients": list(camera.distortion_coefficients),
        "focal_length_mm": camera.focal_length_mm,
        "horizontal_fov_deg": camera.horizontal_fov_deg,
        "image_height_px": camera.image_height_px,
        "image_width_px": camera.image_width_px,
        "make": camera.make,
        "model": camera.model,
        "name": camera.name,
        "profile_id": camera.profile_id,
        "vertical_fov_deg": camera.vertical_fov_deg,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def calculate_camera_footprint(
    camera: CameraProfile,
    profile: MissionPlanningProfile,
    *,
    image_size_px: tuple[int, int] | None = None,
) -> CameraFootprint:
    """Calculate nadir ground footprint and spacing from persisted camera metadata."""

    size = image_size_px
    if size is None and camera.image_width_px and camera.image_height_px:
        size = camera.image_width_px, camera.image_height_px
    if size is not None and (size[0] <= 0 or size[1] <= 0):
        raise MissionPlanningError("camera image dimensions must be positive")

    horizontal_fov = camera.horizontal_fov_deg
    vertical_fov = camera.vertical_fov_deg
    if horizontal_fov is None and vertical_fov is not None and size is not None:
        aspect_ratio = size[0] / size[1]
        horizontal_fov = math.degrees(
            2.0 * math.atan(math.tan(math.radians(vertical_fov) / 2.0) * aspect_ratio)
        )
    if vertical_fov is None and horizontal_fov is not None and size is not None:
        aspect_ratio = size[0] / size[1]
        vertical_fov = math.degrees(
            2.0 * math.atan(math.tan(math.radians(horizontal_fov) / 2.0) / aspect_ratio)
        )
    if horizontal_fov is None or vertical_fov is None:
        raise MissionPlanningError(
            "camera requires horizontal/vertical FOV or one FOV plus image aspect ratio",
            context={"camera_profile_id": camera.profile_id},
        )

    altitude = profile.altitude_agl_m
    width_m = 2.0 * altitude * math.tan(math.radians(horizontal_fov) / 2.0)
    height_m = 2.0 * altitude * math.tan(math.radians(vertical_fov) / 2.0)
    lane_spacing = width_m * (1.0 - profile.side_overlap)
    capture_spacing = height_m * (1.0 - profile.forward_overlap)
    if lane_spacing <= 0 or capture_spacing <= 0:
        raise MissionPlanningError("camera footprint spacing must be positive")
    gsd_x = width_m / size[0] * 100.0 if size is not None else None
    gsd_y = height_m / size[1] * 100.0 if size is not None else None
    return CameraFootprint(
        horizontal_fov_deg=round(horizontal_fov, 6),
        vertical_fov_deg=round(vertical_fov, 6),
        ground_width_m=round(width_m, 6),
        ground_height_m=round(height_m, 6),
        lane_spacing_m=round(lane_spacing, 6),
        capture_spacing_m=round(capture_spacing, 6),
        gsd_x_cm_px=round(gsd_x, 6) if gsd_x is not None else None,
        gsd_y_cm_px=round(gsd_y, 6) if gsd_y is not None else None,
    )


def _polygon(area: SurveyArea) -> Polygon:
    polygon = Polygon(
        (point.longitude, point.latitude) for point in area.polygon_wgs84
    )
    if polygon.is_empty or not polygon.is_valid:
        raise MissionPlanningError(
            f"survey polygon is invalid: {explain_validity(polygon)}"
        )
    return polygon


def _projected_crs(area: SurveyArea, centroid: Point) -> CRS:
    try:
        if area.projected_crs is not None:
            crs = CRS.from_user_input(area.projected_crs)
            if not crs.is_projected:
                raise MissionPlanningError("survey projected_crs must use metre coordinates")
            axis_units = {axis.unit_name.casefold() for axis in crs.axis_info}
            if not any("metre" in unit or "meter" in unit for unit in axis_units):
                raise MissionPlanningError("survey projected_crs axes must use metres")
            return crs
        longitude = centroid.x
        latitude = centroid.y
        if latitude >= 84:
            return CRS.from_epsg(3413)
        if latitude <= -80:
            return CRS.from_epsg(3031)
        zone = max(1, min(60, int(math.floor((longitude + 180.0) / 6.0)) + 1))
        return CRS.from_epsg((32600 if latitude >= 0 else 32700) + zone)
    except (ProjError, ValueError) as exc:
        raise MissionPlanningError("cannot resolve survey projected CRS") from exc


def _automatic_heading(polygon: Polygon) -> float:
    coordinates = list(polygon.convex_hull.exterior.coords)
    candidates: list[tuple[float, bool, float]] = []
    center = (polygon.centroid.x, polygon.centroid.y)
    for first, second in pairwise(coordinates):
        dx = second[0] - first[0]
        dy = second[1] - first[1]
        if math.hypot(dx, dy) <= 1e-9:
            continue
        heading = math.degrees(math.atan2(dx, dy)) % 180.0
        aligned = affinity.rotate(polygon, heading - 90.0, origin=center)
        min_x, min_y, max_x, max_y = aligned.bounds
        width = max_x - min_x
        height = max_y - min_y
        candidates.append((width * height, width >= height, heading))
    if not candidates:
        raise MissionPlanningError("survey polygon has no usable edge for sweep heading")
    minimum_box_area = min(area for area, _long_axis, _heading in candidates)
    best = [
        (long_axis, heading)
        for area, long_axis, heading in candidates
        if abs(area - minimum_box_area) <= max(1e-6, minimum_box_area * 1e-9)
    ]
    long_axis_headings = [heading for long_axis, heading in best if long_axis]
    return min(long_axis_headings or [heading for _long_axis, heading in best])


def _generate_lanes(polygon: Polygon, footprint: CameraFootprint) -> tuple[_Lane, ...]:
    min_x, min_y, max_x, max_y = polygon.bounds
    y_positions = _axis_positions(
        min_y,
        max_y,
        footprint.ground_width_m,
        footprint.lane_spacing_m,
    )
    lanes: list[_Lane] = []
    for row_index, y_value in enumerate(y_positions):
        guide = LineString(
            (
                (min_x - footprint.ground_height_m, y_value),
                (max_x + footprint.ground_height_m, y_value),
            )
        )
        segments = sorted(
            _line_segments(polygon.intersection(guide)),
            key=lambda item: item.bounds[0],
        )
        if row_index % 2:
            segments.reverse()
        for segment in segments:
            points = _capture_points(segment, footprint)
            if row_index % 2:
                points = tuple(reversed(points))
            if not points:
                continue
            lanes.append(_Lane(len(lanes), points, segment.length))
            if len(lanes) > MAX_LANE_SEGMENTS:
                raise MissionPlanningError("capture grid exceeds maximum lane count")
    if not lanes:
        raise MissionPlanningError("survey polygon does not produce any flight lane")
    capture_count = sum(len(lane.points_xy) for lane in lanes)
    if capture_count > MAX_CAPTURE_POINTS:
        raise MissionPlanningError(
            "Lưới chụp có "
            f"{capture_count:,} điểm, vượt giới hạn {MAX_CAPTURE_POINTS:,} điểm. "
            "Hãy chia khu khảo sát thành nhiều nhiệm vụ hoặc tăng độ cao bay/giảm chồng ảnh.",
            context={
                "capture_count": capture_count,
                "maximum_capture_points": MAX_CAPTURE_POINTS,
            },
        )
    return tuple(lanes)


def _axis_positions(
    minimum: float,
    maximum: float,
    footprint_size: float,
    spacing: float,
) -> tuple[float, ...]:
    span = maximum - minimum
    if span <= footprint_size:
        return ((minimum + maximum) / 2.0,)
    start = minimum + footprint_size / 2.0
    end = maximum - footprint_size / 2.0
    distance = end - start
    interval_count = max(1, math.ceil(distance / spacing))
    return tuple(start + distance * index / interval_count for index in range(interval_count + 1))


def _line_segments(geometry: BaseGeometry) -> tuple[LineString, ...]:
    if geometry.is_empty:
        return ()
    if isinstance(geometry, LineString):
        return (geometry,) if geometry.length > 1e-6 else ()
    return tuple(
        part
        for part in getattr(geometry, "geoms", ())
        if isinstance(part, LineString) and part.length > 1e-6
    )


def _capture_points(
    segment: LineString,
    footprint: CameraFootprint,
) -> tuple[tuple[float, float], ...]:
    length = segment.length
    if length <= footprint.ground_height_m:
        point = segment.interpolate(0.5, normalized=True)
        return ((point.x, point.y),)
    start_distance = footprint.ground_height_m / 2.0
    end_distance = length - footprint.ground_height_m / 2.0
    usable = end_distance - start_distance
    interval_count = max(1, math.ceil(usable / footprint.capture_spacing_m))
    return tuple(
        (point.x, point.y)
        for point in (
            segment.interpolate(start_distance + usable * index / interval_count)
            for index in range(interval_count + 1)
        )
    )


def _coverage_ratio(
    polygon: Polygon,
    lanes: tuple[_Lane, ...],
    footprint: CameraFootprint,
) -> float:
    half_height = footprint.ground_height_m / 2.0
    half_width = footprint.ground_width_m / 2.0
    footprints = (
        box(x - half_height, y - half_width, x + half_height, y + half_width)
        for lane in lanes
        for x, y in lane.points_xy
    )
    covered = unary_union(tuple(footprints)).intersection(polygon).area
    return min(1.0, covered / polygon.area)


def _partition_lanes(
    lanes: tuple[_Lane, ...],
    profile: MissionPlanningProfile,
) -> tuple[tuple[_Lane, ...], ...]:
    weights = tuple(
        lane.length_m
        + len(lane.points_xy) * profile.capture_pause_seconds * profile.flight_speed_mps
        for lane in lanes
    )
    boundaries = _balanced_boundaries(weights, profile.drone_count)
    return tuple(lanes[start:end] for start, end in pairwise(boundaries))


def _balanced_boundaries(weights: tuple[float, ...], group_count: int) -> tuple[int, ...]:
    item_count = len(weights)
    prefix = [0.0]
    for weight in weights:
        prefix.append(prefix[-1] + weight)
    costs = [[math.inf] * (item_count + 1) for _ in range(group_count + 1)]
    splits = [[0] * (item_count + 1) for _ in range(group_count + 1)]
    costs[0][0] = 0.0
    for groups in range(1, group_count + 1):
        for end in range(groups, item_count + 1):
            for split in range(groups - 1, end):
                candidate = max(costs[groups - 1][split], prefix[end] - prefix[split])
                if candidate < costs[groups][end] - 1e-9:
                    costs[groups][end] = candidate
                    splits[groups][end] = split
    boundaries = [item_count]
    end = item_count
    for groups in range(group_count, 0, -1):
        end = splits[groups][end]
        boundaries.append(end)
    return tuple(reversed(boundaries))


def _route(
    drone_id: str,
    lanes: tuple[_Lane, ...],
    profile: MissionPlanningProfile,
    rotation_origin: tuple[float, float],
    inverse_rotation_deg: float,
    to_projected: Transformer,
    to_wgs84: Transformer,
) -> DroneRoute:
    projected_by_lane = tuple(
        (
            lane,
            tuple(
                _rotate_xy(point, inverse_rotation_deg, rotation_origin)
                for point in lane.points_xy
            ),
        )
        for lane in lanes
    )
    projected_points = tuple(
        point for _lane, lane_points in projected_by_lane for point in lane_points
    )
    waypoints: list[CaptureWaypoint] = []
    for lane, lane_points in projected_by_lane:
        for point in lane_points:
            longitude, latitude = to_wgs84.transform(*point)
            waypoints.append(
                CaptureWaypoint(
                    sequence=len(waypoints),
                    position=GeoPoint(latitude, longitude),
                    altitude_agl_m=profile.altitude_agl_m,
                    hold_seconds=profile.capture_pause_seconds,
                    lane_index=lane.lane_index,
                )
            )
    # The exported QGroundControl mission contains only the capture route.
    # ``plannedHomePosition`` is metadata, not an explicit flight leg, and can
    # be an old/default location far from the current field.  Including it
    # here produced impossible survey estimates (thousands of minutes) while
    # the aircraft was only expected to scan the field.
    distance = _path_distance(projected_points)
    duration = distance / profile.flight_speed_mps + len(waypoints) * profile.capture_pause_seconds
    return DroneRoute(
        drone_id=drone_id,
        # Technical anchor required by QGroundControl's file format. Actual
        # home/take-off/return behavior belongs to the flight controller.
        home=waypoints[0].position,
        lane_indices=tuple(lane.lane_index for lane in lanes),
        waypoints=tuple(waypoints),
        estimated_distance_m=round(distance, 3),
        estimated_duration_seconds=round(duration, 3),
    )


def _rotate_xy(
    point: tuple[float, float],
    angle_deg: float,
    origin: tuple[float, float],
) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    translated_x = point[0] - origin[0]
    translated_y = point[1] - origin[1]
    return (
        origin[0] + translated_x * cosine - translated_y * sine,
        origin[1] + translated_x * sine + translated_y * cosine,
    )


def _path_distance(points: tuple[tuple[float, float], ...]) -> float:
    return sum(math.dist(first, second) for first, second in pairwise(points))


def _warnings(
    routes: tuple[DroneRoute, ...],
    profile: MissionPlanningProfile,
    footprint: CameraFootprint,
) -> tuple[PlanningWarning, ...]:
    warnings = [
        PlanningWarning(
            "fixed_agl_without_terrain",
            "Altitude is fixed AGL; terrain following is not applied.",
        )
    ]
    if len(routes) > 1 and footprint.lane_spacing_m < profile.minimum_route_separation_m:
        warnings.append(
            PlanningWarning(
                "route_separation_below_minimum",
                "Adjacent flight lanes are closer than the configured route separation.",
            )
        )
    durations = [route.estimated_duration_seconds for route in routes]
    if len(durations) > 1 and min(durations) > 0 and max(durations) / min(durations) > 1.5:
        warnings.append(
            PlanningWarning(
                "route_workload_imbalance",
                "Estimated route duration differs by more than 50 percent between drones.",
            )
        )
    return tuple(warnings)
