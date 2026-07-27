"""Main application shell and mission navigation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application import ImportReport, IssueSeverity
from uav_crop_analysis.geospatial import ProgressCallback
from uav_crop_analysis.ui.import_controller import MissionImportController
from uav_crop_analysis.ui.phase6_viewmodels import (
    AnalysisWorkspaceViewModel,
    DataWorkspaceViewModel,
)
from uav_crop_analysis.ui.phase7_viewmodels import SpatialWorkspaceViewModel
from uav_crop_analysis.ui.report_controller import ReportExportController
from uav_crop_analysis.ui.report_viewmodels import ReportWorkspaceViewModel
from uav_crop_analysis.ui.spatial_controller import SpatialTaskController
from uav_crop_analysis.ui.viewmodels import MissionWorkspaceViewModel
from uav_crop_analysis.ui.views import (
    AnalysisWorkspacePage,
    DataWorkspacePage,
    MissionListPage,
    MissionOverviewPage,
    ReportWorkspacePage,
    SpatialWorkspacePage,
)


class MainWindow(QMainWindow):
    analysisRequested = Signal(str)

    def __init__(
        self,
        viewmodel: MissionWorkspaceViewModel,
        data_viewmodel: DataWorkspaceViewModel | None = None,
        analysis_viewmodel: AnalysisWorkspaceViewModel | None = None,
        import_controller: MissionImportController | None = None,
        spatial_viewmodel: SpatialWorkspaceViewModel | None = None,
        report_viewmodel: ReportWorkspaceViewModel | None = None,
    ) -> None:
        super().__init__()
        self.viewmodel = viewmodel
        self.data_viewmodel = data_viewmodel
        self.analysis_viewmodel = analysis_viewmodel
        self.import_controller = import_controller
        self.spatial_viewmodel = spatial_viewmodel
        self.report_viewmodel = report_viewmodel
        self.spatial_controller = (
            SpatialTaskController(self) if spatial_viewmodel is not None else None
        )
        self.report_controller = (
            ReportExportController(self) if report_viewmodel is not None else None
        )
        self._selected_mission_id: str | None = None
        self.setWindowTitle("UAV Crop Analysis")
        self.setMinimumSize(1024, 680)
        self.resize(1366, 768)

        shell = QWidget()
        shell.setObjectName("AppShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self._build_sidebar())

        self.pages = QStackedWidget()
        self.mission_list = MissionListPage()
        self.overview = MissionOverviewPage()
        self.data_workspace = DataWorkspacePage()
        self.analysis_workspace = AnalysisWorkspacePage()
        self.spatial_workspace = SpatialWorkspacePage()
        self.report_workspace = ReportWorkspacePage()
        self.pages.addWidget(self.mission_list)
        self.pages.addWidget(self.overview)
        self.pages.addWidget(self.data_workspace)
        self.pages.addWidget(self.analysis_workspace)
        self.pages.addWidget(self.spatial_workspace)
        self.pages.addWidget(self.report_workspace)
        shell_layout.addWidget(self.pages, 1)
        self.setCentralWidget(shell)

        self.mission_list.refreshRequested.connect(self.refresh)
        self.mission_list.importRequested.connect(self._choose_import_manifest)
        self.mission_list.missionSelected.connect(self.open_mission)
        self.overview.backRequested.connect(self.show_missions)
        self.overview.dataRequested.connect(self.open_data)
        self.overview.analysisRequested.connect(self._forward_analysis)
        self.overview.spatialRequested.connect(self.open_spatial)
        self.overview.reportRequested.connect(self.open_report)
        self.data_workspace.analysisRequested.connect(self._forward_analysis)
        self.analysis_workspace.submitRequested.connect(self._submit_analysis)
        self.analysis_workspace.cancelRequested.connect(self._cancel_analysis)
        self.analysis_workspace.retryRequested.connect(self._retry_analysis)
        self.spatial_workspace.previewRequested.connect(self._build_spatial_preview)
        self.spatial_workspace.importRequested.connect(self._choose_orthomosaic)
        self.spatial_workspace.nodeOdmRequested.connect(self._create_orthomosaic)
        self.spatial_workspace.analyzeRequested.connect(self._analyze_orthomosaic)
        self.spatial_workspace.heatmapRequested.connect(self._export_heatmap)
        self.report_workspace.exportRequested.connect(self._choose_report_directory)
        self.report_workspace.openReportRequested.connect(self._open_report_file)
        if self.import_controller is not None:
            self.import_controller.busyChanged.connect(
                self.mission_list.set_import_busy
            )
            self.import_controller.completed.connect(self._import_completed)
            self.import_controller.failed.connect(self._import_failed)
        if self.spatial_controller is not None:
            self.spatial_controller.busyChanged.connect(self.spatial_workspace.set_busy)
            self.spatial_controller.progress.connect(self.spatial_workspace.set_progress)
            self.spatial_controller.completed.connect(self._spatial_completed)
            self.spatial_controller.failed.connect(self._spatial_failed)
        if self.report_controller is not None:
            self.report_controller.busyChanged.connect(self.report_workspace.set_busy)
            self.report_controller.completed.connect(self._report_completed)
            self.report_controller.failed.connect(self._report_failed)
        self.job_timer = QTimer(self)
        self.job_timer.setInterval(300)
        self.job_timer.timeout.connect(self._poll_analysis_jobs)
        self.job_timer.start()
        self._install_shortcuts()
        self.statusBar().showMessage("Sẵn sàng")
        self.refresh()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 24, 18, 18)
        layout.setSpacing(8)

        brand = QLabel("UAV Crop\nAnalysis")
        brand.setObjectName("BrandTitle")
        brand.setWordWrap(True)
        subtitle = QLabel("Phân tích cây trồng")
        subtitle.setObjectName("BrandSubtitle")
        layout.addWidget(brand)
        layout.addWidget(subtitle)
        layout.addSpacing(24)

        self.missions_nav = QPushButton("Nhiệm vụ")
        self.missions_nav.setObjectName("NavButton")
        self.missions_nav.setCheckable(True)
        self.missions_nav.setChecked(True)
        self.missions_nav.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon)
        )
        self.missions_nav.clicked.connect(self.show_missions)
        layout.addWidget(self.missions_nav)
        self.data_nav = QPushButton("Dữ liệu")
        self.data_nav.setObjectName("NavButton")
        self.data_nav.setCheckable(True)
        self.data_nav.setEnabled(False)
        self.data_nav.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self.data_nav.clicked.connect(self._open_selected_data)
        layout.addWidget(self.data_nav)
        self.analysis_nav = QPushButton("Phân tích")
        self.analysis_nav.setObjectName("NavButton")
        self.analysis_nav.setCheckable(True)
        self.analysis_nav.setEnabled(False)
        self.analysis_nav.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self.analysis_nav.clicked.connect(self._open_selected_analysis)
        layout.addWidget(self.analysis_nav)
        self.spatial_nav = QPushButton("Không gian")
        self.spatial_nav.setObjectName("NavButton")
        self.spatial_nav.setCheckable(True)
        self.spatial_nav.setEnabled(False)
        self.spatial_nav.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
        )
        self.spatial_nav.clicked.connect(self._open_selected_spatial)
        layout.addWidget(self.spatial_nav)
        self.report_nav = QPushButton("Báo cáo")
        self.report_nav.setObjectName("NavButton")
        self.report_nav.setCheckable(True)
        self.report_nav.setEnabled(False)
        self.report_nav.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView)
        )
        self.report_nav.clicked.connect(self._open_selected_report)
        layout.addWidget(self.report_nav)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_group.addButton(self.missions_nav)
        self.nav_group.addButton(self.data_nav)
        self.nav_group.addButton(self.analysis_nav)
        self.nav_group.addButton(self.spatial_nav)
        self.nav_group.addButton(self.report_nav)
        layout.addStretch()

        version = QLabel("v0.2.0")
        version.setObjectName("BrandSubtitle")
        version.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(version)
        return sidebar

    def _install_shortcuts(self) -> None:
        refresh = QShortcut(QKeySequence.StandardKey.Refresh, self)
        refresh.activated.connect(self.refresh)
        find = QShortcut(QKeySequence.StandardKey.Find, self)
        find.activated.connect(self._focus_search)
        back = QShortcut(QKeySequence("Alt+Left"), self)
        back.activated.connect(self.show_missions)

    def refresh(self) -> None:
        state = self.viewmodel.refresh()
        if state.error_message:
            self.mission_list.show_error()
            self.statusBar().showMessage(state.error_message)
            return
        self.mission_list.set_missions(state.missions)
        self.statusBar().showMessage(f"{len(state.missions)} nhiệm vụ")

    def open_mission(self, mission_id: str) -> None:
        state = self.viewmodel.select_mission(mission_id)
        if state.error_message or state.overview is None:
            self.mission_list.show_error()
            self.statusBar().showMessage(state.error_message or "Không thể mở nhiệm vụ")
            return
        self.overview.set_overview(state.overview)
        self._selected_mission_id = mission_id
        self.data_nav.setEnabled(self.data_viewmodel is not None)
        self.analysis_nav.setEnabled(self.analysis_viewmodel is not None)
        self.spatial_nav.setEnabled(self.spatial_viewmodel is not None)
        self.report_nav.setEnabled(self.report_viewmodel is not None)
        self.pages.setCurrentWidget(self.overview)
        self._set_nav(None)
        self.statusBar().showMessage(state.overview.mission.name)

    def show_missions(self) -> None:
        self.pages.setCurrentWidget(self.mission_list)
        self._set_nav(self.missions_nav)
        self.statusBar().showMessage(f"{len(self.viewmodel.state.missions)} nhiệm vụ")

    def _focus_search(self) -> None:
        self.show_missions()
        self.mission_list.focus_search()

    def _choose_import_manifest(self) -> None:
        if self.import_controller is None:
            self.statusBar().showMessage("Mission import chưa được cấu hình")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn mission manifest",
            "",
            "Mission manifest (mission.json *.json);;JSON (*.json)",
        )
        if path and self.import_controller.start(path):
            self.statusBar().showMessage("Đang kiểm tra và nhập dữ liệu mission...")

    def _import_completed(self, value: object) -> None:
        if not isinstance(value, ImportReport):
            self._import_failed("Import worker returned an invalid report")
            return
        self.refresh()
        errors = sum(
            issue.severity is IssueSeverity.ERROR for issue in value.issues
        )
        warnings = sum(
            issue.severity is IssueSeverity.WARNING for issue in value.issues
        )
        if value.persisted:
            self.statusBar().showMessage(
                f"Đã nhập {len(value.images)} ảnh · {warnings} cảnh báo"
            )
            return
        message = (
            f"Mission chưa được lưu vì có {errors} lỗi và {warnings} cảnh báo.\n\n"
            + "\n".join(issue.message for issue in value.issues[:8])
        )
        QMessageBox.warning(self, "Không thể nhập mission", message)
        self.statusBar().showMessage("Dữ liệu import cần được sửa")

    def _import_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Lỗi import", message)
        self.statusBar().showMessage(message)

    def _forward_analysis(self, mission_id: str) -> None:
        self.open_analysis(mission_id)
        self.analysisRequested.emit(mission_id)

    def open_data(self, mission_id: str) -> None:
        if self.data_viewmodel is None:
            self.statusBar().showMessage("Data workspace chưa được cấu hình")
            return
        state = self.data_viewmodel.load(mission_id)
        if state.error_message or state.data is None:
            self.data_workspace.show_error(state.error_message or "Không thể tải dữ liệu")
        else:
            self.data_workspace.set_data(state.data)
        self._selected_mission_id = mission_id
        self.pages.setCurrentWidget(self.data_workspace)
        self._set_nav(self.data_nav)
        self.statusBar().showMessage(f"Dữ liệu · {mission_id}")

    def open_analysis(self, mission_id: str) -> None:
        if self.analysis_viewmodel is None:
            self.statusBar().showMessage("Analysis workspace chưa được cấu hình")
            return
        state = self.analysis_viewmodel.load(mission_id)
        self.analysis_workspace.set_workspace(
            mission_id,
            state.semantic_models,
            state.instance_models,
            state.jobs,
        )
        if state.error_message:
            self.analysis_workspace.show_error(state.error_message)
        self._selected_mission_id = mission_id
        self.pages.setCurrentWidget(self.analysis_workspace)
        self._set_nav(self.analysis_nav)
        self.statusBar().showMessage(f"Phân tích · {mission_id}")

    def open_spatial(self, mission_id: str) -> None:
        if self.spatial_viewmodel is None:
            self.statusBar().showMessage("Spatial workspace chưa được cấu hình")
            return
        state = self.spatial_viewmodel.load(mission_id)
        self._apply_spatial_state(state)
        self._selected_mission_id = mission_id
        self.pages.setCurrentWidget(self.spatial_workspace)
        self._set_nav(self.spatial_nav)
        self.statusBar().showMessage(f"Không gian · {mission_id}")

    def open_report(self, mission_id: str) -> None:
        if self.report_viewmodel is None:
            self.statusBar().showMessage("Report workspace chưa được cấu hình")
            return
        state = self.report_viewmodel.load(mission_id)
        if state.report is not None:
            self.report_workspace.set_report(state.report)
        if state.export is not None:
            self.report_workspace.set_export(state.export)
        if state.error_message:
            self.report_workspace.show_error(state.error_message)
        self._selected_mission_id = mission_id
        self.pages.setCurrentWidget(self.report_workspace)
        self._set_nav(self.report_nav)
        self.statusBar().showMessage(f"Báo cáo · {mission_id}")

    def _open_selected_data(self) -> None:
        if self._selected_mission_id:
            self.open_data(self._selected_mission_id)

    def _open_selected_analysis(self) -> None:
        if self._selected_mission_id:
            self.open_analysis(self._selected_mission_id)

    def _open_selected_spatial(self) -> None:
        if self._selected_mission_id:
            self.open_spatial(self._selected_mission_id)

    def _open_selected_report(self) -> None:
        if self._selected_mission_id:
            self.open_report(self._selected_mission_id)

    def _choose_report_directory(self, mission_id: str) -> None:
        viewmodel = self.report_viewmodel
        controller = self.report_controller
        if viewmodel is None or controller is None:
            return
        directory = QFileDialog.getExistingDirectory(
            self,
            "Chọn thư mục xuất báo cáo",
            "",
        )
        if not directory:
            return
        if not controller.start(lambda: viewmodel.export(Path(directory))):
            self.statusBar().showMessage("Một tác vụ xuất báo cáo đang chạy")
            return
        self.statusBar().showMessage(f"Đang xuất báo cáo · {mission_id}")

    def _report_completed(self, value: object) -> None:
        from uav_crop_analysis.reporting import ReportExport

        if not isinstance(value, ReportExport):
            self._report_failed("Report worker returned an invalid result")
            return
        self.report_workspace.set_export(value)
        self.statusBar().showMessage(f"Đã xuất báo cáo · {value.directory}")

    def _report_failed(self, message: str) -> None:
        self.report_workspace.show_error(message)
        self.statusBar().showMessage(message)

    @staticmethod
    def _open_report_file(path: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _build_spatial_preview(self, mission_id: str) -> None:
        viewmodel = self.spatial_viewmodel
        if viewmodel is None:
            return
        self._start_spatial_operation(
            "preview",
            lambda _progress: viewmodel.build_preview(mission_id),
        )

    def _choose_orthomosaic(self, mission_id: str) -> None:
        viewmodel = self.spatial_viewmodel
        if viewmodel is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn orthomosaic GeoTIFF",
            "",
            "GeoTIFF (*.tif *.tiff)",
        )
        if path:
            self._start_spatial_operation(
                "import_orthomosaic",
                lambda _progress: viewmodel.import_orthomosaic(mission_id, Path(path)),
            )

    def _create_orthomosaic(self, mission_id: str) -> None:
        viewmodel = self.spatial_viewmodel
        if viewmodel is None:
            return
        self._start_spatial_operation(
            "nodeodm",
            lambda progress: viewmodel.create_orthomosaic(mission_id, progress),
        )

    def _analyze_orthomosaic(self, product_id: str, request: object) -> None:
        from uav_crop_analysis.application.analysis_workspace import AnalysisRequest

        if self.spatial_viewmodel is None or not isinstance(request, AnalysisRequest):
            return
        try:
            job = self.spatial_viewmodel.submit_analysis(product_id, request)
        except Exception as exc:
            self._spatial_failed("analysis", str(exc) or type(exc).__name__)
            return
        self.spatial_workspace.show_message(f"Đã đưa job {job.job_id} vào hàng đợi.")
        self._refresh_spatial(poll_jobs=False)

    def _export_heatmap(self, product_id: str, job_id: str) -> None:
        viewmodel = self.spatial_viewmodel
        if viewmodel is None:
            return
        self._start_spatial_operation(
            "heatmap",
            lambda _progress: viewmodel.export_heatmap(product_id, job_id),
        )

    def _start_spatial_operation(
        self,
        operation: str,
        action: Callable[[ProgressCallback], object],
    ) -> None:
        if self.spatial_controller is None:
            return
        if not self.spatial_controller.start(operation, action):
            self.statusBar().showMessage("Một tác vụ không gian đang chạy")
            return
        self.statusBar().showMessage(f"Đang xử lý {operation}...")

    def _spatial_completed(self, operation: str, _value: object) -> None:
        self._refresh_spatial(poll_jobs=False)
        messages = {
            "preview": "Đã tạo preview không georeference.",
            "import_orthomosaic": "Đã nhập orthomosaic GeoTIFF.",
            "nodeodm": "NodeODM đã tạo orthomosaic.",
            "heatmap": "Đã xuất heatmap GeoTIFF.",
        }
        message = messages.get(operation, "Tác vụ không gian hoàn tất.")
        self.spatial_workspace.show_message(message)
        self.statusBar().showMessage(message)

    def _spatial_failed(self, operation: str, message: str) -> None:
        self.spatial_workspace.show_error(message)
        self.statusBar().showMessage(f"{operation}: {message}")

    def _refresh_spatial(self, *, poll_jobs: bool) -> None:
        if self.spatial_viewmodel is None or self._selected_mission_id is None:
            return
        state = self.spatial_viewmodel.load(
            self._selected_mission_id,
            poll_jobs=poll_jobs,
        )
        self._apply_spatial_state(state)

    def _apply_spatial_state(self, state: object) -> None:
        from uav_crop_analysis.ui.phase7_viewmodels import SpatialWorkspaceState

        if not isinstance(state, SpatialWorkspaceState):
            return
        if state.workspace is not None:
            self.spatial_workspace.set_workspace(
                state.workspace,
                state.semantic_models,
                state.product_jobs,
            )
        if state.error_message:
            self.spatial_workspace.show_error(state.error_message)

    def _submit_analysis(self, request: object) -> None:
        from uav_crop_analysis.application.analysis_workspace import AnalysisRequest

        if self.analysis_viewmodel is None or not isinstance(request, AnalysisRequest):
            return
        state = self.analysis_viewmodel.submit(request)
        self._apply_analysis_state(state)

    def _cancel_analysis(self, job_id: str) -> None:
        if self.analysis_viewmodel is not None:
            self._apply_analysis_state(self.analysis_viewmodel.cancel(job_id))

    def _retry_analysis(self, job_id: str) -> None:
        if self.analysis_viewmodel is not None:
            self._apply_analysis_state(self.analysis_viewmodel.retry(job_id))

    def _poll_analysis_jobs(self) -> None:
        if (
            self.pages.currentWidget() is self.spatial_workspace
            and self.spatial_workspace.has_active_jobs()
        ):
            self._refresh_spatial(poll_jobs=True)
            return
        if (
            self.analysis_viewmodel is None
            or self.analysis_viewmodel.state.mission_id is None
            or not self.analysis_workspace.has_active_jobs()
        ):
            return
        self._apply_analysis_state(self.analysis_viewmodel.refresh())

    def _apply_analysis_state(self, state: object) -> None:
        from uav_crop_analysis.ui.phase6_viewmodels import AnalysisWorkspaceState

        if not isinstance(state, AnalysisWorkspaceState):
            return
        self.analysis_workspace.set_jobs(state.jobs)
        if state.error_message:
            self.analysis_workspace.show_error(state.error_message)
            self.statusBar().showMessage(state.error_message)

    def _set_nav(self, button: QPushButton | None) -> None:
        if button is None:
            self.nav_group.setExclusive(False)
            for item in (
                self.missions_nav,
                self.data_nav,
                self.analysis_nav,
                self.spatial_nav,
                self.report_nav,
            ):
                item.setChecked(False)
            self.nav_group.setExclusive(True)
        else:
            button.setChecked(True)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.job_timer.stop()
        if self.analysis_viewmodel is not None:
            self.analysis_viewmodel.shutdown()
        if self.import_controller is not None:
            self.import_controller.shutdown()
        if self.spatial_controller is not None:
            self.spatial_controller.shutdown()
        if self.report_controller is not None:
            self.report_controller.shutdown()
        super().closeEvent(event)
