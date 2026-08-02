"""Capture the planner and Phase 9.5.5 GreenEye shell review states."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest

from uav_crop_analysis.application import CreateSurveyMission, CreateSurveyMissionCommand
from uav_crop_analysis.bootstrap import build_runtime
from uav_crop_analysis.domain import CameraProfile, DroneId, MissionId
from uav_crop_analysis.infrastructure import AppConfig, AppPaths
from uav_crop_analysis.ui.app import create_application
from uav_crop_analysis.ui.import_controller import MissionImportController
from uav_crop_analysis.ui.phase6_viewmodels import (
    AnalysisWorkspaceViewModel,
    DataWorkspaceViewModel,
)
from uav_crop_analysis.ui.phase7_viewmodels import SpatialWorkspaceViewModel
from uav_crop_analysis.ui.planning_viewmodels import (
    PlanningDraft,
    PlanningWorkspaceViewModel,
)
from uav_crop_analysis.ui.report_viewmodels import ReportWorkspaceViewModel
from uav_crop_analysis.ui.shell import MainWindow
from uav_crop_analysis.ui.viewmodels import MissionWorkspaceViewModel


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "review_screenshots"
REGISTRY = ROOT / "models/model_inventory.json"
VIEWPORTS = ((1180, 760), (1440, 900), (1920, 1080))


def main() -> None:
    app = create_application([])
    app.setOrganizationName("GreenEye UI Capture")
    app.setApplicationName("GreenEye Planner Capture")
    QSettings().clear()
    temporary = Path(tempfile.mkdtemp(prefix="greeneye-planner-capture-"))
    paths = AppPaths(
        data_dir=temporary / "data",
        config_dir=temporary / "config",
        cache_dir=temporary / "cache",
        log_dir=temporary / "logs",
    )
    runtime = build_runtime(
        temporary / "capture.db",
        config=AppConfig(paths),
        registry_path=REGISTRY,
    )
    CreateSurveyMission(runtime.missions).execute(
        CreateSurveyMissionCommand(
            mission_id="gre-2026-khu-a",
            name="Khảo sát ngô khu A",
            drone_ids=("drone-01", "drone-02", "drone-03"),
        )
    )
    camera = CameraProfile(
        profile_id="camera-rgb",
        name="Camera RGB khảo sát",
        image_width_px=4000,
        image_height_px=3000,
        horizontal_fov_deg=82.0,
        vertical_fov_deg=62.0,
    )
    runtime.missions.save_camera_profile(
        MissionId("gre-2026-khu-a"),
        camera,
        (DroneId("drone-01"), DroneId("drone-02"), DroneId("drone-03")),
    )
    planning = PlanningWorkspaceViewModel(runtime.data_workspace, runtime.mission_planning)
    planning.load("gre-2026-khu-a")
    polygon = (
        (10.762300, 106.659700),
        (10.762310, 106.660750),
        (10.763000, 106.660770),
        (10.763020, 106.659680),
    )
    planning.calculate(
        PlanningDraft(
            mission_id="gre-2026-khu-a",
            camera_profile_id="camera-rgb",
            polygon_wgs84=polygon,
            altitude_agl_m=10.0,
            sweep_heading_deg=90.0,
        )
    )
    window = MainWindow(
        MissionWorkspaceViewModel(runtime.mission_workspace),
        DataWorkspaceViewModel(runtime.data_workspace),
        AnalysisWorkspaceViewModel(runtime.analysis_workspace),
        MissionImportController(runtime.mission_import),
        SpatialWorkspaceViewModel(runtime.spatial_workspace),
        ReportWorkspaceViewModel(runtime.report_workspace),
        runtime.model_test,
        planning,
    )
    window.open_mission("gre-2026-khu-a")
    window.open_planning("gre-2026-khu-a")
    window.show()
    QTest.qWait(7000)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for width, height in VIEWPORTS:
        window.resize(width, height)
        QTest.qWait(900)
        window.grab().save(str(OUTPUT / f"latest-planning-{width}x{height}.png"))
    window.resize(1180, 760)
    window.set_sidebar_expanded(True)
    QTest.qWait(300)
    window.grab().save(str(OUTPUT / "latest-greeneye-sidebar-expanded-1180x760.png"))
    window.help_button.show_help()
    QTest.qWait(200)
    help_dialog = window.help_button.dialog
    if help_dialog is None:
        raise RuntimeError("help dialog was not created")
    help_dialog.grab().save(str(OUTPUT / "latest-greeneye-help.png"))
    help_dialog.close()
    window.close()
    runtime.shutdown()
    shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    main()
