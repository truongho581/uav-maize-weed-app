"""Main application shell and mission navigation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer, Qt, QUrl, Signal
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
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.adapters import (
    GreenEyeMissionBundleInitializer,
    has_greeneye_bundle_media,
)
from uav_crop_analysis.application import (
    AnalysisTask,
    ImportReport,
    IssueSeverity,
    ModelTestRequest,
    ModelTestResult,
    ModelTestService,
)
from uav_crop_analysis.geospatial import ProgressCallback
from uav_crop_analysis.model_names import display_model_name
from uav_crop_analysis.ui.branding import APP_DISPLAY_NAME, APP_TAGLINE
from uav_crop_analysis.ui.help import HELP_CONTENTS, HelpContent, InfoButton
from uav_crop_analysis.ui.import_controller import MissionImportController
from uav_crop_analysis.ui.icons import ICON_ON_DARK, lucide_icon, set_button_icon
from uav_crop_analysis.ui.phase6_viewmodels import (
    AnalysisWorkspaceViewModel,
    DataWorkspaceViewModel,
)
from uav_crop_analysis.ui.phase7_viewmodels import SpatialWorkspaceViewModel
from uav_crop_analysis.ui.planning_viewmodels import (
    PlanningDraft,
    PlanningWorkspaceState,
    PlanningWorkspaceViewModel,
)
from uav_crop_analysis.ui.report_controller import ReportExportController
from uav_crop_analysis.ui.report_viewmodels import ReportWorkspaceViewModel
from uav_crop_analysis.ui.spatial_controller import SpatialTaskController
from uav_crop_analysis.ui.viewmodels import MissionCreateDraft, MissionWorkspaceViewModel
from uav_crop_analysis.ui.views.common import divider
from uav_crop_analysis.ui.views import (
    AnalysisWorkspacePage,
    DataWorkspacePage,
    MissionListPage,
    MissionOverviewPage,
    MissionPlannerPage,
    ModelTestWorkspacePage,
    ReportWorkspacePage,
    SpatialWorkspacePage,
)


def _configure_nav_icon(button: QPushButton, icon: str, label: str) -> None:
    button.setFixedHeight(44)
    button.setToolTip(label)
    button.setAccessibleName(label)
    set_button_icon(button, icon, color=ICON_ON_DARK, size=21)


def _setting_bool(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


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
        model_test_service: ModelTestService | None = None,
        planning_viewmodel: PlanningWorkspaceViewModel | None = None,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__()
        self.viewmodel = viewmodel
        self.data_viewmodel = data_viewmodel
        self.analysis_viewmodel = analysis_viewmodel
        self.import_controller = import_controller
        self.spatial_viewmodel = spatial_viewmodel
        self.report_viewmodel = report_viewmodel
        self.model_test_service = model_test_service
        self.planning_viewmodel = planning_viewmodel
        self.settings = settings if settings is not None else QSettings()
        self._sidebar_expanded = _setting_bool(
            self.settings.value("ui/sidebar_expanded", False)
        )
        self.spatial_controller = (
            SpatialTaskController(self) if spatial_viewmodel is not None else None
        )
        self.report_controller = (
            ReportExportController(self) if report_viewmodel is not None else None
        )
        self.model_test_controller = (
            SpatialTaskController(self) if model_test_service is not None else None
        )
        self.planning_controller = (
            SpatialTaskController(self) if planning_viewmodel is not None else None
        )
        self._pending_media_imports: list[Path] = []
        self._auto_media_import_active = False
        self._selected_mission_id: str | None = None
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setMinimumSize(1024, 680)
        self.resize(1366, 768)

        shell = QWidget()
        shell.setObjectName("AppShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self._build_sidebar())

        self.pages = QStackedWidget()
        self.mission_list = MissionListPage(self.settings)
        self.planning_workspace = (
            MissionPlannerPage() if planning_viewmodel is not None else QWidget()
        )
        self.model_test_workspace = ModelTestWorkspacePage()
        self.overview = MissionOverviewPage()
        self.data_workspace = DataWorkspacePage()
        self.analysis_workspace = AnalysisWorkspacePage()
        self.spatial_workspace = SpatialWorkspacePage()
        self.report_workspace = ReportWorkspacePage()
        self.pages.addWidget(self.mission_list)
        self.pages.addWidget(self.planning_workspace)
        self.pages.addWidget(self.model_test_workspace)
        self.pages.addWidget(self.overview)
        self.pages.addWidget(self.data_workspace)
        self.pages.addWidget(self.analysis_workspace)
        self.pages.addWidget(self.spatial_workspace)
        self.pages.addWidget(self.report_workspace)
        shell_layout.addWidget(self.pages, 1)
        self.setCentralWidget(shell)

        self.mission_list.refreshRequested.connect(self.refresh)
        self.mission_list.createRequested.connect(self._create_mission)
        self.mission_list.importRequested.connect(self._choose_import_manifest)
        self.mission_list.missionSelected.connect(self.open_mission)
        self.overview.backRequested.connect(self.show_missions)
        self.overview.dataRequested.connect(self.open_data)
        self.overview.analysisRequested.connect(self._forward_analysis)
        self.overview.spatialRequested.connect(self.open_spatial)
        self.overview.reportRequested.connect(self.open_report)
        self.data_workspace.analysisRequested.connect(self._forward_analysis)
        self.data_workspace.cameraProfileSaveRequested.connect(self._save_camera_profile)
        self.analysis_workspace.submitRequested.connect(self._submit_analysis)
        self.analysis_workspace.cancelRequested.connect(self._cancel_analysis)
        self.analysis_workspace.retryRequested.connect(self._retry_analysis)
        self.analysis_workspace.deleteRequested.connect(self._delete_analysis)
        self.spatial_workspace.previewRequested.connect(self._build_spatial_preview)
        self.spatial_workspace.importRequested.connect(self._choose_orthomosaic)
        self.spatial_workspace.nodeOdmRequested.connect(self._create_orthomosaic)
        self.spatial_workspace.analyzeRequested.connect(self._analyze_orthomosaic)
        self.spatial_workspace.heatmapRequested.connect(self._export_heatmap)
        self.report_workspace.exportRequested.connect(self._choose_report_directory)
        self.report_workspace.openReportRequested.connect(self._open_report_file)
        self.model_test_workspace.sourceRequested.connect(self._choose_model_test_source)
        self.model_test_workspace.testRequested.connect(self._run_model_test)
        if isinstance(self.planning_workspace, MissionPlannerPage):
            self.planning_workspace.calculateRequested.connect(self._calculate_plan)
            self.planning_workspace.exportRequested.connect(self._choose_plan_directory)
            self.planning_workspace.clearPlanRequested.connect(self._clear_plan)
        if self.import_controller is not None:
            self.import_controller.busyChanged.connect(self.mission_list.set_import_busy)
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
        if self.model_test_controller is not None:
            self.model_test_controller.busyChanged.connect(
                self.model_test_workspace.set_busy
            )
            self.model_test_controller.progress.connect(
                self.model_test_workspace.set_progress
            )
            self.model_test_controller.completed.connect(self._model_test_completed)
            self.model_test_controller.failed.connect(self._model_test_failed)
        if self.planning_controller is not None and isinstance(
            self.planning_workspace, MissionPlannerPage
        ):
            self.planning_controller.busyChanged.connect(
                self.planning_workspace.set_busy
            )
            self.planning_controller.completed.connect(self._planning_completed)
            self.planning_controller.failed.connect(self._planning_failed)
        self.job_timer = QTimer(self)
        self.job_timer.setInterval(300)
        self.job_timer.timeout.connect(self._poll_analysis_jobs)
        self.job_timer.start()
        self._install_shortcuts()
        self.statusBar().showMessage("Sẵn sàng")
        self.refresh()
        QTimer.singleShot(250, self._discover_mission_media)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        self.sidebar = sidebar
        sidebar.setObjectName("Sidebar")
        sidebar.setToolTip(f"{APP_DISPLAY_NAME} · {APP_TAGLINE}")
        sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(6, 14, 6, 12)
        layout.setSpacing(8)

        brand = QWidget()
        brand.setObjectName("SidebarBrand")
        brand.setFixedHeight(48)
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(9, 0, 4, 0)
        brand_layout.setSpacing(10)
        brand_icon = QLabel()
        brand_icon.setPixmap(
            lucide_icon("eye", color="#FFFFFF", size=26).pixmap(26, 26)
        )
        brand_icon.setAccessibleName(APP_DISPLAY_NAME)
        brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_icon.setFixedSize(26, 38)
        brand_layout.addWidget(brand_icon)
        self.brand_copy = QWidget()
        brand_copy_layout = QVBoxLayout(self.brand_copy)
        brand_copy_layout.setContentsMargins(0, 2, 0, 2)
        brand_copy_layout.setSpacing(0)
        brand_title = QLabel(APP_DISPLAY_NAME)
        brand_title.setObjectName("BrandTitle")
        brand_subtitle = QLabel(APP_TAGLINE)
        brand_subtitle.setObjectName("BrandSubtitle")
        brand_copy_layout.addWidget(brand_title)
        brand_copy_layout.addWidget(brand_subtitle)
        brand_layout.addWidget(self.brand_copy, 1)
        layout.addWidget(brand)
        layout.addSpacing(8)

        self.missions_nav = QPushButton()
        self.missions_nav.setObjectName("NavButton")
        self.missions_nav.setCheckable(True)
        self.missions_nav.setChecked(True)
        _configure_nav_icon(self.missions_nav, "clipboard-list", "Nhiệm vụ")
        self.missions_nav.clicked.connect(self.show_missions)
        layout.addWidget(self.missions_nav)
        self.planning_nav = QPushButton()
        self.planning_nav.setObjectName("NavButton")
        self.planning_nav.setCheckable(True)
        self.planning_nav.setEnabled(self.planning_viewmodel is not None)
        _configure_nav_icon(self.planning_nav, "map-pinned", "Lập đường bay")
        self.planning_nav.clicked.connect(self._open_selected_planning)
        layout.addWidget(self.planning_nav)
        self.data_nav = QPushButton()
        self.data_nav.setObjectName("NavButton")
        self.data_nav.setCheckable(True)
        self.data_nav.setEnabled(False)
        _configure_nav_icon(self.data_nav, "images", "Dữ liệu")
        self.data_nav.clicked.connect(self._open_selected_data)
        layout.addWidget(self.data_nav)
        self.analysis_nav = QPushButton()
        self.analysis_nav.setObjectName("NavButton")
        self.analysis_nav.setCheckable(True)
        self.analysis_nav.setEnabled(False)
        _configure_nav_icon(self.analysis_nav, "scan-search", "Xử lý ảnh")
        self.analysis_nav.clicked.connect(self._open_selected_analysis)
        layout.addWidget(self.analysis_nav)
        self.spatial_nav = QPushButton()
        self.spatial_nav.setObjectName("NavButton")
        self.spatial_nav.setCheckable(True)
        self.spatial_nav.setEnabled(False)
        _configure_nav_icon(self.spatial_nav, "map", "Bản đồ")
        self.spatial_nav.clicked.connect(self._open_selected_spatial)
        layout.addWidget(self.spatial_nav)
        self.report_nav = QPushButton()
        self.report_nav.setObjectName("NavButton")
        self.report_nav.setCheckable(True)
        self.report_nav.setEnabled(False)
        _configure_nav_icon(self.report_nav, "file-chart-column", "Báo cáo")
        self.report_nav.clicked.connect(self._open_selected_report)
        layout.addWidget(self.report_nav)
        layout.addStretch()
        utilities_divider = divider()
        utilities_divider.setObjectName("SidebarDivider")
        layout.addWidget(utilities_divider)
        self.model_test_nav = QPushButton()
        self.model_test_nav.setObjectName("NavButton")
        self.model_test_nav.setCheckable(True)
        self.model_test_nav.setEnabled(self.model_test_service is not None)
        _configure_nav_icon(self.model_test_nav, "camera", "Kiểm tra mô hình")
        self.model_test_nav.clicked.connect(self.open_model_test)
        layout.addWidget(self.model_test_nav)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_group.addButton(self.missions_nav)
        self.nav_group.addButton(self.model_test_nav)
        self.nav_group.addButton(self.planning_nav)
        self.nav_group.addButton(self.data_nav)
        self.nav_group.addButton(self.analysis_nav)
        self.nav_group.addButton(self.spatial_nav)
        self.nav_group.addButton(self.report_nav)
        self._nav_items = (
            (self.missions_nav, "Nhiệm vụ"),
            (self.planning_nav, "Lập đường bay"),
            (self.data_nav, "Dữ liệu"),
            (self.analysis_nav, "Xử lý ảnh"),
            (self.spatial_nav, "Bản đồ"),
            (self.report_nav, "Báo cáo"),
            (self.model_test_nav, "Kiểm tra mô hình"),
        )
        self.help_button = InfoButton(self._current_help_content)
        layout.addWidget(self.help_button)
        self.sidebar_toggle = QPushButton()
        self.sidebar_toggle.setObjectName("SidebarActionButton")
        self.sidebar_toggle.setFixedHeight(44)
        self.sidebar_toggle.clicked.connect(self.toggle_sidebar)
        layout.addWidget(self.sidebar_toggle)
        self.set_sidebar_expanded(self._sidebar_expanded, persist=False)
        return sidebar

    def set_sidebar_expanded(self, expanded: bool, *, persist: bool = True) -> None:
        self._sidebar_expanded = bool(expanded)
        width = 212 if expanded else 56
        action_width = 200 if expanded else 44
        self.sidebar.setFixedWidth(width)
        self.brand_copy.setVisible(expanded)
        for button, label in self._nav_items:
            button.setText(label if expanded else "")
            button.setFixedWidth(action_width)
            button.setProperty("sidebarExpanded", expanded)
            button.style().unpolish(button)
            button.style().polish(button)
        self.help_button.set_expanded(expanded)
        self.sidebar_toggle.setText("Thu gọn" if expanded else "")
        self.sidebar_toggle.setFixedWidth(action_width)
        self.sidebar_toggle.setToolTip(
            "Thu gọn thanh điều hướng" if expanded else "Mở rộng thanh điều hướng"
        )
        self.sidebar_toggle.setAccessibleName(self.sidebar_toggle.toolTip())
        set_button_icon(
            self.sidebar_toggle,
            "chevron-left" if expanded else "chevron-right",
            color=ICON_ON_DARK,
            size=20,
        )
        self.sidebar_toggle.setProperty("sidebarExpanded", expanded)
        self.sidebar_toggle.style().unpolish(self.sidebar_toggle)
        self.sidebar_toggle.style().polish(self.sidebar_toggle)
        if persist:
            self.settings.setValue("ui/sidebar_expanded", expanded)
            self.settings.sync()

    def toggle_sidebar(self) -> None:
        self.set_sidebar_expanded(not self._sidebar_expanded)

    def _current_help_content(self) -> HelpContent:
        current = self.pages.currentWidget() if hasattr(self, "pages") else None
        if current is self.overview:
            return HELP_CONTENTS["overview"]
        if current is self.model_test_workspace:
            return HELP_CONTENTS["model_test"]
        if current is self.planning_workspace:
            return HELP_CONTENTS["planning"]
        if current is self.data_workspace:
            return HELP_CONTENTS["data"]
        if current is self.analysis_workspace:
            return HELP_CONTENTS["analysis"]
        if current is self.spatial_workspace:
            return HELP_CONTENTS["spatial"]
        if current is self.report_workspace:
            return HELP_CONTENTS["report"]
        return HELP_CONTENTS["missions"]

    def _install_shortcuts(self) -> None:
        refresh = QShortcut(QKeySequence.StandardKey.Refresh, self)
        refresh.activated.connect(self.refresh)
        find = QShortcut(QKeySequence.StandardKey.Find, self)
        find.activated.connect(self._focus_search)
        back = QShortcut(QKeySequence("Alt+Left"), self)
        back.activated.connect(self.show_missions)
        help_contents = QShortcut(QKeySequence.StandardKey.HelpContents, self)
        help_contents.activated.connect(self.help_button.show_help)

    def refresh(self) -> None:
        state = self.viewmodel.refresh()
        if state.error_message:
            self.mission_list.show_error()
            self.statusBar().showMessage(state.error_message)
            return
        self.mission_list.set_missions(state.missions)
        self.mission_list.set_camera_profiles(state.camera_profiles)
        self.statusBar().showMessage(f"{len(state.missions)} nhiệm vụ")

    def _create_mission(self, value: object) -> None:
        if not isinstance(value, MissionCreateDraft):
            return
        state = self.viewmodel.create_mission(value)
        if state.error_message:
            QMessageBox.warning(self, "Không thể tạo nhiệm vụ", state.error_message)
            self.statusBar().showMessage(state.error_message)
            return
        try:
            bundle = GreenEyeMissionBundleInitializer().create(
                mission_id=value.mission_id,
                name=value.name,
                drone_ids=value.drone_ids,
                flight_profile=value.flight_profile,
                camera_profile=value.camera_profile,
                output_root=self._mission_library_parent(),
            )
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            QMessageBox.warning(self, "Không thể tạo thư mục nhiệm vụ", message)
            self.statusBar().showMessage(message)
            return
        self.settings.setValue("mission_library/root", str(bundle.parent))
        self.mission_list.set_missions(state.missions)
        self.mission_list.set_camera_profiles(state.camera_profiles)
        self.statusBar().showMessage(f"Đã tạo nhiệm vụ · {bundle}")
        self.open_planning(value.mission_id)

    def open_mission(self, mission_id: str) -> None:
        state = self.viewmodel.select_mission(mission_id)
        if state.error_message or state.overview is None:
            self.mission_list.show_error()
            self.statusBar().showMessage(state.error_message or "Không thể mở nhiệm vụ")
            return
        self.overview.set_overview(state.overview)
        self._selected_mission_id = mission_id
        self.data_nav.setEnabled(self.data_viewmodel is not None)
        self.planning_nav.setEnabled(self.planning_viewmodel is not None)
        self.analysis_nav.setEnabled(self.analysis_viewmodel is not None)
        self.spatial_nav.setEnabled(self.spatial_viewmodel is not None)
        self.report_nav.setEnabled(self.report_viewmodel is not None)
        self.pages.setCurrentWidget(self.overview)
        self._set_nav(None)
        self.statusBar().showMessage(state.overview.mission.name)

    def show_missions(self) -> None:
        self.refresh()
        self.pages.setCurrentWidget(self.mission_list)
        self._set_nav(self.missions_nav)
        self.statusBar().showMessage(f"{len(self.viewmodel.state.missions)} nhiệm vụ")

    def open_model_test(self) -> None:
        service = self.model_test_service
        if service is None:
            self.statusBar().showMessage("Kiểm tra mô hình chưa được cấu hình")
            return
        try:
            self.model_test_workspace.set_models(
                service.list_models(AnalysisTask.SEMANTIC),
                service.list_models(AnalysisTask.MAIZE_INSTANCE),
            )
        except Exception as exc:
            self.model_test_workspace.show_error(str(exc) or type(exc).__name__)
        self.pages.setCurrentWidget(self.model_test_workspace)
        self._set_nav(self.model_test_nav)
        self.statusBar().showMessage("Kiểm tra mô hình")

    def open_planning(self, mission_id: str) -> None:
        viewmodel = self.planning_viewmodel
        page = self.planning_workspace
        if viewmodel is None or not isinstance(page, MissionPlannerPage):
            self.statusBar().showMessage("Khu vực lập đường bay chưa được cấu hình")
            return
        state = viewmodel.load(mission_id)
        if state.workspace is not None:
            page.set_workspace(state.workspace, state.plan)
        if state.error_message:
            page.show_error(state.error_message)
        self._selected_mission_id = mission_id
        self.pages.setCurrentWidget(page)
        self._set_nav(self.planning_nav)
        self.statusBar().showMessage(f"Lập đường bay · {mission_id}")

    def _choose_model_test_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn ảnh hoặc video kiểm tra",
            "",
            (
                "Ảnh và video (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp "
                "*.mp4 *.mov *.avi *.mkv *.m4v);;Ảnh (*.jpg *.jpeg *.png *.tif "
                "*.tiff *.bmp *.webp);;Video (*.mp4 *.mov *.avi *.mkv *.m4v)"
            ),
        )
        if path:
            self.model_test_workspace.set_source(Path(path))

    def _run_model_test(self, request: object) -> None:
        service = self.model_test_service
        controller = self.model_test_controller
        if (
            service is None
            or controller is None
            or not isinstance(request, ModelTestRequest)
        ):
            return
        if not controller.start(
            "model_test",
            lambda progress: service.run(request, progress),
        ):
            self.statusBar().showMessage("Một lượt kiểm tra mô hình đang chạy")
            return
        self.statusBar().showMessage("Đang kiểm tra mô hình...")

    def _model_test_completed(self, operation: str, value: object) -> None:
        if operation != "model_test" or not isinstance(value, ModelTestResult):
            self._model_test_failed("model_test", "Kết quả kiểm tra không hợp lệ")
            return
        self.model_test_workspace.set_result(value)
        self.statusBar().showMessage(
            f"Đã kiểm tra {value.frame_count} khung · "
            f"{display_model_name(value.job.config.model_id)}"
        )

    def _model_test_failed(self, _operation: str, message: str) -> None:
        self.model_test_workspace.show_error(message)
        self.statusBar().showMessage(f"Kiểm tra mô hình: {message}")

    def _focus_search(self) -> None:
        self.show_missions()
        self.mission_list.focus_search()

    def _choose_import_manifest(self) -> None:
        if self.import_controller is None:
            self.statusBar().showMessage("Chức năng nhập nhiệm vụ chưa được cấu hình")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp mô tả nhiệm vụ",
            "",
            "Tệp nhiệm vụ (mission.json *.json);;JSON (*.json)",
        )
        if path and self.import_controller.start(path):
            self.statusBar().showMessage("Đang kiểm tra và nhập dữ liệu nhiệm vụ...")

    def _discover_mission_media(self) -> None:
        """Import media added after a GreenEye route bundle was exported."""
        if self.import_controller is None:
            return
        value = self.settings.value("mission_library/root", "")
        root = Path(str(value)).expanduser()
        if not root.is_dir():
            return
        self._pending_media_imports = [
            directory
            for directory in sorted(root.iterdir(), key=lambda path: path.name.casefold())
            if directory.is_dir()
            and not directory.name.startswith(".")
            and has_greeneye_bundle_media(directory)
        ]
        self._start_next_media_import()

    def _mission_library_parent(self) -> Path:
        value = self.settings.value("mission_library/root", "")
        if str(value).strip():
            root = Path(str(value)).expanduser()
            return root.parent if root.name == "GreenEye mission" else root
        return Path.home() / "Documents"

    def _start_next_media_import(self) -> None:
        controller = self.import_controller
        if controller is None or not self._pending_media_imports:
            return
        if controller.is_busy:
            QTimer.singleShot(150, self._start_next_media_import)
            return
        directory = self._pending_media_imports.pop(0)
        self._auto_media_import_active = controller.start(directory)
        if self._auto_media_import_active:
            self.statusBar().showMessage(f"Đang nhận media · {directory.name}")

    def _import_completed(self, value: object) -> None:
        if not isinstance(value, ImportReport):
            self._import_failed("Bộ nhập dữ liệu trả về kết quả không hợp lệ")
            return
        automatic = self._auto_media_import_active
        self._auto_media_import_active = False
        self.refresh()
        errors = sum(issue.severity is IssueSeverity.ERROR for issue in value.issues)
        warnings = sum(issue.severity is IssueSeverity.WARNING for issue in value.issues)
        if value.persisted:
            prefix = "Đã tự nhận" if automatic else "Đã nhập"
            self.statusBar().showMessage(f"{prefix} {len(value.images)} ảnh · {warnings} cảnh báo")
            if automatic:
                QTimer.singleShot(150, self._start_next_media_import)
            return
        if automatic:
            self.statusBar().showMessage(
                f"Media của {value.mission_id} cần kiểm tra trước khi xử lý"
            )
            QTimer.singleShot(150, self._start_next_media_import)
            return
        message = (
            f"Nhiệm vụ chưa được lưu vì có {errors} lỗi và {warnings} cảnh báo.\n\n"
            + "\n".join(issue.message for issue in value.issues[:8])
        )
        QMessageBox.warning(self, "Không thể nhập nhiệm vụ", message)
        self.statusBar().showMessage("Dữ liệu đầu vào cần được sửa")

    def _import_failed(self, message: str) -> None:
        if self._auto_media_import_active:
            self._auto_media_import_active = False
            self.statusBar().showMessage(f"Không thể tự nhận media: {message}")
            QTimer.singleShot(150, self._start_next_media_import)
            return
        QMessageBox.critical(self, "Lỗi nhập dữ liệu", message)
        self.statusBar().showMessage(message)

    def _forward_analysis(self, mission_id: str) -> None:
        self.open_analysis(mission_id)
        self.analysisRequested.emit(mission_id)

    def _save_camera_profile(self, value: object) -> None:
        if self.data_viewmodel is None or not isinstance(value, tuple) or len(value) != 2:
            return
        profile, drone_ids = value
        from uav_crop_analysis.domain import CameraProfile

        if not isinstance(profile, CameraProfile) or not isinstance(drone_ids, tuple):
            return
        state = self.data_viewmodel.save_camera_profile(profile, drone_ids)
        if state.data is not None:
            self.data_workspace.set_data(state.data)
            self.statusBar().showMessage("Đã lưu hồ sơ máy ảnh và cập nhật GSD")
        elif state.error_message:
            self.data_workspace.show_error(state.error_message)
            self.statusBar().showMessage(state.error_message)

    def open_data(self, mission_id: str) -> None:
        if self.data_viewmodel is None:
            self.statusBar().showMessage("Khu vực dữ liệu chưa được cấu hình")
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
            self.statusBar().showMessage("Khu vực xử lý chưa được cấu hình")
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
        self.statusBar().showMessage(f"Xử lý · {mission_id}")

    def open_spatial(self, mission_id: str) -> None:
        if self.spatial_viewmodel is None:
            self.statusBar().showMessage("Khu vực bản đồ chưa được cấu hình")
            return
        state = self.spatial_viewmodel.load(mission_id)
        self._apply_spatial_state(state)
        self._selected_mission_id = mission_id
        self.pages.setCurrentWidget(self.spatial_workspace)
        self._set_nav(self.spatial_nav)
        self.statusBar().showMessage(f"Bản đồ · {mission_id}")

    def open_report(self, mission_id: str) -> None:
        if self.report_viewmodel is None:
            self.statusBar().showMessage("Khu vực báo cáo chưa được cấu hình")
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

    def _open_selected_planning(self) -> None:
        if self._selected_mission_id:
            self.open_planning(self._selected_mission_id)
            return
        self.show_missions()
        self.mission_list.open_create_dialog()

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

    def _calculate_plan(self, value: object) -> None:
        viewmodel = self.planning_viewmodel
        controller = self.planning_controller
        if viewmodel is None or controller is None or not isinstance(value, PlanningDraft):
            return
        if not controller.start(
            "calculate",
            lambda _progress: viewmodel.calculate(value),
        ):
            self.statusBar().showMessage("Một tác vụ lập đường bay đang chạy")
            return
        self.statusBar().showMessage("Đang tính đường bay…")

    def _choose_plan_directory(self, mission_id: str) -> None:
        viewmodel = self.planning_viewmodel
        controller = self.planning_controller
        if viewmodel is None or controller is None:
            return
        directory = QFileDialog.getExistingDirectory(
            self,
            "Chọn thư mục xuất nhiệm vụ",
            str(self._mission_library_parent()),
        )
        if not directory:
            return
        if not controller.start(
            "export",
            lambda _progress: viewmodel.export(Path(directory)),
        ):
            self.statusBar().showMessage("Một tác vụ lập đường bay đang chạy")
            return
        self.statusBar().showMessage(f"Đang xuất nhiệm vụ · {mission_id}")

    def _clear_plan(self, mission_id: str) -> None:
        viewmodel = self.planning_viewmodel
        if viewmodel is None:
            return
        state = viewmodel.discard(mission_id)
        if state.error_message:
            self._planning_failed("clear", state.error_message)
            return
        self.statusBar().showMessage("Đã xóa ranh giới và đường bay")

    def _planning_completed(self, operation: str, value: object) -> None:
        if not isinstance(value, PlanningWorkspaceState):
            self._planning_failed(operation, "Kết quả lập đường bay không hợp lệ")
            return
        self._apply_planning_state(value)
        if value.error_message:
            return
        if operation == "calculate" and value.plan is not None:
            message = (
                f"Đã tính {len(value.plan.routes)} tuyến · "
                f"{value.plan.capture_count} điểm chụp"
            )
        elif operation == "export" and value.exported is not None:
            self.settings.setValue("mission_library/root", str(value.exported.directory.parent))
            message = f"Đã xuất nhiệm vụ · {value.exported.directory}"
        else:
            message = "Tác vụ lập đường bay hoàn tất"
        if isinstance(self.planning_workspace, MissionPlannerPage):
            self.planning_workspace.show_message(message)
        self.statusBar().showMessage(message)

    def _planning_failed(self, _operation: str, message: str) -> None:
        if isinstance(self.planning_workspace, MissionPlannerPage):
            self.planning_workspace.show_error(message)
        self.statusBar().showMessage(f"Lập đường bay: {message}")

    def _apply_planning_state(self, state: PlanningWorkspaceState) -> None:
        page = self.planning_workspace
        if not isinstance(page, MissionPlannerPage):
            return
        if state.plan is not None:
            page.set_plan(state.plan)
        if state.error_message:
            page.show_error(state.error_message)

    def _report_completed(self, value: object) -> None:
        from uav_crop_analysis.reporting import ReportExport

        if not isinstance(value, ReportExport):
            self._report_failed("Bộ xuất báo cáo trả về kết quả không hợp lệ")
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
            "Chọn ảnh ghép GeoTIFF",
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
        self.spatial_workspace.show_message(f"Đã đưa tác vụ {job.job_id} vào hàng đợi.")
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
            self.statusBar().showMessage("Một tác vụ bản đồ đang chạy")
            return
        operation_names = {
            "preview": "ảnh xem nhanh",
            "import_orthomosaic": "ảnh ghép được nhập",
            "nodeodm": "ảnh ghép",
            "heatmap": "bản đồ mật độ cỏ dại",
        }
        self.statusBar().showMessage(
            f"Đang tạo {operation_names.get(operation, 'sản phẩm bản đồ')}..."
        )

    def _spatial_completed(self, operation: str, value: object) -> None:
        self._refresh_spatial(poll_jobs=False)
        from uav_crop_analysis.geospatial import SpatialProduct

        if operation == "nodeodm" and isinstance(value, SpatialProduct):
            self.spatial_workspace.select_product(value.product_id)
        messages = {
            "preview": "Đã tạo ảnh xem nhanh, không có tọa độ.",
            "import_orthomosaic": "Đã nhập ảnh ghép GeoTIFF.",
            "nodeodm": "NodeODM đã dựng và mở ảnh ghép GeoTIFF.",
            "heatmap": "Đã tạo bản đồ mật độ cỏ dại GeoTIFF.",
        }
        message = messages.get(operation, "Tác vụ không gian hoàn tất.")
        self.spatial_workspace.show_message(message)
        self.statusBar().showMessage(message)

    def _spatial_failed(self, operation: str, message: str) -> None:
        self.spatial_workspace.show_error(message)
        operation_names = {
            "analysis": "Phân tích cỏ dại",
            "preview": "Ảnh xem nhanh",
            "import_orthomosaic": "Nhập ảnh ghép",
            "nodeodm": "Dựng ảnh ghép",
            "heatmap": "Bản đồ mật độ cỏ dại",
        }
        self.statusBar().showMessage(
            f"{operation_names.get(operation, 'Tác vụ bản đồ')}: {message}"
        )

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
        if state.error_message is None:
            self.statusBar().showMessage("Đã đưa tác vụ xử lý vào hàng đợi")

    def _cancel_analysis(self, job_id: str) -> None:
        if self.analysis_viewmodel is not None:
            self._apply_analysis_state(self.analysis_viewmodel.cancel(job_id))

    def _retry_analysis(self, job_id: str) -> None:
        if self.analysis_viewmodel is not None:
            self._apply_analysis_state(self.analysis_viewmodel.retry(job_id))

    def _delete_analysis(self, job_id: str) -> None:
        if self.analysis_viewmodel is None:
            return
        answer = QMessageBox.question(
            self,
            "Xóa tác vụ xử lý",
            "Xóa tác vụ này cùng toàn bộ mặt nạ, ảnh chồng lớp và tệp kết quả?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Discard:
            return
        state = self.analysis_viewmodel.delete(job_id)
        self._apply_analysis_state(state)
        if state.error_message is None:
            self.statusBar().showMessage("Đã xóa tác vụ xử lý và kết quả")

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
                self.model_test_nav,
                self.planning_nav,
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
        if self.model_test_controller is not None:
            self.model_test_controller.shutdown()
        if self.planning_controller is not None:
            self.planning_controller.shutdown()
        super().closeEvent(event)
