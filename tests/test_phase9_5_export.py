from __future__ import annotations

import hashlib
from io import StringIO
import json
from pathlib import Path

from pyproj import Transformer
import pytest

from uav_crop_analysis.adapters import (
    GreenEyeMissionBundleExporter,
    GreenEyeMissionBundleInitializer,
    JsonMissionPlanRepository,
    QGroundControlPlanWriter,
    has_greeneye_bundle_media,
    load_greeneye_bundle_media,
)
from uav_crop_analysis.api import ApiApplication
from uav_crop_analysis.bootstrap import build_runtime
from uav_crop_analysis.cli import main as cli_main
from uav_crop_analysis.domain import (
    CameraProfile,
    DroneId,
    FlightProfile,
    GeoPoint,
    MissionId,
)
from uav_crop_analysis.errors import MissionPlanningError
from uav_crop_analysis.infrastructure import AppConfig, AppPaths
from uav_crop_analysis.integrations import QGroundControlPlanReader
from uav_crop_analysis.planning import (
    GridMissionPlanner,
    MissionPlanningProfile,
    MissionPlanningRequest,
    SurveyArea,
    load_mission_plan_schema,
)
from uav_crop_analysis.planning.serialization import plan_from_dict, plan_to_dict
from uav_crop_analysis.sdk import (
    CreateMissionRequest,
    PlanMissionRequest,
    UavCropAnalysis,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "models/model_inventory.json"
PROJECTED_CRS = "EPSG:32648"
TO_WGS84 = Transformer.from_crs(PROJECTED_CRS, "EPSG:4326", always_xy=True)
RECTANGLE = (
    (500_000.0, 1_200_000.0),
    (500_050.0, 1_200_000.0),
    (500_050.0, 1_200_030.0),
    (500_000.0, 1_200_030.0),
)


def _points() -> tuple[GeoPoint, ...]:
    return tuple(
        GeoPoint(latitude, longitude)
        for longitude, latitude in (
            TO_WGS84.transform(x_value, y_value) for x_value, y_value in RECTANGLE
        )
    )


def _camera() -> CameraProfile:
    return CameraProfile(
        profile_id="camera-phase9-5",
        name="Camera RGB",
        image_width_px=4000,
        image_height_px=3000,
        horizontal_fov_deg=82.0,
        vertical_fov_deg=62.0,
    )


def _domain_plan(drone_count: int = 2):
    points = _points()
    return GridMissionPlanner().plan(
        MissionPlanningRequest(
            mission_id="mission-export",
            survey_area=SurveyArea(points),
            profile=MissionPlanningProfile(
                drone_count=drone_count,
                sweep_heading_deg=90.0,
            ),
            camera=_camera(),
            drone_ids=tuple(f"drone-{index + 1}" for index in range(drone_count)),
            homes=(points[0],) * drone_count,
        )
    )


def _runtime(tmp_path: Path):
    paths = AppPaths(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    )
    return build_runtime(
        tmp_path / "app.db",
        config=AppConfig(paths),
        registry_path=REGISTRY,
    )


def _prepare_sdk(sdk: UavCropAnalysis, mission_id: str = "planned-mission") -> None:
    sdk.create_mission(
        CreateMissionRequest(
            mission_id=mission_id,
            name="Lập nhiệm vụ",
            drone_ids=("drone-1", "drone-2"),
        )
    )
    sdk.runtime.missions.save_camera_profile(
        MissionId(mission_id),
        _camera(),
        (DroneId("drone-1"), DroneId("drone-2")),
    )


def _sdk_request(mission_id: str = "planned-mission") -> PlanMissionRequest:
    points = _points()
    polygon = tuple((point.latitude, point.longitude) for point in points)
    home = polygon[0]
    return PlanMissionRequest(
        mission_id=mission_id,
        camera_profile_id=_camera().profile_id,
        polygon_wgs84=polygon,
        homes_wgs84=(home, home),
        sweep_heading_deg=90.0,
    )


def test_greeneye_schema_round_trip_and_version_validation() -> None:
    plan = _domain_plan()
    payload = plan_to_dict(plan)

    assert plan_from_dict(payload) == plan
    assert payload["schema_version"] == 1
    assert payload["statistics"]["capture_count"] == plan.capture_count
    assert payload["camera"]["profile_sha256"] == plan.camera_profile_sha256

    payload["schema_version"] = 99
    with pytest.raises(MissionPlanningError, match="unsupported"):
        plan_from_dict(payload)


def test_packaged_json_schema_matches_runtime_contract() -> None:
    schema = load_mission_plan_schema()
    payload = plan_to_dict(_domain_plan())

    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["properties"]["schema_version"]["const"] == 1
    assert set(schema["required"]) <= set(payload)
    assert schema["$defs"]["profile"]["properties"]["capture_mode"]["const"] == (
        "stop_and_capture"
    )


def test_json_repository_persists_and_replaces_by_mission_id(tmp_path: Path) -> None:
    repository = JsonMissionPlanRepository(tmp_path / "plans")
    plan = _domain_plan(1)

    repository.save(plan)

    assert repository.get(plan.mission_id) == plan
    assert repository.list() == (plan,)
    files = list((tmp_path / "plans").iterdir())
    assert len(files) == 1
    assert files[0].name.endswith(".plan.json")
    assert plan.mission_id not in files[0].name


def test_bundle_checksums_paths_and_qgc_round_trip(tmp_path: Path) -> None:
    plan = _domain_plan(2)
    exported = GreenEyeMissionBundleExporter().export(plan, tmp_path)

    assert exported.directory.parent == tmp_path / "GreenEye mission"
    assert exported.directory.name == "mission-export"
    assert not (tmp_path / "mission-export").exists()
    for route in plan.routes:
        media_folder = exported.directory / "media" / route.drone_id
        assert (media_folder / ".keep").is_file()
    assert (exported.directory / "media" / "README.txt").is_file()
    assert exported.mission_json.relative_to(exported.directory).as_posix() == "mission.json"
    assert [path.name for path in exported.qgroundcontrol_plans] == [
        "drone-01.plan",
        "drone-02.plan",
    ]
    for relative, expected in exported.checksums:
        source = exported.directory / relative
        assert source.is_file()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
        assert not Path(relative).is_absolute()
        assert ".." not in Path(relative).parts
    checksum_lines = exported.checksums_file.read_text(encoding="utf-8").splitlines()
    assert len(checksum_lines) == 3

    all_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            exported.mission_json,
            *exported.qgroundcontrol_plans,
        )
    )
    assert str(tmp_path) not in all_text

    for route, qgc_path in zip(plan.routes, exported.qgroundcontrol_plans, strict=True):
        qgc = QGroundControlPlanReader().read(qgc_path)
        assert qgc.plan_version == 1
        assert qgc.mission_version == 2
        assert len(qgc.waypoints) == len(route.waypoints)
        assert all(waypoint.command == 16 for waypoint in qgc.waypoints)
        raw = json.loads(qgc_path.read_text(encoding="utf-8"))
        assert len(raw["mission"]["items"]) == len(route.waypoints) * 2
        assert {item["command"] for item in raw["mission"]["items"]} == {16, 206}


