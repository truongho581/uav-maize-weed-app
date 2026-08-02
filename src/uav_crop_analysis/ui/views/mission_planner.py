"""Mission-planning workspace with an interactive field map and route review."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSettings,
    QTimer,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application import MissionDataWorkspace
from uav_crop_analysis.planning import CaptureWaypoint, DroneRoute, PlannedMission
from uav_crop_analysis.ui.icons import (
    ICON_ON_PRIMARY,
    configure_icon_button,
    set_button_icon,
)
from uav_crop_analysis.ui.components import metric_row
from uav_crop_analysis.ui.planning_viewmodels import PlanningDraft
from uav_crop_analysis.ui.tokens import COLORS
from uav_crop_analysis.ui.views.common import configure_table


_LEAFLET_CSS = "leaflet.css"
_LEAFLET_JS = "leaflet.js"
_SATELLITE_TILES = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/"
    "MapServer/tile/{z}/{y}/{x}"
)
_ROUTE_COLORS = ("#16724A", "#236C8E", "#A35C00")
_ROUTE_DASHES = (None, "10 6", "3 6")
_DRAFT_VERSION = 2


class _PlannerMapBridge(QObject):
    polygonChanged = Signal(str)
    viewStateChanged = Signal(str)

    @Slot(str)
    def updatePolygon(self, value: str) -> None:  # noqa: N802
        self.polygonChanged.emit(value)

    @Slot(str)
    def updateViewState(self, value: str) -> None:  # noqa: N802
        self.viewStateChanged.emit(value)


class MissionPlannerMap(QWidget):
    polygonChanged = Signal(object)
    viewScaleChanged = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MissionPlannerMap")
        self._loaded = False
        self._pending_polygon: tuple[tuple[float, float], ...] = ()
        self._pending_routes: dict[str, Any] = {"routes": []}
        self.web_view = QWebEngineView(self)
        self.web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        settings = self.web_view.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            True,
        )
        self._bridge = _PlannerMapBridge(self)
        self._channel = QWebChannel(self.web_view.page())
        self._channel.registerObject("plannerBridge", self._bridge)
        self.web_view.page().setWebChannel(self._channel)
        self._bridge.polygonChanged.connect(self._receive_polygon)
        self._bridge.viewStateChanged.connect(self._receive_view_state)
        self.web_view.loadFinished.connect(self._load_finished)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web_view)
        self.web_view.setHtml(build_mission_planner_map_html(), _planner_assets_base_url())

    def set_polygon(
        self,
        points: tuple[tuple[float, float], ...],
        *,
        fit: bool = True,
    ) -> None:
        self._pending_polygon = points
        if self._loaded:
            self._run("plannerSetPolygon", [list(point) for point in points], fit)

    def set_plan(self, plan: PlannedMission | None) -> None:
        self._pending_routes = _map_plan_payload(plan)
        if self._loaded:
            self._run("plannerSetRoutes", self._pending_routes)

    def set_draw_mode(self, enabled: bool) -> None:
        self._run("plannerSetDrawMode", enabled)

    def set_edit_mode(self, enabled: bool) -> None:
        self._run("plannerSetEditMode", enabled)

    def undo_point(self) -> None:
        self._run("plannerUndoPoint")

    def clear_polygon(self) -> None:
        self._run("plannerClearPolygon")

    def fit_content(self) -> None:
        self._run("plannerFitContent")

    def set_route_visible(self, route_index: int, visible: bool) -> None:
        self._run("plannerSetRouteVisible", route_index, visible)

    @Slot(bool)
    def _load_finished(self, successful: bool) -> None:
        self._loaded = successful
        if not successful:
            return
        self.set_polygon(self._pending_polygon, fit=bool(self._pending_polygon))
        self._run("plannerSetRoutes", self._pending_routes)
        # Read the state directly once the document is ready.  The WebChannel
        # emits later as well, but this avoids a stale scale label if it was
        # created after Leaflet's initial move event.
        QTimer.singleShot(0, self._refresh_view_scale)

    @Slot(str)
    def _receive_polygon(self, value: str) -> None:
        try:
            raw = json.loads(value)
            points = tuple((float(item[0]), float(item[1])) for item in raw)
        except (TypeError, ValueError, json.JSONDecodeError, IndexError):
            return
        if any(not math.isfinite(value) for point in points for value in point):
            return
        self._pending_polygon = points
        self.polygonChanged.emit(points)

    @Slot(str)
    def _receive_view_state(self, value: str) -> None:
        try:
            state = json.loads(value)
            meters_per_pixel = float(state["meters_per_pixel"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return
        if math.isfinite(meters_per_pixel) and meters_per_pixel > 0:
            self.viewScaleChanged.emit(meters_per_pixel)

    def _refresh_view_scale(self) -> None:
        if not self._loaded:
            return
        self.web_view.page().runJavaScript(
            "window.plannerGetViewState ? window.plannerGetViewState() : null;",
            self._receive_view_state,
        )

    def _run(self, function: str, *arguments: object) -> None:
        if not self._loaded:
            return
        encoded = ", ".join(json.dumps(argument) for argument in arguments)
        self.web_view.page().runJavaScript(f"window.{function}({encoded});")


class WaypointTableModel(QAbstractTableModel):
    HEADERS = ("STT", "Vĩ độ", "Kinh độ", "AGL", "Dừng", "Làn", "Hành động")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._waypoints: tuple[CaptureWaypoint, ...] = ()

    def set_route(self, route: DroneRoute | None) -> None:
        self.beginResetModel()
        self._waypoints = () if route is None else route.waypoints
        self.endResetModel()

    def rowCount(  # noqa: N802
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> int:
        return 0 if parent.isValid() else len(self._waypoints)

    def columnCount(  # noqa: N802
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._waypoints):
            return None
        waypoint = self._waypoints[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            values = (
                waypoint.sequence + 1,
                f"{waypoint.position.latitude:.7f}",
                f"{waypoint.position.longitude:.7f}",
                f"{waypoint.altitude_agl_m:.1f} m",
                f"{waypoint.hold_seconds:.1f} s",
                waypoint.lane_index + 1,
                "Dừng và chụp",
            )
            return values[index.column()]
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in {0, 3, 4, 5}:
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None


class AdvancedPlanningDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Thiết lập đường bay")
        self.setMinimumWidth(420)
        self.speed = _number_spin(0.5, 15.0, 3.0, " m/s")
        self.pause = _number_spin(0.0, 10.0, 1.0, " s")
        self.heading_mode = QComboBox()
        self.heading_mode.addItem("Tự động theo thửa", None)
        self.heading_mode.addItem("Góc chỉ định", "custom")
        self.heading = _number_spin(0.0, 179.9, 0.0, "°")
        self.heading.setEnabled(False)
        self.heading_mode.currentIndexChanged.connect(
            lambda: self.heading.setEnabled(self.heading_mode.currentData() == "custom")
        )
        self.separation = _number_spin(0.0, 50.0, 2.0, " m")
        form = QFormLayout(self)
        form.setContentsMargins(22, 18, 22, 18)
        form.setSpacing(10)
        form.addRow("Tốc độ hành trình", self.speed)
        form.addRow("Thời gian dừng chụp", self.pause)
        form.addRow("Hướng quét", self.heading_mode)
        form.addRow("Góc quét", self.heading)
        form.addRow("Khoảng cách cảnh báo", self.separation)
        note = QLabel("Độ cao là AGL cố định; phiên bản này chưa bám địa hình.")
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        form.addRow("", note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok is not None:
            ok.setText("Áp dụng")
        if cancel is not None:
            cancel.setText("Hủy")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[float, float, float | None, float]:
        heading = self.heading.value() if self.heading_mode.currentData() == "custom" else None
        return self.speed.value(), self.pause.value(), heading, self.separation.value()

    def set_values(
        self,
        speed: float,
        pause: float,
        heading: float | None,
        separation: float,
    ) -> None:
        self.speed.setValue(speed)
        self.pause.setValue(pause)
        self.heading_mode.setCurrentIndex(0 if heading is None else 1)
        if heading is not None:
            self.heading.setValue(heading)
        self.separation.setValue(separation)


class CoordinateImportDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nhập ranh giới khảo sát")
        self.setMinimumSize(520, 380)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        label = QLabel("Mỗi dòng: vĩ độ, kinh độ")
        label.setObjectName("MutedLabel")
        layout.addWidget(label)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("10.762622, 106.660172\n10.762900, 106.660800")
        layout.addWidget(self.text, 1)
        self.error = QLabel()
        self.error.setObjectName("MutedLabel")
        self.error.setStyleSheet(f"color: {COLORS['danger']};")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok is not None:
            ok.setText("Nhập")
        if cancel is not None:
            cancel.setText("Hủy")
        buttons.accepted.connect(self._accept_coordinates)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.coordinates: tuple[tuple[float, float], ...] = ()

    def set_coordinates(self, points: tuple[tuple[float, float], ...]) -> None:
        self.text.setPlainText("\n".join(f"{lat:.7f}, {lon:.7f}" for lat, lon in points))

    def _accept_coordinates(self) -> None:
        try:
            self.coordinates = parse_coordinate_text(self.text.toPlainText())
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class MissionPlannerPage(QWidget):
    calculateRequested = Signal(object)
    exportRequested = Signal(str)
    clearPlanRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PageSurface")
        self._mission_id: str | None = None
        self._workspace: MissionDataWorkspace | None = None
        self._plan: PlannedMission | None = None
        self._plan_stale = False
        self._polygon: tuple[tuple[float, float], ...] = ()
        self._loading = False
        self.advanced_dialog = AdvancedPlanningDialog(self)
        self.coordinate_dialog = CoordinateImportDialog(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("Lập đường bay")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        self.mission_label = QLabel()
        self.mission_label.setObjectName("MutedLabel")
        header.addWidget(self.mission_label)
        header.addStretch()
        self.draft_status = QLabel("Bản nháp tự động")
        self.draft_status.setObjectName("MutedLabel")
        header.addWidget(self.draft_status)
        root.addLayout(header)

        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.setChildrenCollapsible(False)
        self.settings_panel = self._build_settings_panel()
        horizontal.addWidget(self.settings_panel)

        center_split = QSplitter(Qt.Orientation.Vertical)
        center_split.setChildrenCollapsible(False)
        map_panel = QWidget()
        map_panel.setObjectName("WorkspacePanel")
        map_layout = QVBoxLayout(map_panel)
        map_layout.setContentsMargins(8, 8, 8, 8)
        map_layout.setSpacing(6)
        self.map_view = MissionPlannerMap()
        self.map_view.setMinimumSize(420, 320)
        self.map_view.polygonChanged.connect(self._polygon_changed)
        self.map_view.viewScaleChanged.connect(self._update_map_resolution)
        map_layout.addWidget(self._build_map_toolbar())
        map_layout.addWidget(self.map_view, 1)
        center_split.addWidget(map_panel)
        center_split.addWidget(self._build_waypoint_panel())
        center_split.setSizes([470, 210])
        horizontal.addWidget(center_split)
        self.routes_panel = self._build_routes_panel()
        horizontal.addWidget(self.routes_panel)
        horizontal.setStretchFactor(0, 0)
        horizontal.setStretchFactor(1, 1)
        horizontal.setStretchFactor(2, 0)
        horizontal.setSizes([270, 680, 270])
        root.addWidget(horizontal, 1)

        self.message = QLabel()
        self.message.setObjectName("CameraStatusBar")
        self.message.setMinimumHeight(30)
        root.addWidget(self.message)
        self._update_actions()

    def _build_settings_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("WorkspacePanel")
        panel.setMinimumWidth(248)
        panel.setMaximumWidth(288)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("PlannerSettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea, QScrollArea > QWidget > QWidget {{ background: {COLORS['surface']}; }}"
        )
        body = QWidget()
        body.setObjectName("PlannerSettingsBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        label = QLabel("Thiết lập khảo sát")
        label.setObjectName("PanelTitle")
        heading.addWidget(label)
        heading.addStretch()
        self.advanced_button = QPushButton()
        configure_icon_button(self.advanced_button, "settings-2", "Thiết lập đường bay")
        self.advanced_button.clicked.connect(self._edit_advanced)
        heading.addWidget(self.advanced_button)
        layout.addLayout(heading)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(7)
        self.camera_combo = QComboBox()
        self.camera_combo.setAccessibleName("Hồ sơ máy ảnh")
        self.camera_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.camera_combo.setMinimumContentsLength(12)
        self.camera_combo.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.camera_combo.currentIndexChanged.connect(self._draft_changed)
        form.addRow("Máy ảnh", self.camera_combo)
        self.altitude = _number_spin(10.0, 20.0, 10.0, " m")
        self.altitude.valueChanged.connect(self._draft_changed)
        form.addRow("Độ cao AGL", self.altitude)
        self.forward_overlap = _number_spin(0.0, 95.0, 75.0, "%", decimals=0)
        self.forward_overlap.valueChanged.connect(self._draft_changed)
        form.addRow("Chồng ảnh dọc", self.forward_overlap)
        self.side_overlap = _number_spin(0.0, 95.0, 65.0, "%", decimals=0)
        self.side_overlap.valueChanged.connect(self._draft_changed)
        form.addRow("Chồng ảnh ngang", self.side_overlap)
        self.drone_count = QLabel("—")
        form.addRow("Số drone", self.drone_count)
        layout.addLayout(form)

        layout.addStretch()

        self.calculate_button = QPushButton("Tính đường bay")
        self.calculate_button.setObjectName("PrimaryButton")
        set_button_icon(self.calculate_button, "scan-search", color=ICON_ON_PRIMARY)
        self.calculate_button.clicked.connect(self._calculate)
        layout.addWidget(self.calculate_button)
        self.export_button = QPushButton("Xuất nhiệm vụ")
        set_button_icon(self.export_button, "download")
        self.export_button.clicked.connect(self._export)
        layout.addWidget(self.export_button)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        return panel

    def _build_map_toolbar(self) -> QWidget:
        toolbar = QFrame()
        toolbar.setObjectName("ViewerToolbar")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(5)
        self.draw_button = QPushButton()
        configure_icon_button(self.draw_button, "square-dashed", "Vẽ ranh giới")
        self.draw_button.setCheckable(True)
        self.draw_button.toggled.connect(self._draw_toggled)
        layout.addWidget(self.draw_button)
        self.edit_button = QPushButton()
        configure_icon_button(self.edit_button, "mouse-pointer-2", "Chỉnh sửa đỉnh")
        self.edit_button.setCheckable(True)
        self.edit_button.toggled.connect(self.map_view_set_edit)
        layout.addWidget(self.edit_button)
        undo = QPushButton()
        configure_icon_button(undo, "undo-2", "Hoàn tác đỉnh cuối")
        undo.clicked.connect(self.map_view_undo)
        layout.addWidget(undo)
        imported = QPushButton()
        configure_icon_button(imported, "file-up", "Nhập tọa độ")
        imported.clicked.connect(self._import_coordinates)
        layout.addWidget(imported)
        self.clear_boundary_button = QPushButton()
        self.clear_boundary_button.setObjectName("ClearBoundaryButton")
        self.clear_boundary_button.setAccessibleName("Xóa ranh giới đã vẽ")
        self.clear_boundary_button.setShortcut(QKeySequence.StandardKey.Delete)
        configure_icon_button(
            self.clear_boundary_button,
            "trash-2",
            "Xóa ranh giới đã vẽ (Delete)",
        )
        self.clear_boundary_button.clicked.connect(self.map_view_clear)
        layout.addWidget(self.clear_boundary_button)
        fit = QPushButton()
        configure_icon_button(fit, "map-pinned", "Vừa ranh giới và đường bay")
        fit.clicked.connect(self.map_view.fit_content)
        layout.addWidget(fit)
        layout.addStretch()
        self.vertex_label = QLabel("0 đỉnh")
        self.vertex_label.setObjectName("MapStatusLabel")
        layout.addWidget(self.vertex_label)
        self.map_resolution_label = QLabel("Độ phân giải —")
        self.map_resolution_label.setObjectName("MapStatusLabel")
        self.map_resolution_label.setToolTip(
            "Độ phân giải nền bản đồ ở mức thu phóng hiện tại, không phải GSD ảnh bay."
        )
        layout.addWidget(self.map_resolution_label)
        return toolbar

    @Slot(float)
    def _update_map_resolution(self, meters_per_pixel: float) -> None:
        if meters_per_pixel < 1:
            value = f"{meters_per_pixel * 100:.0f} cm/px"
        else:
            value = f"{meters_per_pixel:.1f} m/px"
        self.map_resolution_label.setText(f"Độ phân giải {value}")

    def _build_waypoint_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("WorkspacePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 7, 8, 8)
        layout.setSpacing(5)
        header = QHBoxLayout()
        title = QLabel("Điểm dừng chụp")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        self.waypoint_summary = QLabel("Chưa có đường bay")
        self.waypoint_summary.setObjectName("MutedLabel")
        header.addWidget(self.waypoint_summary)
        header.addStretch()
        layout.addLayout(header)
        self.waypoint_table = QTableView()
        configure_table(self.waypoint_table, row_height=36)
        self.waypoint_model = WaypointTableModel(self.waypoint_table)
        self.waypoint_table.setModel(self.waypoint_model)
        header_view = self.waypoint_table.horizontalHeader()
        for column in range(7):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if column in {1, 2, 6}
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header_view.setSectionResizeMode(column, mode)
        layout.addWidget(self.waypoint_table)
        return panel

    def _build_routes_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("WorkspacePanel")
        panel.setMinimumWidth(244)
        panel.setMaximumWidth(292)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Tuyến drone")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)
        self.area_value = QLabel("—")
        self.coverage_value = QLabel("—")
        self.capture_value = QLabel("—")
        layout.addWidget(metric_row("Diện tích", self.area_value))
        layout.addWidget(metric_row("Bao phủ", self.coverage_value))
        layout.addWidget(metric_row("Ảnh dự kiến", self.capture_value))
        self.route_table = QTableWidget(0, 4)
        self.route_table.setHorizontalHeaderLabels(("Drone", "Làn", "Ảnh", "Thời gian"))
        configure_table(self.route_table, row_height=42)
        self.route_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.route_table.setMinimumHeight(168)
        self.route_table.setMaximumHeight(190)
        self.route_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.route_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for column in (1, 2, 3):
            self.route_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.route_table.itemSelectionChanged.connect(self._route_selected)
        self.route_table.itemChanged.connect(self._route_item_changed)
        layout.addWidget(self.route_table)
        layout.addWidget(_section_label("Tuyến đang chọn"))
        self.route_distance_value = QLabel("—")
        self.route_duration_value = QLabel("—")
        self.route_lane_value = QLabel("—")
        self.route_capture_value = QLabel("—")
        layout.addWidget(metric_row("Quãng đường quét", self.route_distance_value))
        layout.addWidget(metric_row("Quét và chụp", self.route_duration_value))
        layout.addWidget(metric_row("Số làn", self.route_lane_value))
        layout.addWidget(metric_row("Điểm chụp", self.route_capture_value))
        layout.addWidget(_section_label("Cảnh báo"))
        self.warning_label = QLabel("Chưa có cảnh báo")
        self.warning_label.setObjectName("MutedLabel")
        self.warning_label.setWordWrap(True)
        self.warning_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.warning_label)
        layout.addStretch()
        return panel

    def set_workspace(
        self,
        workspace: MissionDataWorkspace,
        plan: PlannedMission | None,
    ) -> None:
        self._loading = True
        self._workspace = workspace
        self._mission_id = workspace.mission.mission_id.value
        self._plan = plan
        self.mission_label.setText(f"· {workspace.mission.name}")
        self.drone_count.setText(str(len(workspace.mission.assignments)))
        self.camera_combo.clear()
        cameras = {profile.profile_id: profile for profile in workspace.camera_catalog}
        cameras.update({profile.profile_id: profile for profile in workspace.cameras})
        for profile in sorted(cameras.values(), key=lambda item: item.name.casefold()):
            fov = (
                ""
                if profile.horizontal_fov_deg is None
                else f" · FOV {profile.horizontal_fov_deg:g}°"
            )
            self.camera_combo.addItem(f"{profile.name}{fov}", profile.profile_id)
        draft = self._load_draft()
        draft_stale = False
        if draft is not None:
            self._apply_draft(draft)
            draft_stale = plan is not None and draft != _draft_from_plan(plan)
            self.draft_status.setText(
                "Cần tính lại" if draft_stale else "Đã khôi phục bản nháp"
            )
        elif plan is not None:
            self._apply_plan_inputs(plan)
            self.draft_status.setText("Kế hoạch đã lưu")
        else:
            self._apply_mission_defaults(workspace)
            self.draft_status.setText("Bản nháp tự động")
        self._loading = False
        self.set_plan(plan)
        self._plan_stale = draft_stale
        self._save_draft()
        self._update_actions()

    def set_plan(self, plan: PlannedMission | None) -> None:
        self._plan = plan
        self._plan_stale = False
        self.map_view.set_plan(plan)
        self.route_table.blockSignals(True)
        self.route_table.setRowCount(0 if plan is None else len(plan.routes))
        if plan is None:
            self.area_value.setText("—")
            self.coverage_value.setText("—")
            self.capture_value.setText("—")
            self.warning_label.setText("Chưa có cảnh báo")
            self.route_distance_value.setText("—")
            self.route_duration_value.setText("—")
            self.route_lane_value.setText("—")
            self.route_capture_value.setText("—")
            self.waypoint_model.set_route(None)
            self.waypoint_summary.setText("Chưa có đường bay")
        else:
            self.area_value.setText(f"{plan.area_m2:,.1f} m²")
            self.coverage_value.setText(f"{plan.coverage_ratio * 100:.1f}%")
            self.capture_value.setText(f"{plan.capture_count:,}")
            for row, route in enumerate(plan.routes):
                item = QTableWidgetItem(str(row + 1))
                item.setToolTip(route.drone_id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setForeground(QColor(_ROUTE_COLORS[row]))
                self.route_table.setItem(row, 0, item)
                self.route_table.setItem(row, 1, QTableWidgetItem(str(len(route.lane_indices))))
                self.route_table.setItem(row, 2, QTableWidgetItem(str(len(route.waypoints))))
                self.route_table.setItem(
                    row,
                    3,
                    QTableWidgetItem(
                        _short_duration_text(route.estimated_duration_seconds)
                    ),
                )
            warnings = [_warning_text(warning.code, warning.drone_id) for warning in plan.warnings]
            self.warning_label.setText("\n".join(f"• {item}" for item in warnings) or "Không có")
            self.route_table.selectRow(0)
        self.route_table.blockSignals(False)
        self._route_selected()
        self._update_actions()

    def set_busy(self, busy: bool) -> None:
        self.calculate_button.setEnabled(not busy and self._can_calculate())
        self.export_button.setEnabled(
            not busy
            and self._plan is not None
            and not self._plan_stale
            and self._plan.export_ready
        )
        self.settings_panel.setEnabled(not busy)
        self.routes_panel.setEnabled(not busy)
        if busy:
            self.message.setText("Đang xử lý kế hoạch nhiệm vụ…")

    def show_error(self, message: str) -> None:
        self.message.setStyleSheet(f"color: {COLORS['danger']};")
        self.message.setText(message)

    def show_message(self, message: str) -> None:
        self.message.setStyleSheet("")
        self.message.setText(message)

    def draft(self) -> PlanningDraft:
        if self._mission_id is None:
            raise ValueError("Chưa chọn nhiệm vụ")
        camera_id = self.camera_combo.currentData()
        if not isinstance(camera_id, str) or not camera_id:
            raise ValueError("Chưa có hồ sơ máy ảnh hợp lệ")
        speed, pause, heading, separation = self.advanced_dialog.values()
        return PlanningDraft(
            mission_id=self._mission_id,
            camera_profile_id=camera_id,
            polygon_wgs84=self._polygon,
            altitude_agl_m=self.altitude.value(),
            forward_overlap=self.forward_overlap.value() / 100.0,
            side_overlap=self.side_overlap.value() / 100.0,
            flight_speed_mps=speed,
            capture_pause_seconds=pause,
            sweep_heading_deg=heading,
            minimum_route_separation_m=separation,
        )

    @Slot()
    def _calculate(self) -> None:
        try:
            draft = self.draft()
        except ValueError as exc:
            self.show_error(str(exc))
            return
        self.calculateRequested.emit(draft)

    @Slot()
    def _export(self) -> None:
        if self._mission_id is not None:
            self.exportRequested.emit(self._mission_id)

    @Slot(bool)
    def _draw_toggled(self, enabled: bool) -> None:
        if enabled:
            self.edit_button.setChecked(False)
        self.map_view.set_draw_mode(enabled)

    @Slot(bool)
    def map_view_set_edit(self, enabled: bool) -> None:
        if enabled:
            self.draw_button.setChecked(False)
        self.map_view.set_edit_mode(enabled)

    @Slot()
    def map_view_undo(self) -> None:
        self.map_view.undo_point()

    @Slot()
    def map_view_clear(self) -> None:
        self.draw_button.setChecked(False)
        self.edit_button.setChecked(False)
        self.map_view.clear_polygon()
        # A route belongs to its original boundary. Clear the preview and every
        # route/table metric at once so a replacement boundary starts clean.
        self.set_plan(None)
        self._polygon_changed(())
        self.draft_status.setText("Đã xóa ranh giới và đường bay")
        if self._mission_id is not None:
            self.clearPlanRequested.emit(self._mission_id)

    @Slot(object)
    def _polygon_changed(self, value: object) -> None:
        if not isinstance(value, tuple):
            return
        self._polygon = value
        self.vertex_label.setText(f"{len(self._polygon)} đỉnh")
        self._draft_changed()

    @Slot()
    def _import_coordinates(self) -> None:
        self.coordinate_dialog.set_coordinates(self._polygon)
        if self.coordinate_dialog.exec() == QDialog.DialogCode.Accepted:
            self._polygon = self.coordinate_dialog.coordinates
            self.map_view.set_polygon(self._polygon)
            self.vertex_label.setText(f"{len(self._polygon)} đỉnh")
            self._draft_changed()

    @Slot()
    def _edit_advanced(self) -> None:
        before = self.advanced_dialog.values()
        if self.advanced_dialog.exec() == QDialog.DialogCode.Accepted:
            if self.advanced_dialog.values() != before:
                self._draft_changed()

    @Slot()
    def _draft_changed(self, *_args: object) -> None:
        if self._loading:
            return
        if self._plan is not None:
            self._plan_stale = True
            self.draft_status.setText("Cần tính lại")
        else:
            self.draft_status.setText("Đã lưu bản nháp")
        self._save_draft()
        self._update_actions()

    def _update_actions(self) -> None:
        self.calculate_button.setEnabled(self._can_calculate())
        self.export_button.setEnabled(
            self._plan is not None
            and not self._plan_stale
            and self._plan.export_ready
        )

    def _can_calculate(self) -> bool:
        return (
            self._mission_id is not None
            and self.camera_combo.count() > 0
            and len(self._polygon) >= 3
        )

    def _route_selected(self) -> None:
        row = self.route_table.currentRow()
        if self._plan is None or not 0 <= row < len(self._plan.routes):
            self.waypoint_model.set_route(None)
            return
        route = self._plan.routes[row]
        self.waypoint_model.set_route(route)
        self.waypoint_summary.setText(f"· {route.drone_id} · {len(route.waypoints)} điểm")
        self.route_distance_value.setText(f"{route.estimated_distance_m:,.0f} m")
        self.route_duration_value.setText(_duration_text(route.estimated_duration_seconds))
        self.route_lane_value.setText(str(len(route.lane_indices)))
        self.route_capture_value.setText(str(len(route.waypoints)))

    def _route_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self.map_view.set_route_visible(
                item.row(), item.checkState() == Qt.CheckState.Checked
            )

    def _apply_draft(self, draft: PlanningDraft) -> None:
        self._set_combo_data(draft.camera_profile_id)
        self._polygon = draft.polygon_wgs84
        self.map_view.set_polygon(self._polygon)
        self.vertex_label.setText(f"{len(self._polygon)} đỉnh")
        self.altitude.setValue(draft.altitude_agl_m)
        self.forward_overlap.setValue(draft.forward_overlap * 100)
        self.side_overlap.setValue(draft.side_overlap * 100)
        self.advanced_dialog.set_values(
            draft.flight_speed_mps,
            draft.capture_pause_seconds,
            draft.sweep_heading_deg,
            draft.minimum_route_separation_m,
        )
    def _apply_plan_inputs(self, plan: PlannedMission) -> None:
        self._set_combo_data(plan.camera_profile_id)
        self._polygon = tuple(
            (point.latitude, point.longitude) for point in plan.survey_area.polygon_wgs84
        )
        self.map_view.set_polygon(self._polygon)
        self.vertex_label.setText(f"{len(self._polygon)} đỉnh")
        profile = plan.profile
        self.altitude.setValue(profile.altitude_agl_m)
        self.forward_overlap.setValue(profile.forward_overlap * 100)
        self.side_overlap.setValue(profile.side_overlap * 100)
        self.advanced_dialog.set_values(
            profile.flight_speed_mps,
            profile.capture_pause_seconds,
            profile.sweep_heading_deg,
            profile.minimum_route_separation_m,
        )
    def _apply_mission_defaults(self, workspace: MissionDataWorkspace) -> None:
        profile = workspace.mission.flight_profile
        self.altitude.setValue(profile.altitude_m)
        self.forward_overlap.setValue(profile.forward_overlap * 100)
        self.side_overlap.setValue(profile.side_overlap * 100)
    def _set_combo_data(self, value: str) -> None:
        index = self.camera_combo.findData(value)
        if index >= 0:
            self.camera_combo.setCurrentIndex(index)

    def _draft_key(self) -> str | None:
        if self._mission_id is None:
            return None
        digest = hashlib.sha256(self._mission_id.encode("utf-8")).hexdigest()
        return f"planning/drafts/{digest}"

    def _save_draft(self) -> None:
        key = self._draft_key()
        if key is None or self.camera_combo.count() == 0:
            return
        try:
            draft = self.draft()
        except ValueError:
            return
        payload = {
            "version": _DRAFT_VERSION,
            "mission_id": draft.mission_id,
            "camera_profile_id": draft.camera_profile_id,
            "polygon_wgs84": draft.polygon_wgs84,
            "altitude_agl_m": draft.altitude_agl_m,
            "gimbal_pitch_deg": draft.gimbal_pitch_deg,
            "forward_overlap": draft.forward_overlap,
            "side_overlap": draft.side_overlap,
            "flight_speed_mps": draft.flight_speed_mps,
            "capture_pause_seconds": draft.capture_pause_seconds,
            "sweep_heading_deg": draft.sweep_heading_deg,
            "minimum_route_separation_m": draft.minimum_route_separation_m,
        }
        QSettings().setValue(key, json.dumps(payload, ensure_ascii=False))

    def _load_draft(self) -> PlanningDraft | None:
        key = self._draft_key()
        if key is None:
            return None
        value = QSettings().value(key)
        if not isinstance(value, str) or not value:
            return None
        try:
            payload = json.loads(value)
            if payload.get("version") != _DRAFT_VERSION:
                return None
            return PlanningDraft(
                mission_id=str(payload["mission_id"]),
                camera_profile_id=str(payload["camera_profile_id"]),
                polygon_wgs84=tuple(
                    (float(item[0]), float(item[1]))
                    for item in payload["polygon_wgs84"]
                ),
                altitude_agl_m=float(payload["altitude_agl_m"]),
                gimbal_pitch_deg=float(payload.get("gimbal_pitch_deg", -90.0)),
                forward_overlap=float(payload["forward_overlap"]),
                side_overlap=float(payload["side_overlap"]),
                flight_speed_mps=float(payload["flight_speed_mps"]),
                capture_pause_seconds=float(payload["capture_pause_seconds"]),
                sweep_heading_deg=(
                    None
                    if payload.get("sweep_heading_deg") is None
                    else float(payload["sweep_heading_deg"])
                ),
                minimum_route_separation_m=float(
                    payload["minimum_route_separation_m"]
                ),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None


def parse_coordinate_text(value: str) -> tuple[tuple[float, float], ...]:
    text = value.strip()
    if not text:
        raise ValueError("Cần ít nhất ba tọa độ.")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        raw = None
    points: list[tuple[float, float]] = []
    if isinstance(raw, list):
        try:
            points = [(float(item[0]), float(item[1])) for item in raw]
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError("JSON phải là danh sách [vĩ độ, kinh độ].") from exc
    else:
        for number, line in enumerate(text.splitlines(), start=1):
            normalized = line.strip().replace(";", ",")
            if not normalized:
                continue
            parts = [part.strip() for part in normalized.split(",")]
            if len(parts) != 2:
                parts = normalized.split()
            if len(parts) != 2:
                raise ValueError(f"Dòng {number} phải có vĩ độ và kinh độ.")
            try:
                points.append((float(parts[0]), float(parts[1])))
            except ValueError as exc:
                raise ValueError(f"Dòng {number} chứa tọa độ không hợp lệ.") from exc
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        raise ValueError("Cần ít nhất ba tọa độ khác nhau.")
    if len(set(points)) < 3:
        raise ValueError("Cần ít nhất ba tọa độ khác nhau.")
    for latitude, longitude in points:
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Tọa độ nằm ngoài phạm vi WGS84.")
    return tuple(points)


def build_mission_planner_map_html() -> str:
    fallback = "Không tải được bản đồ nền. Vẫn có thể nhập tọa độ bằng nút phía trên."
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="{_LEAFLET_CSS}">
<style>
html,body,#map{{width:100%;height:100%;margin:0;background:#252c29}}
#map{{position:absolute;inset:0}} #loading{{position:absolute;inset:0;display:grid;
place-items:center;color:#d9e0dc;font:13px sans-serif;text-align:center;padding:20px}}
.leaflet-control-attribution{{font-size:7px;line-height:9px;padding:0 2px!important}}
.vertex-marker{{box-sizing:border-box;background:#fff;border:1.5px solid #FF9F1C;border-radius:50%;width:8px;height:8px}}
</style></head><body><div id="loading">Đang tải bản đồ…</div><div id="map"></div>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="{_LEAFLET_JS}" onerror="document.getElementById('loading').textContent={json.dumps(fallback)}"></script>
<script>
let map, bridge, polygonLayer, guideLine, drawMode=false, editMode=false;
let points=[], vertexMarkers=[], routeGroups=[];
function sendPolygon() {{ if (bridge) bridge.updatePolygon(JSON.stringify(points)); }}
function clearGuide() {{if(guideLine&&map){{map.removeLayer(guideLine);guideLine=null;}}}}
function rebuildPolygon() {{
  if (!map) return;
  if (polygonLayer) map.removeLayer(polygonLayer);
  vertexMarkers.forEach(marker => map.removeLayer(marker)); vertexMarkers=[];
  polygonLayer = points.length >= 2 ? L.polygon(points, {{color:'#FF9F1C',weight:2.5,
    fillColor:'#FF9F1C',fillOpacity:0.22}}).addTo(map) : null;
  points.forEach((point,index) => {{
    const marker=L.marker(point,{{draggable:editMode,icon:L.divIcon({{className:'vertex-marker',
      iconSize:[8,8],iconAnchor:[4,4]}})}}).addTo(map);
    marker.on('drag', event => {{ const p=event.target.getLatLng(); points[index]=[p.lat,p.lng];
      if (polygonLayer) polygonLayer.setLatLngs(points); sendPolygon(); }});
    vertexMarkers.push(marker);
  }});
}}
window.plannerSetPolygon=(value,fit=true)=>{{ points=value||[]; rebuildPolygon();
  if(fit&&points.length>0) map.fitBounds(L.latLngBounds(points),{{padding:[30,30]}}); }};
window.plannerSetDrawMode=value=>{{drawMode=value;if(!value)clearGuide();
  if(map)map.getContainer().style.cursor=value?'crosshair':'';}};
window.plannerSetEditMode=value=>{{editMode=value; rebuildPolygon();}};
window.plannerUndoPoint=()=>{{if(points.length){{points.pop();clearGuide();rebuildPolygon();sendPolygon();}}}};
window.plannerClearPolygon=()=>{{points=[];clearGuide();rebuildPolygon();sendPolygon();}};
window.plannerSetRoutes=data=>{{
  routeGroups.forEach(group=>map.removeLayer(group)); routeGroups=[];
  (data.routes||[]).forEach(route=>{{const group=L.layerGroup().addTo(map);
    L.polyline(route.points,{{color:route.color,weight:3,dashArray:route.dash||null}}).addTo(group);
    (route.captures||[]).forEach(point=>L.circleMarker(point,{{radius:2,color:route.color,
      weight:1,fillColor:route.color,fillOpacity:.8}}).addTo(group));
    routeGroups.push(group); }});
}};
window.plannerSetRouteVisible=(index,visible)=>{{const group=routeGroups[index];if(!group)return;
  if(visible)group.addTo(map);else map.removeLayer(group);}};
window.plannerFitContent=()=>{{let bounds=[];if(points.length)bounds=bounds.concat(points);
  routeGroups.forEach(group=>group.eachLayer(layer=>{{if(layer.getLatLngs){{const v=layer.getLatLngs();
    if(Array.isArray(v))bounds=bounds.concat(v);}}else if(layer.getLatLng)bounds.push(layer.getLatLng());}}));
  if(bounds.length)map.fitBounds(L.latLngBounds(bounds),{{padding:[30,30]}});}};
function currentViewState(){{if(!map)return null;const center=map.getCenter();
  const metersPerPixel=156543.03392*Math.cos(center.lat*Math.PI/180)/Math.pow(2,map.getZoom());
  return {{zoom:map.getZoom(),meters_per_pixel:metersPerPixel}};}}
window.plannerGetViewState=()=>{{const state=currentViewState();return state?JSON.stringify(state):null;}};
function reportViewState(){{const state=currentViewState();if(state&&bridge)
  bridge.updateViewState(JSON.stringify(state));}}
if(window.L){{map=L.map('map',{{zoomControl:true,doubleClickZoom:false}}).setView([10.7626,106.6602],18);
L.tileLayer('{_SATELLITE_TILES}',{{maxNativeZoom:20,maxZoom:22,
attribution:'Esri, Vantor, Earthstar Geographics'}}).addTo(map);
map.on('click',event=>{{if(drawMode){{points.push([event.latlng.lat,event.latlng.lng]);
clearGuide();rebuildPolygon();sendPolygon();}}}});
map.on('mousemove',event=>{{if(!drawMode||!points.length)return;clearGuide();
  guideLine=L.polyline([points[points.length-1],event.latlng],{{color:'#FFFFFF',weight:1.5,
    dashArray:'5 5',opacity:.9,interactive:false}}).addTo(map);}});
map.on('zoom zoomend move moveend',reportViewState);
document.getElementById('loading').style.display='none';}}
new QWebChannel(qt.webChannelTransport, channel=>{{bridge=channel.objects.plannerBridge;reportViewState();}});
</script></body></html>"""


