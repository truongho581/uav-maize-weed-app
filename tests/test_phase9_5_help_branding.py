from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from uav_crop_analysis.ui.app import create_application
from uav_crop_analysis.ui.branding import (
    APP_DISPLAY_NAME,
    STORAGE_APPLICATION_NAME,
)
from uav_crop_analysis.ui.shell import MainWindow
from uav_crop_analysis.ui.viewmodels import MissionWorkspaceViewModel

from test_ui_shell import FakeWorkspaceQuery


class MemorySettings:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.sync_count = 0

    def value(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)

    def setValue(self, key: str, value: object) -> None:  # noqa: N802
        self.values[key] = value

    def sync(self) -> None:
        self.sync_count += 1


def _window(qtbot: QtBot, settings: MemorySettings) -> MainWindow:
    window = MainWindow(
        MissionWorkspaceViewModel(FakeWorkspaceQuery()),
        settings=settings,  # type: ignore[arg-type]
    )
    qtbot.addWidget(window)
    window.show()
    return window


def test_greeneye_display_name_keeps_legacy_settings_namespace() -> None:
    app = create_application([])

    assert app is QApplication.instance()
    assert app.applicationDisplayName() == APP_DISPLAY_NAME
    assert app.applicationName() == STORAGE_APPLICATION_NAME


def test_sidebar_expansion_is_persisted_and_restored(qtbot: QtBot) -> None:
    settings = MemorySettings()
    first = _window(qtbot, settings)

    assert first.sidebar.width() == 56
    assert first.missions_nav.text() == ""
    assert first.missions_nav.toolTip() == "Nhiệm vụ"
    assert first.sidebar_toggle.accessibleName() == "Mở rộng thanh điều hướng"

    qtbot.mouseClick(first.sidebar_toggle, Qt.MouseButton.LeftButton)

    assert first.sidebar.width() == 212
    assert first.missions_nav.text() == "Nhiệm vụ"
    assert first.help_button.text() == "Trợ giúp"
    assert settings.values["ui/sidebar_expanded"] is True
    assert settings.sync_count == 1

    second = _window(qtbot, settings)
    assert second.sidebar.width() == 212
    assert second.analysis_nav.text() == "Xử lý ảnh"


def test_context_help_updates_for_current_workspace(qtbot: QtBot) -> None:
    window = _window(qtbot, MemorySettings())

    qtbot.mouseClick(window.help_button, Qt.MouseButton.LeftButton)
    dialog = window.help_button.dialog
    assert dialog is not None
    assert dialog.isVisible()
    assert dialog.title_label.text() == "Bắt đầu một nhiệm vụ"
    assert "Nội dung trợ giúp 1.1" in dialog.version_label.text()
    assert "GreenEye 0.2.0" in dialog.version_label.text()

    window.open_mission("mission-ui")
    window.help_button.show_help()

    assert dialog.title_label.text() == "Tổng quan nhiệm vụ"
    assert "Dữ liệu" in dialog.body_label.text()
    assert "Xử lý ảnh" in dialog.body_label.text()
    assert "Bản đồ" in dialog.body_label.text()


def test_expanded_sidebar_preserves_main_workspace_at_1180(qtbot: QtBot) -> None:
    window = _window(qtbot, MemorySettings())
    window.resize(1180, 760)
    window.set_sidebar_expanded(True)
    qtbot.wait(20)

    assert window.windowTitle() == APP_DISPLAY_NAME
    assert window.sidebar.width() == 212
    assert window.pages.width() >= 940
    assert window.sidebar_toggle.toolTip() == "Thu gọn thanh điều hướng"
    assert window.help_button.accessibleName() == "Trợ giúp"