def test_creation_initializes_bundle_and_export_reuses_it(tmp_path: Path) -> None:
    created = GreenEyeMissionBundleInitializer().create(
        mission_id="mission-export",
        name="Khảo sát khu A",
        drone_ids=("drone-1", "drone-2"),
        flight_profile=FlightProfile(),
        camera_profile=_camera(),
        output_root=tmp_path,
    )

    assert created == tmp_path / "GreenEye mission" / "mission-export"
    assert (created / "mission.json").is_file()
    assert (created / "qgroundcontrol" / ".keep").is_file()
    assert (created / "media" / "drone-1" / ".keep").is_file()
    image = created / "media" / "drone-1" / "DJI_0001.JPG"
    image.write_bytes(b"image-placeholder")

    exported = GreenEyeMissionBundleExporter().export(_domain_plan(2), tmp_path)

    assert exported.directory == created
    assert image.is_file()
    payload = json.loads(exported.mission_json.read_text(encoding="utf-8"))
    assert payload["kind"] == "greeneye_mission_plan"


def test_bundle_media_layout_builds_a_repeatable_import_request(tmp_path: Path) -> None:
    exported = GreenEyeMissionBundleExporter().export(_domain_plan(2), tmp_path)
    first_drone = exported.directory / "media" / "drone-1"

    assert not has_greeneye_bundle_media(exported.directory)
    (first_drone / "DJI_0001.JPG").write_bytes(b"image-placeholder")

    assert has_greeneye_bundle_media(exported.directory)
    request = load_greeneye_bundle_media(exported.directory)
    assert request.mission.mission_id.value == "mission-export"
    assert tuple(source.drone_id.value for source in request.sources) == (
        "drone-1",
        "drone-2",
    )
    assert request.sources[0].image_dir == first_drone


def test_bundle_exports_without_user_home(tmp_path: Path) -> None:
    points = _points()
    plan = GridMissionPlanner().plan(
        MissionPlanningRequest(
            mission_id="preview-only",
            survey_area=SurveyArea(points),
            profile=MissionPlanningProfile(),
            camera=_camera(),
            drone_ids=("drone-1",),
        )
    )

    exported = GreenEyeMissionBundleExporter().export(plan, tmp_path)
    raw = json.loads(exported.qgroundcontrol_plans[0].read_text(encoding="utf-8"))
    first = plan.routes[0].waypoints[0].position
    assert raw["mission"]["plannedHomePosition"] == [
        first.latitude,
        first.longitude,
        0,
    ]


