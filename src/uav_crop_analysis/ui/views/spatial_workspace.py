"""Spatial products, orthomosaic processing, and georeferenced heatmaps."""

from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QColor, QPen, QPixmap, QResizeEvent, QStandardItemModel
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSplitter,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application import AnalysisModelOption, AnalysisRequest
from uav_crop_analysis.geospatial import (
    SpatialAccuracy,
    SpatialProduct,
    SpatialProductKind,
    SpatialWorkspace,
)
from uav_crop_analysis.jobs import AnalysisJob, JobStatus
from uav_crop_analysis.model_names import display_model_name
from uav_crop_analysis.ui.icons import (
    ICON_ON_PRIMARY,
    configure_icon_button,
    set_button_icon,
)
from uav_crop_analysis.ui.models import JOB_STATUS_TEXT, SpatialProductTableModel
from uav_crop_analysis.ui.spatial_regions import (
    WeedRegion,
    WeedRegionTableModel,
    extract_class_metrics,
    extract_weed_regions,
)
from uav_crop_analysis.ui.views.common import configure_table, divider, stretch_columns
from uav_crop_analysis.ui.views.image_view import PanZoomGraphicsView
from uav_crop_analysis.ui.views.map_overlay import (
    OrthomosaicMapDialog,
    OrthomosaicMapPreview,
)


