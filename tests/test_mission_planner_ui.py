from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

from pyproj import Transformer
import pytest
from pytestqt.qtbot import QtBot

from uav_crop_analysis.application import CreateSurveyMission, CreateSurveyMissionCommand
from uav_crop_analysis.bootstrap import build_runtime
from uav_crop_analysis.domain import CameraProfile, DroneId, MissionId
from uav_crop_analysis.errors import MissionPlanNotFoundError
from uav_crop_analysis.infrastructure import AppConfig, AppPaths
from uav_crop_analysis.ui.planning_viewmodels import (
    PlanningDraft,
    PlanningWorkspaceViewModel,
)
from uav_crop_analysis.ui.views import mission_planner as planner_module
from uav_crop_analysis.ui.views.mission_planner import (
    MissionPlannerPage,
    _duration_text,
    _short_duration_text,
    build_mission_planner_map_html,
    parse_coordinate_text,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "models/model_inventory.json"
PROJECTED_CRS = "EPSG:32648"
TO_WGS84 = Transformer.from_crs(PROJECTED_CRS, "EPSG:4326", always_xy=True)
RECTANGLE = (
    (500_000.0, 1_200_000.0),
    (500_060.0, 1_200_000.0),
    (500_060.0, 1_200_035.0),
    (500_000.0, 1_200_035.0),
)


class FakeSettings:
    values: ClassVar[dict[str, object]] = {}

    def value(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)

    def setValue(self, key: str, value: object) -> None:  # noqa: N802
        self.values[key] = value


@pytest.fixture
def planning_runtime(tmp_path: Path):
    paths = AppPaths(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    )
    runtime = build_runtime(
        tmp_path / "planning.db",
        config=AppConfig(paths),
        registry_path=REGISTRY,
    )
    CreateSurveyMission(runtime.missions).execute(
        CreateSurveyMissionCommand(
            mission_id="mission-planner-ui",
            name="Khảo sát khu A",
            drone_ids=("drone-01", "drone-02"),
        )
    )
    camera = CameraProfile(
        profile_id="camera-rgb",
        name="Camera RGB",
        image_width_px=4000,
        image_height_px=3000,
        horizontal_fov_deg=82.0,
        vertical_fov_deg=62.0,
    )
    runtime.missions.save_camera_profile(
        MissionId("mission-planner-ui"),
        camera,
        (DroneId("drone-01"), DroneId("drone-02")),
    )
    yield runtime
    runtime.shutdown()


def _polygon() -> tuple[tuple[float, float], ...]:
    return tuple(
        (latitude, longitude)
        for longitude, latitude in (
            TO_WGS84.transform(x_value, y_value) for x_value, y_value in RECTANGLE
        )
    )


def _draft() -> PlanningDraft:
    polygon = _polygon()
    return PlanningDraft(
        mission_id="mission-planner-ui",
        camera_profile_id="camera-rgb",
        polygon_wgs84=polygon,
        altitude_agl_m=10.0,
        sweep_heading_deg=90.0,
    )


def test_coordinate_parser_accepts_lines_and_json() -> None:
    lines = "10.0, 106.0\n10.1;106.0\n10.1 106.1\n10.0, 106.0"
    expected = ((10.0, 106.0), (10.1, 106.0), (10.1, 106.1))

    assert parse_coordinate_text(lines) == expected
    assert parse_coordinate_text(json.dumps(expected)) == expected


def test_duration_labels_are_human_readable() -> None:
    assert _duration_text(5_100) == "1 giờ 25 phút"
    assert _short_duration_text(5_100) == "1g 25p"


@pytest.mark.parametrize(
    "value, message",
    [
        ("10,106\n11,106", "ít nhất ba"),
        ("91,106\n10,106\n11,107", "WGS84"),
        ("10,106\ninvalid\n11,107", "Dòng 2"),
    ],
)
def test_coordinate_parser_rejects_invalid_input(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_coordinate_text(value)


def test_planning_viewmodel_calculates_preview_and_publishes_on_export(
    planning_runtime,
    tmp_path: Path,
) -> None:
    viewmodel = PlanningWorkspaceViewModel(
        planning_runtime.data_workspace,
        planning_runtime.mission_planning,
    )

    loaded = viewmodel.load("mission-planner-ui")
    assert loaded.workspace is not None
    assert loaded.plan is None
    assert [item.profile_id for item in loaded.workspace.camera_catalog] == ["camera-rgb"]

    calculated = viewmodel.calculate(_draft())
    assert calculated.error_message is None
    assert calculated.plan is not None
    assert len(calculated.plan.routes) == 2
    assert calculated.plan.export_ready
    with pytest.raises(MissionPlanNotFoundError):
        planning_runtime.mission_planning.get("mission-planner-ui")

    exported = viewmodel.export(tmp_path / "exports")
    assert exported.error_message is None
    assert exported.exported is not None
    assert exported.exported.mission_json.is_file()
    assert planning_runtime.mission_planning.get("mission-planner-ui") == calculated.plan

    cleared = viewmodel.discard("mission-planner-ui")
    assert cleared.plan is None
    with pytest.raises(MissionPlanNotFoundError):
        planning_runtime.mission_planning.get("mission-planner-ui")


def test_planning_page_restores_draft_and_presents_routes(
    qtbot: QtBot,
    planning_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeSettings.values = {}
    monkeypatch.setattr(planner_module, "QSettings", FakeSettings)
    viewmodel = PlanningWorkspaceViewModel(
        planning_runtime.data_workspace,
        planning_runtime.mission_planning,
    )
    workspace = viewmodel.load("mission-planner-ui").workspace
    assert workspace is not None
    plan = viewmodel.calculate(_draft()).plan
    assert plan is not None
    first = MissionPlannerPage()
    qtbot.addWidget(first)

    first.set_workspace(workspace, plan)

    assert first.camera_combo.currentData() == "camera-rgb"
    assert not hasattr(first, "home_container")
    assert first.vertex_label.text() == "4 đỉnh"
    assert first.route_table.rowCount() == 2
    assert first.waypoint_model.rowCount() == len(plan.routes[0].waypoints)
    assert first.export_button.isEnabled()
    assert first.clear_boundary_button.accessibleName() == "Xóa ranh giới đã vẽ (Delete)"
    with qtbot.waitSignal(first.clearPlanRequested) as cleared:
        first.map_view_clear()
    assert cleared.args == ["mission-planner-ui"]
    assert first.vertex_label.text() == "0 đỉnh"
    assert first.draft().polygon_wgs84 == ()
    assert first.map_view._pending_routes == {"routes": []}
    assert first.route_table.rowCount() == 0
    assert first.waypoint_model.rowCount() == 0
    assert not first.export_button.isEnabled()
    first.altitude.setValue(12.0)
    assert FakeSettings.values
    assert not first.export_button.isEnabled()
    assert first.draft_status.text() == "Đã lưu bản nháp"

    restored = MissionPlannerPage()
    qtbot.addWidget(restored)
    restored.set_workspace(workspace, None)

    assert restored.altitude.value() == 12.0
    assert restored.vertex_label.text() == "0 đỉnh"
    assert not restored.calculate_button.isEnabled()


def test_planner_map_html_exposes_drawing_editing_and_route_contract() -> None:
    html = build_mission_planner_map_html()

    assert "plannerSetPolygon" in html
    assert "plannerSetDrawMode" in html
    assert "plannerSetEditMode" in html
    assert "plannerSetRouteVisible" in html
    assert "plannerBridge" in html
    assert "World_Imagery" in html
    assert "meters_per_pixel" in html
    assert "plannerGetViewState" in html
    assert "map.on('zoom zoomend move moveend',reportViewState)" in html
    assert "iconSize:[8,8]" in html
    assert "guideLine=L.polyline" in html
    assert "dashArray:'5 5'" in html
    assert "weight:1.5" in html
    assert "bindTooltip(route.drone_id)" not in html
    assert "unpkg.com" not in html
    assets = planner_module._planner_assets_base_url().toLocalFile()  # noqa: SLF001
    assert (Path(assets) / "leaflet.js").is_file()
    assert (Path(assets) / "leaflet.css").is_file()
