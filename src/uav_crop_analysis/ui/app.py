"""PySide6 composition root for the standalone desktop application."""

from __future__ import annotations

import multiprocessing
from pathlib import Path
import sys
from typing import Sequence

from PySide6.QtWidgets import QApplication

from uav_crop_analysis.bootstrap import build_runtime
from uav_crop_analysis.infrastructure import AppConfig
from uav_crop_analysis.ui.import_controller import MissionImportController
from uav_crop_analysis.ui.phase6_viewmodels import (
    AnalysisWorkspaceViewModel,
    DataWorkspaceViewModel,
)
from uav_crop_analysis.ui.phase7_viewmodels import SpatialWorkspaceViewModel
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
    )


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    if existing is not None:
        raise RuntimeError("a non-GUI QCoreApplication already exists")
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName("UAV Crop Analysis")
    app.setApplicationDisplayName("UAV Crop Analysis")
    app.setOrganizationName("UAV Research Group")
    app.setStyle("Fusion")
    app.setFont(application_font())
    app.setStyleSheet(stylesheet())
    return app


def main() -> None:
    multiprocessing.freeze_support()
    app = create_application()
    window = build_main_window()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
