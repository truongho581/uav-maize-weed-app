from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QStackedWidget
from pytestqt.qtbot import QtBot

from uav_crop_analysis.application import (
    DroneCoverage,
    MissionDataStatus,
    MissionOverview,
    MissionSummary,
)
from uav_crop_analysis.domain import SurveyMission
from uav_crop_analysis.infrastructure import AppConfig, AppPaths
from uav_crop_analysis.ui.app import build_main_window, create_application
from uav_crop_analysis.ui.models import MISSION_ID_ROLE, MissionTableModel
from uav_crop_analysis.ui.shell import MainWindow
from uav_crop_analysis.ui.viewmodels import MissionWorkspaceViewModel


NOW = datetime(2026, 7, 27, 8, 30, tzinfo=timezone.utc)


def _mission() -> SurveyMission:
    return SurveyMission.create(
        mission_id="mission-ui",
        name="Khao sat ngo khu A",
        drone_ids=("drone-01", "drone-02", "drone-03"),
        created_at=NOW,
    )


def _summary(
    *, data_status: MissionDataStatus = MissionDataStatus.READY
) -> MissionSummary:
    return MissionSummary(
        mission_id="mission-ui",
        name="Khảo sát ngô khu A",
        created_at=NOW,
        image_count=360 if data_status is not MissionDataStatus.EMPTY else 0,
        gps_coverage=1.0 if data_status is MissionDataStatus.READY else 0.5,
        data_status=data_status,
        latest_job_status=None,
    )


def _overview(*, image_count: int = 360) -> MissionOverview:
    per_drone = image_count // 3
    status = MissionDataStatus.READY if image_count else MissionDataStatus.EMPTY
    return MissionOverview(
        mission=_mission(),
        data_status=status,
        image_count=image_count,
        gps_coverage=1.0 if image_count else 0.0,
        altitude_coverage=1.0 if image_count else 0.0,
        camera_count=1 if image_count else 0,
        drones=tuple(
            DroneCoverage(
                drone_id=f"drone-0{index + 1}",
                lane_index=index,
                image_count=per_drone,
                telemetry_count=per_drone,
                gps_image_count=per_drone,
                altitude_image_count=per_drone,
            )
            for index in range(3)
        ),
        recent_jobs=(),
    )


class FakeWorkspaceQuery:
    def __init__(self, overview: MissionOverview | None = None) -> None:
        self.overview = overview or _overview()

    def list_missions(self) -> tuple[MissionSummary, ...]:
        return (_summary(data_status=self.overview.data_status),)

    def get_overview(self, mission_id: str) -> MissionOverview | None:
        return self.overview if mission_id == "mission-ui" else None


class FailingWorkspaceQuery:
    def list_missions(self) -> tuple[MissionSummary, ...]:
        raise RuntimeError("database unavailable")

    def get_overview(self, mission_id: str) -> MissionOverview | None:
        raise RuntimeError("database unavailable")


def test_mission_table_exposes_display_and_stable_id_role() -> None:
    model = MissionTableModel((_summary(),))

    assert model.rowCount() == 1
    assert model.data(model.index(0, 0)) == "Khảo sát ngô khu A"
    assert model.data(model.index(0, 0), MISSION_ID_ROLE) == "mission-ui"
    assert model.data(model.index(0, 3)) == "100%"


def test_shell_opens_overview_and_emits_analysis_command(qtbot: QtBot) -> None:
    window = MainWindow(MissionWorkspaceViewModel(FakeWorkspaceQuery()))
    qtbot.addWidget(window)
    window.show()

    window.open_mission("mission-ui")

    assert window.pages.currentWidget() is window.overview
    assert window.overview.analysis_button.isEnabled()
    with qtbot.waitSignal(window.analysisRequested, timeout=1000) as signal:
        qtbot.mouseClick(window.overview.analysis_button, Qt.MouseButton.LeftButton)
    assert signal.args == ["mission-ui"]

    qtbot.mouseClick(window.overview.back_button, Qt.MouseButton.LeftButton)
    assert window.pages.currentWidget() is window.mission_list


def test_shell_disables_analysis_for_empty_mission(qtbot: QtBot) -> None:
    window = MainWindow(MissionWorkspaceViewModel(FakeWorkspaceQuery(_overview(image_count=0))))
    qtbot.addWidget(window)

    window.open_mission("mission-ui")

    assert not window.overview.analysis_button.isEnabled()
    assert "chưa có ảnh" in window.overview.analysis_button.toolTip().lower()


def test_shell_shows_error_state_when_query_fails(qtbot: QtBot) -> None:
    window = MainWindow(MissionWorkspaceViewModel(FailingWorkspaceQuery()))
    qtbot.addWidget(window)

    assert isinstance(window.mission_list.stack, QStackedWidget)
    assert window.mission_list.stack.currentWidget() is window.mission_list.error_state
    assert window.statusBar().currentMessage() == "database unavailable"


def test_composition_root_uses_injected_cross_platform_paths(
    qtbot: QtBot, tmp_path: Path
) -> None:
    root = tmp_path
    config = AppConfig(
        AppPaths(
            data_dir=root / "data",
            config_dir=root / "config",
            cache_dir=root / "cache",
            log_dir=root / "logs",
        )
    )
    app = create_application([])
    window = build_main_window(root / "app.db", config=config)
    qtbot.addWidget(window)

    assert app is QApplication.instance()
    assert window.mission_list.stack.currentWidget() is window.mission_list.empty_state
    assert (root / "app.db").is_file()
    assert (root / "logs/application.log").is_file()