class SpatialWorkspacePage(QWidget):
    previewRequested = Signal(str)
    importRequested = Signal(str)
    nodeOdmRequested = Signal(str)
    analyzeRequested = Signal(str, object)
    heatmapRequested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageSurface")
        self._mission_id: str | None = None
        self._workspace: SpatialWorkspace | None = None
        self._product_jobs: dict[str, tuple[AnalysisJob, ...]] = {}
        self.product_model = SpatialProductTableModel()
        self._scene = QGraphicsScene(self)
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setZValue(0)
        self._scene.addItem(self._pixmap_item)
        self._overlay_item = QGraphicsPixmapItem()
        self._overlay_item.setZValue(1)
        self._scene.addItem(self._overlay_item)
        self._region_item = QGraphicsRectItem()
        self._region_item.setPen(QPen(QColor("#F4C84A"), 2))
        self._region_item.setZValue(2)
        self._region_item.setVisible(False)
        self._scene.addItem(self._region_item)
        self.region_model = WeedRegionTableModel()
        self.view: PanZoomGraphicsView
        self._map_base_product: SpatialProduct | None = None
        self._map_overlay_product: SpatialProduct | None = None
        self._map_dialog: OrthomosaicMapDialog | None = None
        self._compact_width = False
        self._compact_height = False
        self.results_expanded = True
        self.inspector_expanded = True
        self.region_expanded = True
        self._region_expanded_height = 165
        self._region_animation_target_expanded = True
        self._region_animation = QVariantAnimation(self)
        self._region_animation.setDuration(180)
        self._region_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._region_animation.valueChanged.connect(self._apply_region_height)
        self._region_animation.finished.connect(self._finish_region_animation)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(8)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Bản đồ")
        title.setObjectName("PageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("MutedLabel")
        title_box.addWidget(title)
        title_box.addWidget(self.subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFixedWidth(220)
        self.progress.setVisible(False)
        header.addWidget(self.progress)
        self.progress_label = QLabel()
        self.progress_label.setObjectName("MutedLabel")
        self.progress_label.setVisible(False)
        header.addWidget(self.progress_label)
        self.source_button = QPushButton()
        configure_icon_button(
            self.source_button,
            "folder-input",
            "Tạo, nhập hoặc quản lý nguồn bản đồ",
        )
        self.results_toggle = QToolButton()
        configure_icon_button(self.results_toggle, "list-filter", "Ẩn bảng kết quả cỏ dại")
        self.results_toggle.clicked.connect(self._toggle_results_panel)
        header.addWidget(self.results_toggle)
        self.inspector_toggle = QToolButton()
        configure_icon_button(self.inspector_toggle, "layers", "Ẩn bảng lớp và thông tin")
        self.inspector_toggle.clicked.connect(self._toggle_inspector_panel)
        header.addWidget(self.inspector_toggle)
        header.addWidget(self.source_button)
        root.addLayout(header)

        self.source_dialog = QDialog(self)
        self.source_dialog.setWindowTitle("Nguồn bản đồ")
        self.source_dialog.setMinimumSize(470, 560)
        source_dialog_layout = QVBoxLayout(self.source_dialog)
        source_dialog_layout.addWidget(self._build_source_panel())
        source_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_button = source_buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setText("Đóng")
        source_buttons.rejected.connect(self.source_dialog.reject)
        source_dialog_layout.addWidget(source_buttons)
        self.source_button.clicked.connect(self.source_dialog.open)

        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.center_splitter.setChildrenCollapsible(False)
        self.center_splitter.addWidget(self._build_viewer_panel())
        self.region_panel = self._build_region_panel()
        self.center_splitter.addWidget(self.region_panel)
        self.center_splitter.setStretchFactor(0, 1)
        self.center_splitter.setSizes((500, 165))

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.results_panel = self._build_results_panel()
        self.inspector_panel = self._build_inspector_panel()
        self.field_map_panel = self._build_field_map_panel()
        self.right_column = QWidget()
        self.right_column.setObjectName("SpatialRightColumn")
        self.right_column.setMinimumWidth(260)
        self.right_column.setMaximumWidth(310)
        right_layout = QVBoxLayout(self.right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self.inspector_panel, 1)
        right_layout.addWidget(self.field_map_panel)
        self.workspace_splitter.addWidget(self.results_panel)
        self.workspace_splitter.addWidget(self.center_splitter)
        self.workspace_splitter.addWidget(self.right_column)
        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setStretchFactor(2, 0)
        self.workspace_splitter.setSizes((245, 820, 260))
        root.addWidget(self.workspace_splitter, 1)

        self.message = QLabel()
        self.message.setObjectName("MutedLabel")
        self.message.setWordWrap(True)
        root.addWidget(self.message)

        self.view.pointerMoved.connect(self._pointer_moved)
        self.view.zoomChanged.connect(self._update_view_status)
        self.view.measurementChanged.connect(self._measurement_changed)
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        self.artifact_combo.currentIndexChanged.connect(self._update_actions)
        self.device_combo.currentIndexChanged.connect(self._update_settings_summary)
        self.threshold.valueChanged.connect(self._update_settings_summary)
        self.min_region_area.valueChanged.connect(self._refresh_regions)
        self._selection_changed()

    def _build_results_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("WorkspacePanel")
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(260)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        heading = QLabel("Kết quả phân vùng")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        self.field_area_value = _large_metric_value()
        self.crop_area_value = _large_metric_value()
        self.weed_area_value = _large_metric_value()
        self.weed_ratio_value = _large_metric_value()
        self.region_count_value = _large_metric_value()
        for label, value in (
            ("Diện tích khảo sát", self.field_area_value),
            ("Diện tích ngô", self.crop_area_value),
            ("Diện tích cỏ dại", self.weed_area_value),
            ("Tỷ lệ cỏ dại", self.weed_ratio_value),
            ("Số vùng liên tục", self.region_count_value),
        ):
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            layout.addWidget(name)
            layout.addWidget(value)
        layout.addWidget(divider())
        filter_title = QLabel("Lọc vùng hiển thị")
        filter_title.setObjectName("SectionTitle")
        layout.addWidget(filter_title)
        self.min_region_area = QDoubleSpinBox()
        self.min_region_area.setRange(0.0, 10000.0)
        self.min_region_area.setDecimals(3)
        self.min_region_area.setSingleStep(0.01)
        self.min_region_area.setValue(0.02)
        area_label = QLabel("Diện tích tối thiểu")
        area_label.setObjectName("MetricLabel")
        layout.addWidget(area_label)
        self.min_region_area.setSuffix(" m²")
        self.min_region_area.setToolTip("Ẩn các vùng cỏ nhỏ hơn diện tích này")
        layout.addWidget(self.min_region_area)
        layout.addWidget(divider())

        analysis_title = QLabel("Cập nhật kết quả")
        analysis_title.setObjectName("SectionTitle")
        layout.addWidget(analysis_title)
        self.settings_dialog = _SpatialAnalysisSettingsDialog(panel)
        self.model_combo = self.settings_dialog.model_combo
        self.artifact_combo = self.settings_dialog.artifact_combo
        self.device_combo = self.settings_dialog.device_combo
        self.threshold = self.settings_dialog.threshold
        self.settings_summary = QLabel("Chưa có mô hình")
        self.settings_summary.setObjectName("MutedLabel")
        self.settings_summary.setWordWrap(False)
        self.settings_summary.setMaximumHeight(22)
        settings_row = QHBoxLayout()
        settings_row.setSpacing(6)
        settings_row.addWidget(self.settings_summary, 1)
        self.settings_button = QPushButton()
        configure_icon_button(
            self.settings_button,
            "settings-2",
            "Chọn mô hình, trọng số, thiết bị và ngưỡng",
        )
        self.settings_button.clicked.connect(self.settings_dialog.open_for_edit)
        settings_row.addWidget(self.settings_button)
        layout.addLayout(settings_row)
        self.run_button = QPushButton("Phân vùng ngô - cỏ")
        self.run_button.setObjectName("PrimaryButton")
        set_button_icon(self.run_button, "play", color=ICON_ON_PRIMARY)
        self.run_button.clicked.connect(self._analyze)
        layout.addWidget(self.run_button)
        self.job_combo = QComboBox()
        self.job_combo.setAccessibleName("Tác vụ phân tích ảnh ghép")
        self.job_combo.currentIndexChanged.connect(self._update_actions)
        layout.addWidget(self.job_combo)
        self.export_button = QPushButton("Tạo bản đồ mật độ")
        set_button_icon(self.export_button, "map-pinned")
        self.export_button.setToolTip("Tạo GeoTIFF mật độ cỏ dại từ tác vụ hoàn thành")
        self.export_button.clicked.connect(self._export_heatmap)
        layout.addWidget(self.export_button)
        layout.addStretch()
        return panel

    def _build_source_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        heading = QLabel("Dữ liệu bản đồ")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        readiness = QGridLayout()
        readiness.setHorizontalSpacing(16)
        readiness.setVerticalSpacing(3)
        self.image_value = _compact_metric_value()
        self.gps_value = _compact_metric_value()
        self.altitude_value = _compact_metric_value()
        self.engine_value = _compact_metric_value()
        for index, (label, value) in enumerate(
            (
                ("Ảnh đầu vào", self.image_value),
                ("Ảnh có GPS", self.gps_value),
                ("Ảnh có độ cao", self.altitude_value),
                ("Bộ xử lý", self.engine_value),
            )
        ):
            row, column = divmod(index, 2)
            box = QVBoxLayout()
            box.setSpacing(1)
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            box.addWidget(name)
            box.addWidget(value)
            readiness.addLayout(box, row, column)
        layout.addLayout(readiness)
        layout.addWidget(divider())

        action_title = QLabel("Tạo ảnh ghép")
        action_title.setObjectName("SectionTitle")
        layout.addWidget(action_title)
        self.nodeodm_button = QPushButton("Dựng ảnh ghép")
        self.nodeodm_button.setObjectName("PrimaryButton")
        set_button_icon(self.nodeodm_button, "layers", color=ICON_ON_PRIMARY)
        self.nodeodm_button.clicked.connect(self._nodeodm)
        layout.addWidget(self.nodeodm_button)
        self.import_button = QPushButton("Nhập ảnh GeoTIFF")
        set_button_icon(self.import_button, "file-up")
        self.import_button.setToolTip("Nhập ảnh ghép đã có thông tin tọa độ")
        self.import_button.clicked.connect(self._import)
        layout.addWidget(self.import_button)
        self.preview_button = QPushButton("Tạo ảnh xem nhanh")
        self.preview_button.setToolTip(
            "Xếp ảnh theo ba làn bay để xem nhanh; không dùng cho định vị"
        )
        set_button_icon(self.preview_button, "layout-grid")
        self.preview_button.clicked.connect(self._preview)
        layout.addWidget(self.preview_button)
        layout.addWidget(divider())

        product_title = QLabel("Lớp hiển thị")
        product_title.setObjectName("SectionTitle")
        layout.addWidget(product_title)
        self.product_table = QTableView()
        self.product_table.setModel(self.product_model)
        self.product_table.setAccessibleName("Danh sách lớp bản đồ")
        self.product_table.setMinimumHeight(150)
        configure_table(self.product_table, row_height=42)
        stretch_columns(self.product_table, 0)
        for column in range(1, self.product_model.columnCount()):
            self.product_table.setColumnHidden(column, True)
        self.product_table.selectionModel().selectionChanged.connect(self._selection_changed)
        layout.addWidget(self.product_table, 1)
        self.empty_products = QLabel("Chưa có ảnh ghép hoặc bản đồ mật độ.")
        self.empty_products.setObjectName("MutedLabel")
        self.empty_products.setWordWrap(True)
        layout.addWidget(self.empty_products)
        return panel

    def _build_region_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("WorkspacePanel")
        panel.setMinimumHeight(150)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(6)
        heading = QHBoxLayout()
        title = QLabel("Vùng cỏ dại phát hiện")
        title.setObjectName("SectionTitle")
        heading.addWidget(title)
        self.region_summary = QLabel("Chưa có kết quả semantic trên ảnh ghép")
        self.region_summary.setObjectName("MutedLabel")
        heading.addWidget(self.region_summary)
        heading.addStretch()
        self.region_toggle = QToolButton()
        configure_icon_button(self.region_toggle, "eye-off", "Thu gọn danh sách vùng")
        self.region_toggle.setFixedSize(28, 28)
        self.region_toggle.clicked.connect(self._toggle_region_panel)
        heading.addWidget(self.region_toggle)
        layout.addLayout(heading)
        self.region_table = QTableView()
        self.region_table.setModel(self.region_model)
        self.region_table.setAccessibleName("Danh sách vùng cỏ dại semantic")
        configure_table(self.region_table, row_height=36)
        stretch_columns(self.region_table, 3)
        self.region_table.selectionModel().selectionChanged.connect(self._region_selection_changed)
        layout.addWidget(self.region_table)
        return panel

    def _build_viewer_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("ViewerPanel")
        self.view = PanZoomGraphicsView(self._scene)
        self.view.setObjectName("ImageViewer")
        self.view.setBackgroundBrush(QBrush(QColor("#202724")))
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("ViewerToolbar")
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(8, 6, 8, 6)
        toolbar.setSpacing(6)
        self.current_layer_label = QLabel("Bản đồ")
        self.current_layer_label.setObjectName("ViewerTitle")
        self.current_layer_label.setVisible(False)
        toolbar.addWidget(self.current_layer_label)
        toolbar.addStretch()
        north = QToolButton()
        configure_icon_button(north, "compass", "Hướng Bắc ở phía trên")
        north.setToolTip("Ảnh bản đồ được hiển thị theo hướng Bắc ở phía trên")
        toolbar.addWidget(north)
        toolbar.addWidget(divider(vertical=True))
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        for name, icon, tip in (
            ("pan", "mouse-pointer-2", "Kéo bản đồ"),
            ("point", "crosshair", "Đo tọa độ điểm"),
            ("distance", "ruler", "Đo khoảng cách"),
            ("area", "square-dashed", "Đo diện tích; nhấp đúp tại đỉnh cuối để kết thúc"),
        ):
            button = QToolButton()
            configure_icon_button(button, icon, tip)
            button.setCheckable(True)
            button.setProperty("viewerTool", name)
            button.clicked.connect(lambda checked=False, value=name: self._set_viewer_tool(value))
            self.tool_group.addButton(button)
            toolbar.addWidget(button)
            if name == "pan":
                button.setChecked(True)
                toolbar.addWidget(divider(vertical=True))
            elif name == "area":
                toolbar.addWidget(divider(vertical=True))
        self.zoom_out_button = QPushButton()
        configure_icon_button(self.zoom_out_button, "zoom-out", "Thu nhỏ")
        self.zoom_out_button.clicked.connect(lambda: self.view.zoom_by(1 / 1.25))
        toolbar.addWidget(self.zoom_out_button)
        self.zoom_in_button = QPushButton()
        configure_icon_button(self.zoom_in_button, "zoom-in", "Phóng to")
        self.zoom_in_button.clicked.connect(lambda: self.view.zoom_by(1.25))
        toolbar.addWidget(self.zoom_in_button)
        self.fit_button = QPushButton()
        configure_icon_button(
            self.fit_button,
            "maximize-2",
            "Hiển thị toàn bộ ảnh trong vùng xem",
        )
        self.fit_button.clicked.connect(self.fit_image)
        toolbar.addWidget(self.fit_button)
        layout.addWidget(toolbar_frame)

        layout.addWidget(self.view, 1)
        status = QHBoxLayout()
        self.coordinate_value = QLabel("X — · Y —")
        self.coordinate_value.setObjectName("MapStatusLabel")
        status.addWidget(self.coordinate_value, 1)
        self.scale_value = QLabel("100 px ≈ —")
        self.scale_value.setObjectName("MapStatusLabel")
        status.addWidget(self.scale_value)
        layout.addLayout(status)
        return panel

    def _build_inspector_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("InspectorPanel")
        panel.setMinimumWidth(260)
        panel.setMaximumWidth(310)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Lớp và thông tin")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 8, 0, 0)
        content_layout.setSpacing(10)

        layer_layout = content_layout
        self.product_combo = QComboBox()
        self.product_combo.setAccessibleName("Chọn lớp bản đồ")
        self.product_combo.currentIndexChanged.connect(self._product_combo_changed)
        layer_layout.addWidget(self.product_combo)
        self.map_layer_check = QCheckBox("Ảnh ghép nền")
        self.map_layer_check.setChecked(True)
        self.map_layer_check.toggled.connect(self._layer_visibility_changed)
        layer_layout.addWidget(self.map_layer_check)
        self.heatmap_layer_check = QCheckBox("Bản đồ mật độ cỏ dại")
        self.heatmap_layer_check.setChecked(False)
        self.heatmap_layer_check.toggled.connect(self._layer_visibility_changed)
        layer_layout.addWidget(self.heatmap_layer_check)
        self.region_layer_check = QCheckBox("Khung vùng cỏ dại")
        self.region_layer_check.setChecked(True)
        self.region_layer_check.toggled.connect(self._layer_visibility_changed)
        layer_layout.addWidget(self.region_layer_check)
        opacity_row = QHBoxLayout()
        self.opacity_label = QLabel("Độ trong suốt")
        self.opacity_label.setObjectName("MetricLabel")
        self.opacity_value = QLabel("0%")
        self.opacity_value.setObjectName("MutedLabel")
        opacity_row.addWidget(self.opacity_label)
        opacity_row.addStretch()
        opacity_row.addWidget(self.opacity_value)
        layer_layout.addLayout(opacity_row)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 90)
        self.opacity_slider.setValue(0)
        self.opacity_slider.setAccessibleName("Độ trong suốt của lớp bản đồ")
        self.opacity_slider.valueChanged.connect(self._set_opacity)
        layer_layout.addWidget(self.opacity_slider)
        content_layout.addWidget(divider())

        info_layout = content_layout
        self.accuracy_value = _value_label()
        self.crs_value = _value_label()
        self.bounds_value = _value_label()
        self.resolution_value = _value_label()
        self.source_value = _value_label()
        details = QGridLayout()
        details.setHorizontalSpacing(8)
        details.setVerticalSpacing(6)
        for row, (label, value) in enumerate(
            (
                ("Định vị", self.accuracy_value),
                ("Hệ tọa độ", self.crs_value),
                ("Phạm vi", self.bounds_value),
                ("Độ phân giải", self.resolution_value),
                ("Tệp nguồn", self.source_value),
            )
        ):
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            details.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
            details.addWidget(value, row, 1)
        details.setColumnStretch(1, 1)
        info_layout.addLayout(details)
        self.provenance_value = QLabel("—")
        self.provenance_value.setObjectName("MutedLabel")
        self.provenance_value.setWordWrap(True)
        self.provenance_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.provenance_value.setVisible(False)
        info_layout.addWidget(divider())
        region_title = QLabel("Thông tin vùng đang chọn")
        region_title.setObjectName("SectionTitle")
        info_layout.addWidget(region_title)
        self.region_id_value = _value_label()
        self.region_area_value = _value_label()
        self.region_centroid_value = _value_label()
        self.region_bounds_value = _value_label()
        region_details = QGridLayout()
        region_details.setHorizontalSpacing(8)
        region_details.setVerticalSpacing(6)
        for row, (label, value) in enumerate(
            (
                ("Vùng", self.region_id_value),
                ("Diện tích", self.region_area_value),
                ("Tâm vùng", self.region_centroid_value),
                ("Khung ảnh", self.region_bounds_value),
            )
        ):
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            region_details.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
            region_details.addWidget(value, row, 1)
        region_details.setColumnStretch(1, 1)
        info_layout.addLayout(region_details)
        content_layout.addWidget(divider())
        legend_layout = content_layout
        weed_legend = QHBoxLayout()
        weed_swatch = QFrame()
        weed_swatch.setObjectName("WeedSwatch")
        weed_swatch.setFixedSize(16, 16)
        weed_legend.addWidget(weed_swatch)
        weed_legend.addWidget(QLabel("Cỏ dại / mật độ cao"))
        weed_legend.addStretch()
        legend_layout.addLayout(weed_legend)
        legend_note = QLabel("Bảng màu được lấy từ lớp kết quả hiện có.")
        legend_note.setObjectName("MutedLabel")
        legend_note.setWordWrap(True)
        legend_layout.addWidget(legend_note)
        legend_layout.addStretch()
        scroll = QScrollArea()
        scroll.setObjectName("InspectorScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        return panel

    def _build_field_map_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("FieldMapPanel")
        panel.setMinimumHeight(215)
        panel.setMaximumHeight(235)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(7)
        map_title = QLabel("Bản đồ thực địa")
        map_title.setObjectName("SectionTitle")
        layout.addWidget(map_title)
        self.map_preview = OrthomosaicMapPreview(panel)
        self.map_preview.openRequested.connect(self._open_map_dialog)
        layout.addWidget(self.map_preview, 1)
        return panel

    def set_workspace(
        self,
        workspace: SpatialWorkspace,
        models: tuple[AnalysisModelOption, ...],
        product_jobs: tuple[tuple[str, tuple[AnalysisJob, ...]], ...],
    ) -> None:
        selected = self.selected_product()
        selected_id = selected.product_id if selected else None
        self._mission_id = workspace.mission_id
        self._workspace = workspace
        self._product_jobs = dict(product_jobs)
        self.subtitle.setText(workspace.mission_id)
        self.image_value.setText(f"{workspace.image_count:,}")
        self.gps_value.setText(f"{workspace.geotagged_image_count:,}/{workspace.image_count:,}")
        self.altitude_value.setText(f"{workspace.altitude_image_count:,}/{workspace.image_count:,}")
        self.engine_value.setText(
            workspace.orthomosaic_engine_name
            if workspace.orthomosaic_engine_configured
            else "Chưa sẵn sàng"
        )
        self.engine_value.setToolTip(workspace.orthomosaic_engine_location or "")
        self.product_model.set_rows(workspace.products)
        self.empty_products.setVisible(not workspace.products)
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        for product in workspace.products:
            if product.kind is SpatialProductKind.ORTHOMOSAIC:
                label = "Ảnh ghép"
            elif product.kind is SpatialProductKind.WEED_HEATMAP:
                label = "Bản đồ mật độ"
            else:
                label = "Ảnh xem nhanh"
            self.product_combo.addItem(label, product.product_id)
        self.product_combo.blockSignals(False)
        self._set_models(models)
        if workspace.products:
            row = next(
                (
                    index
                    for index, product in enumerate(workspace.products)
                    if product.product_id == selected_id
                ),
                0,
            )
            self.product_table.selectRow(row)
        self._update_actions()

    def selected_product(self) -> SpatialProduct | None:
        rows = self.product_table.selectionModel().selectedRows()
        return self.product_model.product_at(rows[0].row()) if rows else None

    def select_product(self, product_id: str) -> bool:
        workspace = self._workspace
        if workspace is None:
            return False
        row = next(
            (
                index
                for index, product in enumerate(workspace.products)
                if product.product_id == product_id
            ),
            None,
        )
        if row is None:
            return False
        self.product_table.selectRow(row)
        self.fit_image()
        return True

    def has_active_jobs(self) -> bool:
        return any(
            job.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}
            for jobs in self._product_jobs.values()
            for job in jobs
        )

    def set_busy(self, busy: bool) -> None:
        for button in (self.preview_button, self.import_button, self.nodeodm_button):
            button.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.progress_label.setVisible(busy)
        if busy:
            self.progress.setValue(0)
            self.progress_label.setText("Đang xử lý")
        else:
            self._update_actions()

    def set_progress(self, value: float, status: str) -> None:
        self.progress.setValue(round(max(0.0, min(1.0, value)) * 100))
        self.progress_label.setText(status)

    def show_error(self, message: str) -> None:
        self.message.setObjectName("StatusFailed")
        self.message.setText(message)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)

    def show_message(self, message: str) -> None:
        self.message.setObjectName("MutedLabel")
        self.message.setText(message)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Keep both information columns visible on standard 1180px laptop
        # windows; hide one only when the map would become genuinely unusable.
        compact_width = event.size().width() < 980
        if compact_width != self._compact_width:
            self._compact_width = compact_width
            if compact_width:
                self._set_inspector_expanded(False)
                self._set_results_expanded(True)
            else:
                self._set_results_expanded(True)
                self._set_inspector_expanded(True)
        compact_height = event.size().height() < 760
        if compact_height != self._compact_height:
            self._compact_height = compact_height
            self._set_region_expanded(not compact_height)

    def _toggle_results_panel(self) -> None:
        opening = not self.results_expanded
        if opening and self._compact_width:
            self._set_inspector_expanded(False)
        self._set_results_expanded(opening)

    def _toggle_inspector_panel(self) -> None:
        opening = not self.inspector_expanded
        if opening and self._compact_width:
            self._set_results_expanded(False)
        self._set_inspector_expanded(opening)

    def _set_results_expanded(self, expanded: bool) -> None:
        self.results_expanded = expanded
        self.results_panel.setVisible(expanded)
        self.results_toggle.setToolTip(
            "Ẩn bảng kết quả cỏ dại" if expanded else "Mở bảng kết quả cỏ dại"
        )

    def _set_inspector_expanded(self, expanded: bool) -> None:
        self.inspector_expanded = expanded
        self.right_column.setVisible(expanded)
        self.inspector_toggle.setToolTip(
            "Ẩn cột thông tin bản đồ" if expanded else "Mở cột thông tin bản đồ"
        )

    def _toggle_region_panel(self) -> None:
        self._set_region_expanded(not self.region_expanded, animated=True)

    def _set_region_expanded(self, expanded: bool, *, animated: bool = False) -> None:
        self._region_animation.stop()
        sizes = self.center_splitter.sizes()
        current_height = sizes[1] if len(sizes) > 1 else self.region_panel.height()
        if not expanded and current_height > 42:
            self._region_expanded_height = max(120, min(220, current_height))

        self.region_expanded = expanded
        self._region_animation_target_expanded = expanded
        target_height = self._region_expanded_height if expanded else 42
        self.region_table.setVisible(expanded or animated)
        self.region_panel.setMinimumHeight(42)
        self.region_panel.setMaximumHeight(220)
        set_button_icon(self.region_toggle, "eye-off" if expanded else "eye")
        self.region_toggle.setToolTip(
            "Thu gọn danh sách vùng" if expanded else "Mở danh sách vùng"
        )
        if animated and current_height != target_height:
            self._region_animation.setStartValue(current_height)
            self._region_animation.setEndValue(target_height)
            self._region_animation.start()
            return

        self._apply_region_height(target_height)
        self._finish_region_animation()

    def _apply_region_height(self, value: object) -> None:
        sizes = self.center_splitter.sizes()
        if len(sizes) < 2:
            return
        available_height = sum(sizes)
        if available_height <= 42:
            return
        region_height = max(42, min(int(cast(Any, value)), available_height - 1))
        self.center_splitter.setSizes((available_height - region_height, region_height))

    def _finish_region_animation(self) -> None:
        expanded = self._region_animation_target_expanded
        self.region_table.setVisible(expanded)
        self.region_panel.setMinimumHeight(120 if expanded else 42)
        self.region_panel.setMaximumHeight(220 if expanded else 42)

    def fit_image(self) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.view.resetTransform()
            self.view.fitInView(
                self._pixmap_item.boundingRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            self.view.notify_zoom()
            self.view.remember_view()

    def _set_viewer_tool(self, tool: str) -> None:
        self.view.set_tool(tool)
        instructions = {
            "pan": "Kéo để di chuyển bản đồ",
            "point": "Nhấp một điểm trên bản đồ để xem tọa độ",
            "distance": "Nhấp hai điểm trên bản đồ để đo khoảng cách",
            "area": "Nhấp hai đỉnh đầu; nhấp đúp tại đỉnh cuối để tính diện tích",
        }
        self.coordinate_value.setText(instructions[tool])

    def _set_models(self, models: tuple[AnalysisModelOption, ...]) -> None:
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for model in models:
            self.model_combo.addItem(display_model_name(model.model_id), model)
        self.model_combo.blockSignals(False)
        self._model_changed()

    def _model_changed(self, *_args: object) -> None:
        model = self.model_combo.currentData()
        self.artifact_combo.clear()
        if not isinstance(model, AnalysisModelOption):
            self._update_settings_summary()
            self._update_actions()
            return
        first_available = -1
        for artifact in model.artifacts:
            self.artifact_combo.addItem(artifact.role, artifact)
            if artifact.available and first_available < 0:
                first_available = self.artifact_combo.count() - 1
            item_model = self.artifact_combo.model()
            if isinstance(item_model, QStandardItemModel):
                item = item_model.item(self.artifact_combo.count() - 1)
                if item is not None:
                    item.setEnabled(artifact.available)
        if first_available >= 0:
            self.artifact_combo.setCurrentIndex(first_available)
        self._update_settings_summary()
        self._update_actions()

    def _selection_changed(self, *_args: object) -> None:
        self.view.clear_measurements()
        product = self.selected_product()
        if product is None:
            self._pixmap_item.setPixmap(QPixmap())
            self._overlay_item.setPixmap(QPixmap())
            self._region_item.setVisible(False)
            self.current_layer_label.setText("Bản đồ")
            self.current_layer_label.setToolTip("")
            self._clear_inspector()
            self.job_combo.clear()
            self.region_model.set_rows(())
            self._set_map_products(None, None)
            self._update_agriculture_metrics(None, 0, None, 0, None, ())
            self._update_actions()
            return
        base_product = product
        overlay_product: SpatialProduct | None = None
        workspace = self._workspace
        if workspace is not None and product.kind is SpatialProductKind.ORTHOMOSAIC:
            overlay_product = next(
                (
                    item
                    for item in workspace.products
                    if item.kind is SpatialProductKind.WEED_HEATMAP
                    and item.source_product_id == product.product_id
                ),
                None,
            )
        elif workspace is not None and product.kind is SpatialProductKind.WEED_HEATMAP:
            overlay_product = product
            base_product = next(
                (
                    item
                    for item in workspace.products
                    if item.product_id == product.source_product_id
                ),
                product,
            )
        pixmap = QPixmap(str(base_product.preview_path))
        self._pixmap_item.setPixmap(pixmap)
        self._pixmap_item.setOpacity(1.0)
        self._overlay_item.setPixmap(
            QPixmap(str(overlay_product.preview_path)) if overlay_product is not None else QPixmap()
        )
        self._overlay_item.setOpacity(1 - self.opacity_slider.value() / 100)
        self._set_map_products(
            base_product if base_product.raster is not None else None,
            overlay_product,
        )
        self.heatmap_layer_check.setEnabled(overlay_product is not None)
        if overlay_product is None:
            self.heatmap_layer_check.setChecked(False)
        elif product.kind is SpatialProductKind.WEED_HEATMAP:
            self.heatmap_layer_check.setChecked(True)
        self._layer_visibility_changed()
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.product_combo.blockSignals(True)
        combo_index = self.product_combo.findData(product.product_id)
        if combo_index >= 0:
            self.product_combo.setCurrentIndex(combo_index)
        self.product_combo.blockSignals(False)
        layer_name = str(
            self.product_model.data(
                self.product_model.index(self.product_table.currentIndex().row(), 0)
            )
        )
        self.current_layer_label.setText("Bản đồ")
        self.current_layer_label.setToolTip(layer_name)
        self.fit_image()
        self._show_product(product)
        self.job_combo.clear()
        for job in self._product_jobs.get(product.product_id, ()):
            self.job_combo.addItem(
                f"{JOB_STATUS_TEXT[job.status]} · "
                f"{display_model_name(job.config.model_id)}",
                job,
            )
        if not self.job_combo.count():
            self.job_combo.addItem("Chưa có tác vụ phân tích", None)
        self._refresh_regions()
        self._update_actions()

    def _show_product(self, product: SpatialProduct) -> None:
        raster = product.raster
        georeferenced = product.accuracy is SpatialAccuracy.GEOREFERENCED
        self.accuracy_value.setText(
            "Đã định vị địa lý" if georeferenced else "Ảnh xem nhanh, không có tọa độ"
        )
        self.accuracy_value.setObjectName("StatusReady" if georeferenced else "StatusIncomplete")
        self.accuracy_value.style().unpolish(self.accuracy_value)
        self.accuracy_value.style().polish(self.accuracy_value)
        self.crs_value.setText(raster.crs if raster else "—")
        self.bounds_value.setText(
            "\n".join(f"{value:.3f}" for value in raster.bounds) if raster else "—"
        )
        self.resolution_value.setText(
            f"{raster.resolution[0]:.5g} × {raster.resolution[1]:.5g} m/px" if raster else "—"
        )
        self.source_value.setText(product.path.name)
        self.source_value.setToolTip(str(product.path))
        provenance = dict(product.provenance)
        provenance_names = {
            "engine": "Bộ xử lý",
            "task_id": "Mã tác vụ",
            "model_id": "Mô hình",
            "weed_threshold": "Ngưỡng cỏ dại",
            "layout": "Cách sắp xếp",
        }
        self.provenance_value.setText(
            "\n".join(
                f"{provenance_names.get(key, key)}: "
                f"{display_model_name(str(value)) if key == 'model_id' else value}"
                for key, value in provenance.items()
            )
            if provenance
            else "Không có thông tin bổ sung."
        )
        self._update_view_status()

    def _clear_inspector(self) -> None:
        for label in (
            self.accuracy_value,
            self.crs_value,
            self.bounds_value,
            self.resolution_value,
            self.source_value,
            self.provenance_value,
            self.region_id_value,
            self.region_area_value,
            self.region_centroid_value,
            self.region_bounds_value,
        ):
            label.setText("—")
        self.coordinate_value.setText("X — · Y —")
        self.scale_value.setText("100 px ≈ —")

    def _set_map_products(
        self,
        orthomosaic: SpatialProduct | None,
        heatmap: SpatialProduct | None,
    ) -> None:
        self._map_base_product = orthomosaic
        self._map_overlay_product = heatmap
        self.map_preview.set_products(orthomosaic, heatmap)
        if self._map_dialog is not None and self._map_dialog.isVisible() and orthomosaic:
            self._map_dialog.set_products(orthomosaic, heatmap)

    def _open_map_dialog(self) -> None:
        orthomosaic = self._map_base_product
        if orthomosaic is None:
            return
        if self._map_dialog is None:
            self._map_dialog = OrthomosaicMapDialog(self)
            self._map_dialog.providerChanged.connect(self.map_preview.reload)
        self._map_dialog.set_products(orthomosaic, self._map_overlay_product)
        self._map_dialog.open()
        self._map_dialog.raise_()
        self._map_dialog.activateWindow()

    def _set_opacity(self, value: int) -> None:
        self.opacity_value.setText(f"{value}%")
        self._overlay_item.setOpacity(1 - value / 100)

    def _product_combo_changed(self, index: int) -> None:
        product_id = self.product_combo.itemData(index)
        if isinstance(product_id, str):
            self.select_product(product_id)

    def _layer_visibility_changed(self, *_args: object) -> None:
        self._pixmap_item.setVisible(self.map_layer_check.isChecked())
        self._overlay_item.setVisible(self.heatmap_layer_check.isChecked())
        self._region_item.setVisible(
            self.region_layer_check.isChecked()
            and bool(self.region_table.selectionModel().selectedRows())
        )

    def _refresh_regions(self, *_args: object) -> None:
        product = self.selected_product()
        if product is None or product.kind is not SpatialProductKind.ORTHOMOSAIC:
            self.region_model.set_rows(())
            self.region_summary.setText("Chọn ảnh ghép đã phân tích semantic")
            self._update_agriculture_metrics(product, 0, None, 0, None, ())
            return
        regions, weed_pixels, weed_coverage = extract_weed_regions(
            product,
            self._product_jobs.get(product.product_id, ()),
            min_area_m2=self.min_region_area.value(),
        )
        crop_pixels, crop_coverage = extract_class_metrics(
            product,
            self._product_jobs.get(product.product_id, ()),
            "crop",
        )
        self.region_model.set_rows(regions)
        self.region_summary.setText(
            f"{len(regions):,} vùng sau bộ lọc"
            if regions
            else "Chưa có mặt nạ semantic để phân vùng"
        )
        self._update_agriculture_metrics(
            product,
            weed_pixels,
            weed_coverage,
            crop_pixels,
            crop_coverage,
            regions,
        )
        self._region_item.setVisible(False)

    def _update_agriculture_metrics(
        self,
        product: SpatialProduct | None,
        weed_pixels: int,
        weed_coverage: float | None,
        crop_pixels: int,
        crop_coverage: float | None,
        regions: tuple[WeedRegion, ...],
    ) -> None:
        raster = product.raster if product is not None else None
        if raster is None:
            self.field_area_value.setText("—")
            self.crop_area_value.setText("—")
            self.weed_area_value.setText("—")
        else:
            pixel_area = abs(raster.resolution[0] * raster.resolution[1])
            self.field_area_value.setText(
                f"{_format_vi_number(raster.width * raster.height * pixel_area)} m²"
            )
            self.crop_area_value.setText(
                f"{_format_vi_number(crop_pixels * pixel_area)} m²"
            )
            self.weed_area_value.setText(f"{_format_vi_number(weed_pixels * pixel_area)} m²")
        self.crop_area_value.setToolTip(
            f"Tỷ lệ ngô semantic: {_format_vi_number(crop_coverage)}%"
            if crop_coverage is not None
            else "Chưa có kết quả semantic ngô"
        )
        self.weed_ratio_value.setText(
            f"{_format_vi_number(weed_coverage)}%" if weed_coverage is not None else "—"
        )
        self.region_count_value.setText(f"{len(regions):,}".replace(",", "."))

    def _selected_region(self) -> WeedRegion | None:
        rows = self.region_table.selectionModel().selectedRows()
        return self.region_model.region_at(rows[0].row()) if rows else None

    def _region_selection_changed(self, *_args: object) -> None:
        region = self._selected_region()
        if region is None:
            self._region_item.setVisible(False)
            return
        self.region_id_value.setText(f"Cỏ dại {region.region_id}")
        self.region_area_value.setText(
            f"{region.area_m2:.3f} m²"
            if region.area_m2 is not None
            else f"{region.pixel_count:,} px"
        )
        self.region_centroid_value.setText(
            f"X {region.centroid_map[0]:.3f}\nY {region.centroid_map[1]:.3f}"
            if region.centroid_map is not None
            else f"x {region.centroid_pixel[0]:.0f}, y {region.centroid_pixel[1]:.0f}"
        )
        x1, y1, x2, y2 = region.bounds_pixel
        self.region_bounds_value.setText(f"x {x1:.0f}–{x2:.0f}\ny {y1:.0f}–{y2:.0f}")
        product = self.selected_product()
        raster = product.raster if product is not None else None
        pixmap = self._pixmap_item.pixmap()
        scale_x = pixmap.width() / raster.width if raster and raster.width else 1.0
        scale_y = pixmap.height() / raster.height if raster and raster.height else 1.0
        self._region_item.setRect(
            x1 * scale_x,
            y1 * scale_y,
            (x2 - x1) * scale_x,
            (y2 - y1) * scale_y,
        )
        self._region_item.setVisible(self.region_layer_check.isChecked())
        self.view.centerOn(
            region.centroid_pixel[0] * scale_x,
            region.centroid_pixel[1] * scale_y,
        )

    def _pointer_moved(self, pixel_x: float, pixel_y: float) -> None:
        product = self.selected_product()
        if product is None or product.raster is None:
            self.coordinate_value.setText(f"x {pixel_x:.0f} · y {pixel_y:.0f}")
            return
        pixmap = self._pixmap_item.pixmap()
        pixel_x *= product.raster.width / max(pixmap.width(), 1)
        pixel_y *= product.raster.height / max(pixmap.height(), 1)
        a, b, c, d, e, f = product.raster.transform
        map_x = a * pixel_x + b * pixel_y + c
        map_y = d * pixel_x + e * pixel_y + f
        self.coordinate_value.setText(f"X {map_x:.3f} · Y {map_y:.3f}")

    def _update_view_status(self, *_args: object) -> None:
        product = self.selected_product()
        raster = product.raster if product is not None else None
        zoom = self.view.transform().m11() * 100
        if raster is None:
            self.scale_value.setText(f"Thu phóng {zoom:.0f}%")
            return
        metres_per_screen_pixel = raster.resolution[0] / max(self.view.transform().m11(), 0.0001)
        self.scale_value.setText(f"100 px ≈ {metres_per_screen_pixel * 100:.2f} m")

    def _measurement_changed(self, kind: str, value: object) -> None:
        product = self.selected_product()
        raster = product.raster if product is not None else None
        pixmap = self._pixmap_item.pixmap()
        if kind == "point" and isinstance(value, tuple):
            self._pointer_moved(float(value[0]), float(value[1]))
        elif kind == "distance" and isinstance(value, float):
            if raster is None:
                self.coordinate_value.setText(f"Khoảng cách {value:.1f} px")
            else:
                scale = raster.width / max(pixmap.width(), 1)
                self.coordinate_value.setText(
                    f"Khoảng cách {value * scale * raster.resolution[0]:.2f} m"
                )
        elif kind == "area" and isinstance(value, float):
            if raster is None:
                self.coordinate_value.setText(f"Diện tích {value:.1f} px²")
            else:
                scale_x = raster.width / max(pixmap.width(), 1)
                scale_y = raster.height / max(pixmap.height(), 1)
                area = value * scale_x * scale_y * abs(raster.resolution[0] * raster.resolution[1])
                self.coordinate_value.setText(f"Diện tích {area:.2f} m²")

    def _update_settings_summary(self, *_args: object) -> None:
        model = self.model_combo.currentData()
        if not isinstance(model, AnalysisModelOption):
            self.settings_summary.setText("Chưa có mô hình cỏ dại khả dụng")
            return
        self.settings_summary.setText(
            f"{display_model_name(model.model_id)} · {self.device_combo.currentText()} · "
            f"ngưỡng {self.threshold.value():.2f}"
        )
        self.settings_summary.setToolTip(self.settings_summary.text())

    def _update_actions(self, *_args: object) -> None:
        product = self.selected_product()
        orthomosaic = product is not None and product.kind is SpatialProductKind.ORTHOMOSAIC
        model = self.model_combo.currentData()
        artifact = self.artifact_combo.currentData()
        self.run_button.setEnabled(
            orthomosaic
            and isinstance(model, AnalysisModelOption)
            and model.available
            and artifact is not None
            and getattr(artifact, "available", False)
        )
        job = self.job_combo.currentData()
        self.export_button.setEnabled(
            orthomosaic and isinstance(job, AnalysisJob) and job.status is JobStatus.COMPLETED
        )
        workspace = self._workspace
        self.nodeodm_button.setEnabled(
            workspace is not None
            and workspace.orthomosaic_engine_configured
            and workspace.geospatial_ready
        )
        if workspace is None or not workspace.orthomosaic_engine_configured:
            self.nodeodm_button.setToolTip("Bộ dựng ảnh ghép NodeODM chưa sẵn sàng trong bản cài")
        elif not workspace.geospatial_ready:
            self.nodeodm_button.setToolTip("Tất cả ảnh nhiệm vụ cần có GPS")
        else:
            self.nodeodm_button.setToolTip(
                "Ứng dụng tự kiểm tra Docker, khởi động NodeODM và dựng ảnh ghép"
            )

    def _preview(self) -> None:
        if self._mission_id:
            self.previewRequested.emit(self._mission_id)

    def _import(self) -> None:
        if self._mission_id:
            self.importRequested.emit(self._mission_id)

    def _nodeodm(self) -> None:
        if self._mission_id:
            self.nodeOdmRequested.emit(self._mission_id)

    def _analyze(self) -> None:
        product = self.selected_product()
        model = self.model_combo.currentData()
        artifact = self.artifact_combo.currentData()
        if (
            product is None
            or self._mission_id is None
            or not isinstance(model, AnalysisModelOption)
            or artifact is None
        ):
            return
        self.analyzeRequested.emit(
            product.product_id,
            AnalysisRequest(
                mission_id=self._mission_id,
                model_id=model.model_id,
                artifact_role=artifact.role,
                device=str(self.device_combo.currentData()),
                weed_threshold=self.threshold.value(),
            ),
        )

    def _export_heatmap(self) -> None:
        product = self.selected_product()
        job = self.job_combo.currentData()
        if product is not None and isinstance(job, AnalysisJob):
            self.heatmapRequested.emit(product.product_id, job.job_id)


class _SpatialAnalysisSettingsDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Thiết lập phân tích ảnh ghép")
        self.setMinimumWidth(420)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(250)
        self.artifact_combo = QComboBox()
        self.device_combo = QComboBox()
        self.device_combo.addItem("CPU", "cpu")
        self.device_combo.addItem("Apple MPS", "mps")
        self.device_combo.addItem("CUDA", "cuda")
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.05, 0.95)
        self.threshold.setSingleStep(0.05)
        self.threshold.setValue(0.5)
        self.threshold.setToolTip("Điểm ảnh có xác suất từ ngưỡng này trở lên được xếp là cỏ dại")
        layout = QFormLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addRow("Mô hình", self.model_combo)
        layout.addRow("Trọng số mô hình", self.artifact_combo)
        layout.addRow("Thiết bị tính toán", self.device_combo)
        layout.addRow("Ngưỡng cỏ dại", self.threshold)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_button is not None:
            save_button.setText("Lưu")
        if cancel_button is not None:
            cancel_button.setText("Hủy")
        layout.addRow(buttons)
        self._snapshot: tuple[int, int, int, float] | None = None

    def open_for_edit(self) -> None:
        self._snapshot = (
            self.model_combo.currentIndex(),
            self.artifact_combo.currentIndex(),
            self.device_combo.currentIndex(),
            self.threshold.value(),
        )
        self.exec()

    def reject(self) -> None:
        if self._snapshot is not None:
            model, artifact, device, threshold = self._snapshot
            self.model_combo.setCurrentIndex(model)
            self.artifact_combo.setCurrentIndex(artifact)
            self.device_combo.setCurrentIndex(device)
            self.threshold.setValue(threshold)
        super().reject()


def _compact_metric_value() -> QLabel:
    label = QLabel("—")
    label.setObjectName("CompactMetricValue")
    label.setWordWrap(True)
    return label


def _large_metric_value() -> QLabel:
    label = QLabel("—")
    label.setObjectName("MetricValue")
    label.setWordWrap(True)
    return label


def _value_label() -> QLabel:
    label = QLabel("—")
    label.setObjectName("InspectorValue")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _format_vi_number(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
