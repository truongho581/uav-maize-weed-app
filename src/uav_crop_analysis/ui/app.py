"""PySide6 composition root for the standalone desktop application."""

from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import sys
from typing import Sequence

from PySide6.QtCore import QCoreApplication, QTimer, Qt
from PySide6.QtWidgets import QApplication

from uav_crop_analysis.bootstrap import build_runtime
from uav_crop_analysis.infrastructure import AppConfig
from uav_crop_analysis.ui.branding import (
    APP_DISPLAY_NAME,
    ORGANIZATION_NAME,
    STORAGE_APPLICATION_NAME,
)
from uav_crop_analysis.ui.icons import lucide_icon
from uav_crop_analysis.ui.import_controller import MissionImportController
from uav_crop_analysis.ui.phase6_viewmodels import (
    AnalysisWorkspaceViewModel,
    DataWorkspaceViewModel,
)
from uav_crop_analysis.ui.phase7_viewmodels import SpatialWorkspaceViewModel
from uav_crop_analysis.ui.planning_viewmodels import PlanningWorkspaceViewModel
from uav_crop_analysis.ui.report_viewmodels import ReportWorkspaceViewModel
from uav_crop_analysis.ui.shell import MainWindow
from uav_crop_analysis.ui.tokens import application_font, stylesheet
from uav_crop_analysis.ui.viewmodels import MissionWorkspaceViewModel


def build_main_window(
    database_path: str | Path | None = None,
    *,
    config: AppConfig | None = None,
    registry_path: str | Path | None = None,
) -> MainWindow:
    runtime = build_runtime(
        database_path,
        config=config,
        registry_path=registry_path,
    )
    import_controller = MissionImportController(
        runtime.mission_import
    )
    return MainWindow(
        MissionWorkspaceViewModel(runtime.mission_workspace),
        DataWorkspaceViewModel(runtime.data_workspace),
        AnalysisWorkspaceViewModel(runtime.analysis_workspace),
        import_controller,
        SpatialWorkspaceViewModel(runtime.spatial_workspace),
        ReportWorkspaceViewModel(runtime.report_workspace),
        runtime.model_test,
        PlanningWorkspaceViewModel(runtime.data_workspace, runtime.mission_planning),
    )


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        app = existing
    elif existing is not None:
        raise RuntimeError("a non-GUI QCoreApplication already exists")
    else:
        # QtWebEngine needs shared OpenGL contexts. This must be configured
        # before QApplication exists, otherwise creating map views can abort
        # in a frozen macOS bundle.
        QCoreApplication.setAttribute(
            Qt.ApplicationAttribute.AA_ShareOpenGLContexts,
            True,
        )
        app = QApplication(list(argv) if argv is not None else sys.argv)
    # Keep the legacy application name as the QSettings namespace so upgrades retain
    # camera profiles, map keys and UI preferences stored by earlier releases.
    app.setApplicationName(STORAGE_APPLICATION_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setWindowIcon(lucide_icon("eye", color="#16724A", size=32))
    app.setStyle("Fusion")
    app.setFont(application_font())
    app.setStyleSheet(stylesheet())
    return app


def main() -> None:
    multiprocessing.freeze_support()
    app = create_application()
    if os.environ.get("UAV_CROP_WEBENGINE_SMOKE") == "1":
        raise SystemExit(_run_webengine_smoke(app))
    window = build_main_window()
    window.showMaximized()
    raise SystemExit(app.exec())


def _run_webengine_smoke(app: QApplication) -> int:
    """Create a real page for frozen-build verification without opening app data."""
    from PySide6.QtWebEngineCore import QWebEnginePage

    page = QWebEnginePage(app)
    page.setHtml("<html><body>GreenEye WebEngine smoke</body></html>")
    # In a no-window macOS smoke process, Chromium may not emit loadFinished
    # even though it has initialized successfully. Reaching this timer proves
    # that the native WebEngine page was created without an abort.
    def complete() -> None:
        page.deleteLater()
        app.exit(0)

    QTimer.singleShot(750, complete)
    return app.exec()


if __name__ == "__main__":
    main()