def test_sdk_persists_plan_across_runtime_restart(tmp_path: Path) -> None:
    first = _runtime(tmp_path)
    try:
        sdk = UavCropAnalysis(first)
        _prepare_sdk(sdk)
        planned = sdk.plan_mission(_sdk_request())
        assert planned.export_ready
        assert len(planned.routes) == 2
        assert sdk.capabilities().mission_planning
        assert sdk.capabilities().drone_commands_enabled is False
    finally:
        first.shutdown()

    second = _runtime(tmp_path)
    try:
        reopened = UavCropAnalysis(second).get_mission_plan("planned-mission")
        assert reopened == planned
        assert len(second.mission_planning.list()) == 1
    finally:
        second.shutdown()


def test_rest_plan_create_get_and_export(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    try:
        sdk = UavCropAnalysis(runtime)
        _prepare_sdk(sdk, "api-plan")
        request = _sdk_request("api-plan")
        body = {
            "mission_id": request.mission_id,
            "camera_profile_id": request.camera_profile_id,
            "polygon_wgs84": request.polygon_wgs84,
            "homes_wgs84": request.homes_wgs84,
            "sweep_heading_deg": request.sweep_heading_deg,
        }
        api = ApiApplication(sdk)

        created = api.handle("POST", "/api/v1/mission-plans", json.dumps(body).encode())
        assert created.status == 201
        assert created.payload["data"]["mission_id"] == "api-plan"
        assert api.handle("GET", "/api/v1/mission-plans").status == 200
        assert api.handle("GET", "/api/v1/mission-plans/api-plan").status == 200
        missing = api.handle("GET", "/api/v1/mission-plans/missing")
        assert missing.status == 404
        assert missing.payload["error"]["code"] == "mission_plan_not_found"

        exported = api.handle(
            "POST",
            "/api/v1/mission-plans/api-plan/export",
            json.dumps({"output_root": str(tmp_path / "exports")}).encode(),
        )
        assert exported.status == 201
        assert Path(exported.payload["data"]["mission_json"]).is_file()
    finally:
        runtime.shutdown()


def test_cli_plan_create_show_and_export(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    try:
        _prepare_sdk(UavCropAnalysis(runtime), "cli-plan")
    finally:
        runtime.shutdown()
    request = _sdk_request("cli-plan")
    request_path = tmp_path / "plan-request.json"
    request_path.write_text(
        json.dumps(
            {
                "mission_id": request.mission_id,
                "camera_profile_id": request.camera_profile_id,
                "polygon_wgs84": request.polygon_wgs84,
                "homes_wgs84": request.homes_wgs84,
                "sweep_heading_deg": request.sweep_heading_deg,
            }
        ),
        encoding="utf-8",
    )
    common = [
        "--database",
        str(tmp_path / "app.db"),
        "--registry",
        str(REGISTRY),
        "--plan-store",
        str(tmp_path / "data/mission-plans"),
    ]
    output = StringIO()

    assert cli_main([*common, "plan", "create", str(request_path)], stdout=output) == 0
    assert json.loads(output.getvalue())["mission_id"] == "cli-plan"
    output = StringIO()
    assert cli_main([*common, "plan", "show", "cli-plan"], stdout=output) == 0
    assert json.loads(output.getvalue())["capture_count"] > 0
    output = StringIO()
    assert (
        cli_main(
            [
                *common,
                "plan",
                "export",
                "cli-plan",
                "--output",
                str(tmp_path / "cli-export"),
            ],
            stdout=output,
        )
        == 0
    )
    assert Path(json.loads(output.getvalue())["checksums_file"]).is_file()


def test_qgc_writer_matches_golden_fixture() -> None:
    plan = _domain_plan(1)
    payload = QGroundControlPlanWriter().to_dict(plan, plan.routes[0])
    expected = json.loads(
        (ROOT / "tests/fixtures/phase9_5/qgc_plan_shape.json").read_text(
            encoding="utf-8"
        )
    )

    assert {
        "fileType": payload["fileType"],
        "version": payload["version"],
        "geoFence": payload["geoFence"],
        "rallyPoints": payload["rallyPoints"],
        "mission_keys": sorted(payload["mission"]),
        "item_commands": [item["command"] for item in payload["mission"]["items"][:4]],
        "item_keys": sorted(payload["mission"]["items"][0]),
    } == expected
