from __future__ import annotations

import math

from pyproj import Transformer
import pytest
from shapely import affinity
from shapely.geometry import Point, Polygon

from uav_crop_analysis.domain import CameraProfile, GeoPoint
from uav_crop_analysis.errors import MissionPlanningError
from uav_crop_analysis.planning import (
    CaptureAction,
    GridMissionPlanner,
    MissionPlanningProfile,
    MissionPlanningRequest,
    SurveyArea,
    calculate_camera_footprint,
)


PROJECTED_CRS = "EPSG:32648"
TO_WGS84 = Transformer.from_crs(PROJECTED_CRS, "EPSG:4326", always_xy=True)
TO_PROJECTED = Transformer.from_crs("EPSG:4326", PROJECTED_CRS, always_xy=True)
RECTANGLE = (
    (500_000.0, 1_200_000.0),
    (500_080.0, 1_200_000.0),
    (500_080.0, 1_200_050.0),
    (500_000.0, 1_200_050.0),
)
CONCAVE = (
    (500_000.0, 1_200_000.0),
    (500_080.0, 1_200_000.0),
    (500_080.0, 1_200_020.0),
    (500_040.0, 1_200_020.0),
    (500_040.0, 1_200_060.0),
    (500_000.0, 1_200_060.0),
)


def _area(coordinates: tuple[tuple[float, float], ...]) -> SurveyArea:
    points = tuple(
        GeoPoint(latitude, longitude)
        for longitude, latitude in (
            TO_WGS84.transform(x_value, y_value) for x_value, y_value in coordinates
        )
    )
    return SurveyArea(points)


def _camera(*, horizontal_fov: float = 82.0, vertical_fov: float = 62.0) -> CameraProfile:
    return CameraProfile(
        profile_id=f"camera-{horizontal_fov:g}",
        name="RGB planning camera",
        horizontal_fov_deg=horizontal_fov,
        vertical_fov_deg=vertical_fov,
        image_width_px=4000,
        image_height_px=3000,
    )


def _request(
    coordinates: tuple[tuple[float, float], ...] = RECTANGLE,
    *,
    drone_count: int = 1,
    camera: CameraProfile | None = None,
    heading: float | None = 90.0,
    include_homes: bool = True,
) -> MissionPlanningRequest:
    area = _area(coordinates)
    drone_ids = tuple(f"drone-{index + 1}" for index in range(drone_count))
    homes = (area.polygon_wgs84[0],) * drone_count if include_homes else ()
    return MissionPlanningRequest(
        mission_id=f"planning-{drone_count}",
        survey_area=area,
        profile=MissionPlanningProfile(
            drone_count=drone_count,
            sweep_heading_deg=heading,
        ),
        camera=camera or _camera(),
        drone_ids=drone_ids,
        homes=homes,
    )


def test_camera_footprint_infers_vertical_fov_and_reports_gsd() -> None:
    camera = CameraProfile(
        "camera-hfov",
        "Camera with horizontal FOV",
        horizontal_fov_deg=82.0,
    )
    profile = MissionPlanningProfile()

    footprint = calculate_camera_footprint(
        camera,
        profile,
        image_size_px=(4000, 3000),
    )

    expected_width = 2.0 * 10.0 * math.tan(math.radians(82.0) / 2.0)
    expected_vertical_fov = math.degrees(
        2.0 * math.atan(math.tan(math.radians(82.0) / 2.0) / (4.0 / 3.0))
    )
    assert footprint.ground_width_m == pytest.approx(expected_width, abs=1e-6)
    assert footprint.vertical_fov_deg == pytest.approx(expected_vertical_fov, abs=1e-6)
    assert footprint.gsd_x_cm_px == pytest.approx(expected_width / 4000 * 100, abs=1e-6)
    assert footprint.lane_spacing_m == pytest.approx(
        expected_width * (1.0 - profile.side_overlap),
        abs=1e-6,
    )


def test_camera_footprint_rejects_insufficient_camera_geometry() -> None:
    camera = CameraProfile("camera-focal", "Focal only", focal_length_mm=4.5)

    with pytest.raises(MissionPlanningError, match="requires horizontal/vertical FOV"):
        calculate_camera_footprint(camera, MissionPlanningProfile())


@pytest.mark.parametrize("drone_count", [1, 2, 3])
def test_rectangle_plan_supports_one_to_three_contiguous_routes(
    drone_count: int,
) -> None:
    request = _request(drone_count=drone_count)

    plan = GridMissionPlanner().plan(request)

    assert len(plan.routes) == drone_count
    assert plan.area_m2 == pytest.approx(4000.0, abs=0.02)
    assert plan.coverage_ratio >= 0.999999
    assert plan.effective_sweep_heading_deg == 90.0
    assert plan.export_ready
    assert plan.capture_count > 0
    lane_groups = [route.lane_indices for route in plan.routes]
    flat_lanes = tuple(lane for group in lane_groups for lane in group)
    assert flat_lanes == tuple(range(len(flat_lanes)))
    assert all(
        tuple(range(group[0], group[-1] + 1)) == group for group in lane_groups
    )
    polygon = Polygon(RECTANGLE).buffer(1e-5)
    for route in plan.routes:
        assert route.estimated_distance_m > 0
        assert route.estimated_duration_seconds > 0
        assert [waypoint.sequence for waypoint in route.waypoints] == list(
            range(len(route.waypoints))
        )
        assert all(
            waypoint.action is CaptureAction.STOP_AND_CAPTURE
            for waypoint in route.waypoints
        )
        for waypoint in route.waypoints:
            x_value, y_value = TO_PROJECTED.transform(
                waypoint.position.longitude,
                waypoint.position.latitude,
            )
            assert polygon.covers(Point(x_value, y_value))
    durations = [route.estimated_duration_seconds for route in plan.routes]
    if drone_count > 1:
        # A contiguous allocation cannot always split an odd number of flight
        # lanes equally.  An unavoidable imbalance must be surfaced to the user.
        if max(durations) / min(durations) > 1.5:
            assert "route_workload_imbalance" in {
                warning.code for warning in plan.warnings
            }


