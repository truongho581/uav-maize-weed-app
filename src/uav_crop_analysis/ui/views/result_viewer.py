"""Stable image/layer viewer with result inspector and legend."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSplitter,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.jobs.models import AnalysisJob
from uav_crop_analysis.model_names import display_model_name
from uav_crop_analysis.ui.icons import configure_icon_button, set_button_icon
from uav_crop_analysis.ui.result_layers import (
    LayerMode,
    ResultImageEntry,
    render_layer,
    result_entries,
)
from uav_crop_analysis.ui.views.image_view import PanZoomGraphicsView
from uav_crop_analysis.ui.views.common import divider


class ResultViewer(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._job: AnalysisJob | None = None
        self._entries: tuple[ResultImageEntry, ...] = ()
        self._scene = QGraphicsScene(self)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self.view = PanZoomGraphicsView(self._scene)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("ViewerToolbar")
        toolbar_layout = QVBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        toolbar_layout.setSpacing(4)
        file_toolbar = QHBoxLayout()
        file_toolbar.setSpacing(6)
        self.previous_image = QPushButton()
        configure_icon_button(self.previous_image, "chevron-left", "Ảnh trước")
        self.previous_image.clicked.connect(lambda: self._step_image(-1))
        file_toolbar.addWidget(self.previous_image)
        self.image_combo = QComboBox()
        self.image_combo.setMinimumWidth(110)
        self.image_combo.setMaximumWidth(180)
        self.image_combo.setAccessibleName("Chọn ảnh kết quả")
        self.image_combo.currentIndexChanged.connect(self._image_changed)
        file_toolbar.addWidget(self.image_combo)
        self.next_image = QPushButton()
        configure_icon_button(self.next_image, "chevron-right", "Ảnh tiếp theo")
        self.next_image.clicked.connect(lambda: self._step_image(1))
        file_toolbar.addWidget(self.next_image)
        self.image_position = QLabel("0 / 0")
        self.image_position.setObjectName("MapStatusLabel")
        self.image_position.setMinimumWidth(36)
        self.image_position.setAlignment(Qt.AlignmentFlag.AlignCenter)
        file_toolbar.addWidget(self.image_position)
        self.actual_size = QPushButton("1:1")
        self.actual_size.setToolTip("Hiển thị ảnh ở tỷ lệ điểm ảnh gốc")
        self.actual_size.clicked.connect(self._actual_size)
        file_toolbar.addWidget(self.actual_size)
        self.layer_tabs = QTabBar()
        self.layer_tabs.setObjectName("LayerTabs")
        self.layer_tabs.setExpanding(False)
        self.layer_tabs.setUsesScrollButtons(True)
        self.layer_tabs.currentChanged.connect(self._layer_changed)
        self.layer_tabs.setVisible(False)
        file_toolbar.addStretch()
        tool_toolbar = file_toolbar
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        for name, icon, tip in (
            ("pan", "mouse-pointer-2", "Kéo bản đồ"),
            ("point", "crosshair", "Đo tọa độ điểm"),
            ("distance", "ruler", "Đo khoảng cách"),
            ("area", "square-dashed", "Đo diện tích; nhấp đúp để kết thúc"),
        ):
            button = QToolButton()
            configure_icon_button(button, icon, tip)
            button.setCheckable(True)
            button.setProperty("viewerTool", name)
            button.clicked.connect(lambda checked=False, value=name: self.view.set_tool(value))
            self.tool_group.addButton(button)
            tool_toolbar.addWidget(button)
            if name == "pan":
                button.setChecked(True)
                tool_toolbar.addWidget(divider(vertical=True))
            elif name == "area":
                tool_toolbar.addWidget(divider(vertical=True))
        self.zoom_out = QPushButton()
        configure_icon_button(self.zoom_out, "zoom-out", "Thu nhỏ")
        self.zoom_out.clicked.connect(lambda: self.view.zoom_by(1 / 1.25))
        tool_toolbar.addWidget(self.zoom_out)
        self.zoom_in = QPushButton()
        configure_icon_button(self.zoom_in, "zoom-in", "Phóng to")
        self.zoom_in.clicked.connect(lambda: self.view.zoom_by(1.25))
        tool_toolbar.addWidget(self.zoom_in)
        self.fit_button = QPushButton()
        configure_icon_button(
            self.fit_button,
            "maximize-2",
            "Hiển thị toàn bộ ảnh trong vùng xem",
        )
        self.fit_button.clicked.connect(self.fit_image)
        tool_toolbar.addWidget(self.fit_button)
        tool_toolbar.addWidget(divider(vertical=True))
        self.inspector_toggle = QToolButton()
        configure_icon_button(
            self.inspector_toggle,
            "eye-off",
            "Thu gọn bảng lớp và thông tin ảnh",
        )
        self.inspector_toggle.clicked.connect(self._toggle_inspector)
        tool_toolbar.addWidget(self.inspector_toggle)
        toolbar_layout.addLayout(tool_toolbar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        viewer_panel = QWidget()
        viewer_layout = QVBoxLayout(viewer_panel)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(8)
        viewer_layout.addWidget(toolbar_frame)
        self.view.setObjectName("ImageViewer")
        self.view.setBackgroundBrush(QBrush(QColor("#202724")))
        viewer_layout.addWidget(self.view, 1)
        viewer_status = QHBoxLayout()
        self.pointer_value = QLabel("x — · y —")
        self.pointer_value.setObjectName("MapStatusLabel")
        viewer_status.addWidget(self.pointer_value, 1)
        self.zoom_value = QLabel("Thu phóng —")
        self.zoom_value.setObjectName("MapStatusLabel")
        viewer_status.addWidget(self.zoom_value)
        viewer_layout.addLayout(viewer_status)

        self.inspector = QWidget()
        self.inspector.setObjectName("InspectorPanel")
        self.inspector.setMinimumWidth(240)
        self.inspector.setMaximumWidth(290)
        inspector_layout = QVBoxLayout(self.inspector)
        inspector_layout.setContentsMargins(12, 10, 12, 10)
        inspector_layout.setSpacing(6)
        inspector_title = QLabel("Lớp hiển thị")
        inspector_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(inspector_title)
        self.layer_list = QListWidget()
        self.layer_list.setObjectName("LayerList")
        self.layer_list.setFixedHeight(152)
        self.layer_list.itemChanged.connect(self._layer_item_changed)
        inspector_layout.addWidget(self.layer_list)
        details_title = QLabel("Thông tin")
        details_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(details_title)
        self.model_value = _value_label()
        self.size_value = _value_label()
        self.coverage_name = QLabel("Tỷ lệ cỏ dại")
        self.coverage_name.setObjectName("MetricLabel")
        self.coverage_value = _value_label()
        self.crop_coverage_name = QLabel("Tỷ lệ ngô")
        self.crop_coverage_name.setObjectName("MetricLabel")
        self.crop_coverage_value = _value_label()
        self.tiles_value = _value_label()
        self.source_value = _value_label()
        metrics = QGridLayout()
        metrics.setHorizontalSpacing(10)
        metrics.setVerticalSpacing(7)
        for row, (label, value) in enumerate(
            (
                ("Mô hình", self.model_value),
                ("Kích thước", self.size_value),
                (self.coverage_name, self.coverage_value),
                (self.crop_coverage_name, self.crop_coverage_value),
                ("Số ô xử lý", self.tiles_value),
                ("Tệp nguồn", self.source_value),
            )
        ):
            metric_name = label if isinstance(label, QLabel) else QLabel(str(label))
            metric_name.setObjectName("MetricLabel")
            metrics.addWidget(metric_name, row, 0)
            metrics.addWidget(value, row, 1)
        metrics.setColumnStretch(1, 1)
        inspector_layout.addLayout(metrics)
        opacity_row = QHBoxLayout()
        self.opacity_label = QLabel("Độ trong suốt")
        self.opacity_label.setObjectName("MetricLabel")
        self.opacity_value = QLabel("50%")
        self.opacity_value.setObjectName("MutedLabel")
        opacity_row.addWidget(self.opacity_label)
        opacity_row.addStretch()
        opacity_row.addWidget(self.opacity_value)
        inspector_layout.addLayout(opacity_row)
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(10, 100)
        self.opacity.setValue(50)
        self.opacity.setAccessibleName("Độ đậm lớp chồng")
        self.opacity.valueChanged.connect(self._opacity_changed)
        inspector_layout.addWidget(self.opacity)
        legend = QVBoxLayout()
        legend.setSpacing(5)
        primary_legend = QHBoxLayout()
        self.swatch = QFrame()
        self.swatch.setObjectName("WeedSwatch")
        self.swatch.setFixedSize(16, 16)
        primary_legend.addWidget(self.swatch)
        self.legend_label = QLabel("Cỏ dại")
        primary_legend.addWidget(self.legend_label)
        primary_legend.addStretch()
        legend.addLayout(primary_legend)
        secondary_legend = QHBoxLayout()
        self.crop_swatch = QFrame()
        self.crop_swatch.setObjectName("CropSwatch")
        self.crop_swatch.setFixedSize(16, 16)
        secondary_legend.addWidget(self.crop_swatch)
        self.crop_legend_label = QLabel("Ngô")
        secondary_legend.addWidget(self.crop_legend_label)
        secondary_legend.addStretch()
        legend.addLayout(secondary_legend)
        tertiary_legend = QHBoxLayout()
        self.maize6_swatch = QFrame()
        self.maize6_swatch.setObjectName("Maize6Swatch")
        self.maize6_swatch.setFixedSize(16, 16)
        tertiary_legend.addWidget(self.maize6_swatch)
        self.maize6_legend_label = QLabel("Ngô 6 lá")
        tertiary_legend.addWidget(self.maize6_legend_label)
        tertiary_legend.addStretch()
        legend.addLayout(tertiary_legend)
        self.maize6_swatch.setVisible(False)
        self.maize6_legend_label.setVisible(False)
        inspector_layout.addLayout(legend)
        self.message = QLabel("Chọn một tác vụ hoàn thành để xem kết quả.")
        self.message.setObjectName("MutedLabel")
        self.message.setWordWrap(True)
        inspector_layout.addWidget(self.message)
        inspector_layout.addStretch()
        self.splitter.addWidget(viewer_panel)
        self.splitter.addWidget(self.inspector)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setSizes((760, 260))
        root.addWidget(self.splitter, 1)
        self.inspector_expanded = True
        self._compact_width = False
        self.view.pointerMoved.connect(self._pointer_moved)
        self.view.zoomChanged.connect(self._zoom_changed)
        self.view.measurementChanged.connect(self._measurement_changed)
        self._configure_layers("semantic_segmentation")
        self._update_opacity_visibility()
        self._update_image_navigation()

    def set_job(self, job: AnalysisJob | None) -> None:
        self._job = job
        entry_error: str | None = None
        try:
            self._entries = result_entries(job) if job is not None else ()
        except Exception as exc:
            self._entries = ()
            entry_error = str(exc) or type(exc).__name__
        self.image_combo.blockSignals(True)
        self.image_combo.clear()
        for entry in self._entries:
            self.image_combo.addItem(entry.source_path.name, entry.image_id)
        self.image_combo.blockSignals(False)
        if not self._entries:
            self._pixmap_item.setPixmap(QPixmap())
            self.message.setText(entry_error or "Tác vụ chưa có kết quả để hiển thị.")
            self._clear_inspector()
            self._update_image_navigation()
            return
        self._configure_layers(self._entries[0].analysis_task)
        self.image_combo.setCurrentIndex(0)
        self._image_changed()

    def _step_image(self, offset: int) -> None:
        target = self.image_combo.currentIndex() + offset
        if 0 <= target < self.image_combo.count():
            self.image_combo.setCurrentIndex(target)

    def _image_changed(self, *_args: object) -> None:
        self._update_image_navigation()
        self._render()

    def _update_image_navigation(self) -> None:
        count = self.image_combo.count()
        current = self.image_combo.currentIndex()
        self.previous_image.setEnabled(count > 0 and current > 0)
        self.next_image.setEnabled(count > 0 and current < count - 1)
        self.image_position.setText(f"{current + 1} / {count}" if count else "0 / 0")

    def fit_image(self) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.view.resetTransform()
            self.view.fitInView(
                self._pixmap_item.boundingRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            self.view.notify_zoom()
            self.view.remember_view()

    def _actual_size(self) -> None:
        self.view.resetTransform()
        self.view.notify_zoom()
        self.view.remember_view()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 900
        if compact != self._compact_width:
            self._compact_width = compact
            self._set_inspector_expanded(not compact)

    def _toggle_inspector(self) -> None:
        self._set_inspector_expanded(not self.inspector_expanded)

    def _set_inspector_expanded(self, expanded: bool) -> None:
        self.inspector_expanded = expanded
        self.inspector.setVisible(expanded)
        set_button_icon(self.inspector_toggle, "eye-off" if expanded else "eye")
        self.inspector_toggle.setToolTip(
            "Thu gọn bảng lớp và thông tin ảnh"
            if expanded
            else "Mở bảng lớp và thông tin ảnh"
        )

    def _render(self, *_args: object) -> None:
        index = self.image_combo.currentIndex()
        if not 0 <= index < len(self._entries):
            return
        entry = self._entries[index]
        self.view.clear_measurements()
        mode = LayerMode(self.layer_tabs.tabData(self.layer_tabs.currentIndex()))
        try:
            image = render_layer(entry, mode, opacity=self.opacity.value() / 100)
        except Exception as exc:
            self._pixmap_item.setPixmap(QPixmap())
            self.message.setText(str(exc) or type(exc).__name__)
            return
        self._pixmap_item.setPixmap(QPixmap.fromImage(image))
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.message.setText("")
        self._update_inspector(entry)
        self.fit_image()

    def _layer_changed(self, _index: int) -> None:
        mode = self.layer_tabs.tabData(self.layer_tabs.currentIndex())
        self.layer_list.blockSignals(True)
        for row in range(self.layer_list.count()):
            item = self.layer_list.item(row)
            item.setCheckState(
                Qt.CheckState.Checked
                if item.data(Qt.ItemDataRole.UserRole) == mode
                else Qt.CheckState.Unchecked
            )
        self.layer_list.blockSignals(False)
        self._update_opacity_visibility()
        self._render()

    def _opacity_changed(self, value: int) -> None:
        self.opacity_value.setText(f"{value}%")
        if self._current_mode() is LayerMode.OVERLAY:
            self._render()

    def _current_mode(self) -> LayerMode:
        return LayerMode(self.layer_tabs.tabData(self.layer_tabs.currentIndex()))

    def _configure_layers(self, task: str) -> None:
        self.layer_tabs.blockSignals(True)
        self.layer_list.blockSignals(True)
        while self.layer_tabs.count():
            self.layer_tabs.removeTab(0)
        self.layer_list.clear()
        layers: tuple[tuple[str, LayerMode], ...]
        if task == "maize_instance_segmentation":
            layers = (
                ("Ảnh gốc", LayerMode.ORIGINAL),
                ("Mặt nạ cây ngô", LayerMode.INSTANCE_MASK),
                ("Chồng lớp", LayerMode.OVERLAY),
            )
            self.coverage_name.setText("Số cây ngô")
            self.legend_label.setText("Ngô 2 lá")
            self.swatch.setObjectName("Maize2Swatch")
            self.crop_legend_label.setText("Ngô 4 lá")
            self.crop_swatch.setObjectName("Maize4Swatch")
            self.crop_coverage_name.setVisible(False)
            self.crop_coverage_value.setVisible(False)
            self.crop_swatch.setVisible(True)
            self.crop_legend_label.setVisible(True)
            self.maize6_swatch.setVisible(True)
            self.maize6_legend_label.setVisible(True)
        else:
            layers = (
                ("Ảnh gốc", LayerMode.ORIGINAL),
                ("Phân vùng ngô - cỏ", LayerMode.SEMANTIC_MASK),
                ("Mặt nạ cỏ dại", LayerMode.WEED_MASK),
                ("Xác suất cỏ dại", LayerMode.PROBABILITY),
                ("Chồng lớp", LayerMode.OVERLAY),
            )
            self.coverage_name.setText("Tỷ lệ cỏ dại")
            self.legend_label.setText("Cỏ dại")
            self.swatch.setObjectName("WeedSwatch")
            self.crop_legend_label.setText("Ngô")
            self.crop_swatch.setObjectName("CropSwatch")
            self.crop_coverage_name.setVisible(True)
            self.crop_coverage_value.setVisible(True)
            self.crop_swatch.setVisible(True)
            self.crop_legend_label.setVisible(True)
            self.maize6_swatch.setVisible(False)
            self.maize6_legend_label.setVisible(False)
        for swatch in (self.swatch, self.crop_swatch, self.maize6_swatch):
            swatch.style().unpolish(swatch)
            swatch.style().polish(swatch)
        for label, mode in layers:
            index = self.layer_tabs.addTab(label)
            self.layer_tabs.setTabData(index, mode.value)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, mode.value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if index == 0 else Qt.CheckState.Unchecked)
            self.layer_list.addItem(item)
        self.layer_tabs.blockSignals(False)
        self.layer_list.blockSignals(False)
        self._update_opacity_visibility()

    def _layer_item_changed(self, selected: QListWidgetItem) -> None:
        if selected.checkState() is not Qt.CheckState.Checked:
            if not any(
                self.layer_list.item(row).checkState() is Qt.CheckState.Checked
                for row in range(self.layer_list.count())
            ):
                selected.setCheckState(Qt.CheckState.Checked)
            return
        self.layer_list.blockSignals(True)
        for row in range(self.layer_list.count()):
            item = self.layer_list.item(row)
            if item is not selected:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.layer_list.blockSignals(False)
        for index in range(self.layer_tabs.count()):
            if self.layer_tabs.tabData(index) == selected.data(Qt.ItemDataRole.UserRole):
                self.layer_tabs.setCurrentIndex(index)
                break

    def _update_opacity_visibility(self) -> None:
        current = self.image_combo.currentIndex()
        semantic = (
            not self._entries
            or not 0 <= current < len(self._entries)
            or self._entries[current].analysis_task == "semantic_segmentation"
        )
        visible = semantic and self._current_mode() is LayerMode.OVERLAY
        self.opacity.setVisible(visible)
        self.opacity_label.setVisible(visible)
        self.opacity_value.setVisible(visible)

    def _update_inspector(self, entry: ResultImageEntry) -> None:
        self.model_value.setText(
            display_model_name(self._job.config.model_id) if self._job else "—"
        )
        self.size_value.setText(f"{entry.width} × {entry.height}")
        self.coverage_value.setText(
            str(entry.maize_instance_count)
            if entry.analysis_task == "maize_instance_segmentation"
            else f"{entry.weed_coverage_percent:.2f}%"
        )
        self.crop_coverage_value.setText(f"{entry.crop_coverage_percent:.2f}%")
        self.tiles_value.setText(str(entry.tile_count))
        self.source_value.setText(entry.source_path.name)
        self.source_value.setToolTip(str(entry.source_path))

    def _pointer_moved(self, x: float, y: float) -> None:
        self.pointer_value.setText(f"Điểm ảnh x {x:.0f} · y {y:.0f}")

    def _zoom_changed(self, factor: float) -> None:
        self.zoom_value.setText(f"Thu phóng {factor * 100:.0f}%")

    def _measurement_changed(self, kind: str, value: object) -> None:
        if kind == "point" and isinstance(value, tuple):
            self.pointer_value.setText(f"Điểm ảnh x {value[0]:.0f} · y {value[1]:.0f}")
        elif kind == "distance" and isinstance(value, float):
            self.pointer_value.setText(f"Khoảng cách {value:.1f} px")
        elif kind == "area" and isinstance(value, float):
            self.pointer_value.setText(f"Diện tích {value:.1f} px²")

    def _clear_inspector(self) -> None:
        for label in (
            self.model_value,
            self.size_value,
            self.coverage_value,
            self.crop_coverage_value,
            self.tiles_value,
            self.source_value,
        ):
            label.setText("—")


def _value_label() -> QLabel:
    label = QLabel("—")
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label