def _planner_assets_base_url() -> QUrl:
    root = Path(__file__).resolve().parents[2] / "resources" / "web"
    return QUrl.fromLocalFile(str(root) + "/")


def _map_plan_payload(plan: PlannedMission | None) -> dict[str, Any]:
    if plan is None:
        return {"routes": []}
    routes = []
    for index, route in enumerate(plan.routes):
        display = _sample_waypoints(route.waypoints, 2000)
        points = [
            [waypoint.position.latitude, waypoint.position.longitude]
            for waypoint in display
        ]
        captures = points if len(points) <= 800 else points[:: max(1, len(points) // 800)]
        routes.append(
            {
                "drone_id": route.drone_id,
                "color": _ROUTE_COLORS[index],
                "dash": _ROUTE_DASHES[index],
                "points": points,
                "captures": captures,
            }
        )
    return {"routes": routes}


def _sample_waypoints(
    waypoints: tuple[CaptureWaypoint, ...], maximum: int
) -> tuple[CaptureWaypoint, ...]:
    if len(waypoints) <= maximum:
        return waypoints
    stride = math.ceil((len(waypoints) - 1) / (maximum - 1))
    sampled = waypoints[::stride]
    if sampled[-1] is not waypoints[-1]:
        sampled = (*sampled, waypoints[-1])
    return tuple(sampled)


def _draft_from_plan(plan: PlannedMission) -> PlanningDraft:
    profile = plan.profile
    return PlanningDraft(
        mission_id=plan.mission_id,
        camera_profile_id=plan.camera_profile_id,
        polygon_wgs84=tuple(
            (point.latitude, point.longitude) for point in plan.survey_area.polygon_wgs84
        ),
        altitude_agl_m=profile.altitude_agl_m,
        gimbal_pitch_deg=profile.gimbal_pitch_deg,
        forward_overlap=profile.forward_overlap,
        side_overlap=profile.side_overlap,
        flight_speed_mps=profile.flight_speed_mps,
        capture_pause_seconds=profile.capture_pause_seconds,
        sweep_heading_deg=profile.sweep_heading_deg,
        minimum_route_separation_m=profile.minimum_route_separation_m,
    )


def _number_spin(
    minimum: float,
    maximum: float,
    default: float,
    suffix: str,
    *,
    decimals: int = 1,
) -> QDoubleSpinBox:
    value = QDoubleSpinBox()
    value.setRange(minimum, maximum)
    value.setDecimals(decimals)
    value.setValue(default)
    value.setSuffix(suffix)
    return value


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def _duration_text(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds_part = divmod(remainder, 60)
    if hours:
        return f"{hours} giờ {minutes} phút"
    return f"{minutes} phút {seconds_part} giây" if minutes else f"{seconds_part} giây"


def _short_duration_text(seconds: float) -> str:
    total_minutes = max(1, int(round(seconds / 60)))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}g {minutes}p" if hours else f"{minutes}p"


def _warning_text(code: str, drone_id: str | None) -> str:
    messages = {
        "fixed_agl_without_terrain": (
            "Độ cao AGL cố định; chưa áp dụng bám địa hình."
        ),
        "route_separation_below_minimum": (
            "Các làn liền kề gần hơn khoảng cách cảnh báo đã đặt."
        ),
        "route_workload_imbalance": (
            "Thời gian dự kiến giữa các drone chênh lệch trên 50%."
        ),
    }
    message = messages.get(code, code.replace("_", " "))
    return f"{drone_id}: {message}" if drone_id else message