def test_planner_output_is_deterministic() -> None:
    planner = GridMissionPlanner()
    request = _request(drone_count=3)

    assert planner.plan(request) == planner.plan(request)


def test_concave_polygon_has_no_blind_area_under_footprint_model() -> None:
    plan = GridMissionPlanner().plan(_request(CONCAVE, drone_count=3, heading=None))

    assert plan.area_m2 == pytest.approx(3200.0, abs=0.02)
    assert plan.coverage_ratio >= 0.999999
    assert plan.capture_count > 0
    assert len(plan.routes) == 3


def test_automatic_heading_follows_long_axis_of_rotated_field() -> None:
    polygon = affinity.rotate(Polygon(RECTANGLE), 27.0, origin="centroid")
    rotated = tuple(polygon.exterior.coords)[:-1]

    plan = GridMissionPlanner().plan(_request(rotated, heading=None))

    assert plan.effective_sweep_heading_deg == pytest.approx(63.0, abs=0.01)
    assert plan.coverage_ratio >= 0.999


def test_narrower_camera_footprint_produces_more_lanes_and_captures() -> None:
    planner = GridMissionPlanner()
    wide = planner.plan(_request(camera=_camera(horizontal_fov=82.0)))
    narrow = planner.plan(_request(camera=_camera(horizontal_fov=55.0)))

    assert narrow.camera_footprint.lane_spacing_m < wide.camera_footprint.lane_spacing_m
    assert len(narrow.routes[0].lane_indices) > len(wide.routes[0].lane_indices)
    assert narrow.capture_count > wide.capture_count


def test_missing_homes_do_not_block_export() -> None:
    plan = GridMissionPlanner().plan(_request(drone_count=2, include_homes=False))

    assert plan.export_ready
    assert all(route.home == route.waypoints[0].position for route in plan.routes)


def test_survey_duration_does_not_include_planned_home_transit() -> None:
    """Home metadata must not turn an imaging estimate into an intercity trip."""

    request_without_home = _request(include_homes=False)
    request_with_distant_home = MissionPlanningRequest(
        mission_id=request_without_home.mission_id,
        survey_area=request_without_home.survey_area,
        profile=request_without_home.profile,
        camera=request_without_home.camera,
        drone_ids=request_without_home.drone_ids,
        homes=(GeoPoint(21.1136358, 105.8391603),),
    )

    survey_only = GridMissionPlanner().plan(request_without_home)
    with_home = GridMissionPlanner().plan(request_with_distant_home)

    assert with_home.routes[0].home == with_home.routes[0].waypoints[0].position
    assert with_home.routes[0].estimated_distance_m == pytest.approx(
        survey_only.routes[0].estimated_distance_m
    )
    assert with_home.routes[0].estimated_duration_seconds == pytest.approx(
        survey_only.routes[0].estimated_duration_seconds
    )


def test_route_separation_warning_uses_configured_minimum() -> None:
    request = _request(drone_count=2)
    request = MissionPlanningRequest(
        request.mission_id,
        request.survey_area,
        MissionPlanningProfile(
            drone_count=2,
            sweep_heading_deg=90.0,
            minimum_route_separation_m=20.0,
        ),
        request.camera,
        request.drone_ids,
        request.homes,
    )

    plan = GridMissionPlanner().plan(request)

    assert "route_separation_below_minimum" in {
        warning.code for warning in plan.warnings
    }


def test_planner_rejects_self_intersecting_polygon() -> None:
    bow_tie = (
        RECTANGLE[0],
        RECTANGLE[2],
        RECTANGLE[1],
        RECTANGLE[3],
    )

    with pytest.raises(MissionPlanningError, match="survey polygon is invalid"):
        GridMissionPlanner().plan(_request(bow_tie))


def test_planner_rejects_more_drones_than_generated_lanes() -> None:
    tiny = (
        (500_000.0, 1_200_000.0),
        (500_005.0, 1_200_000.0),
        (500_005.0, 1_200_005.0),
        (500_000.0, 1_200_005.0),
    )

    with pytest.raises(MissionPlanningError, match="fewer flight lanes"):
        GridMissionPlanner().plan(_request(tiny, drone_count=2))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("drone_count", 4, "drone_count"),
        ("altitude_agl_m", 9.0, "altitude_agl_m"),
        ("gimbal_pitch_deg", -80.0, "nadir"),
        ("forward_overlap", 1.0, "forward_overlap"),
        ("side_overlap", -0.1, "side_overlap"),
        ("flight_speed_mps", 0.0, "flight_speed_mps"),
        ("sweep_heading_deg", 180.0, "sweep_heading_deg"),
    ],
)
def test_planning_profile_rejects_invalid_values(
    field: str,
    value: float,
    message: str,
) -> None:
    values = {field: value}

    with pytest.raises(MissionPlanningError, match=message):
        MissionPlanningProfile(**values)  # type: ignore[arg-type]
