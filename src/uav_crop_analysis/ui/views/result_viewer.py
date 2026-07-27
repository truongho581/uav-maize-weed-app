"""Stable image/layer viewer with result inspector and legend."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSplitter,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.jobs.models import AnalysisJob
from uav_crop_analysis.ui.result_layers import (
    LayerMode,
    ResultImageEntry,
    render_layer,
    result_entries,
)


class ResultViewer(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._job: AnalysisJob | None = None
        self._entries: tuple[ResultImageEntry, ...] = ()
        self._scene = QGraphicsScene(self)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self.view = QGraphicsView(self._scene)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        toolbar = QGridLayout()
        toolbar.setHorizontalSpacing(8)
        toolbar.setVerticalSpacing(6)
        self.image_combo = QComboBox()
        self.image_combo.setMinimumWidth(160)
        self.image_combo.setMaximumWidth(220)
        self.image_combo.setAccessibleName("Chọn ảnh kết quả")
        self.image_combo.currentIndexChanged.connect(self._render)
        toolbar.addWidget(self.image_combo, 0, 0)
        self.layer_tabs = QTabBar()
        self.layer_tabs.setObjectName("LayerTabs")
        self.layer_tabs.setExpanding(False)
        self.layer_tabs.setUsesScrollButtons(False)
        for label, mode in (
            ("Gốc", LayerMode.ORIGINAL),
            ("Weed mask", LayerMode.WEED_MASK),
            ("Xác suất", LayerMode.PROBABILITY),
            ("Overlay", LayerMode.OVERLAY),
        ):
            index = self.layer_tabs.addTab(label)
            self.layer_tabs.setTabData(index, mode.value)
        self.layer_tabs.currentChanged.connect(self._layer_changed)
        toolbar.addWidget(self.layer_tabs, 0, 1, 1, 5)
        self.opacity_label = QLabel("Độ đậm 50%")
        self.opacity_label.setObjectName("MutedLabel")
        toolbar.addWidget(self.opacity_label, 1, 0, Qt.AlignmentFlag.AlignRight)
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(10, 100)
        self.opacity.setValue(50)
        self.opacity.setFixedWidth(120)
        self.opacity.setAccessibleName("Độ đậm overlay")
        self.opacity.valueChanged.connect(self._opacity_changed)
        toolbar.addWidget(self.opacity, 1, 1)
        toolbar.setColumnStretch(2, 1)
        self.zoom_out = QPushButton("−")
        self.zoom_out.setObjectName("IconButton")
        self.zoom_out.setToolTip("Thu nhỏ")
        self.zoom_out.clicked.connect(lambda: self.view.scale(0.8, 0.8))
        toolbar.addWidget(self.zoom_out, 1, 3)
        self.zoom_in = QPushButton("+")
        self.zoom_in.setObjectName("IconButton")
        self.zoom_in.setToolTip("Phóng to")
        self.zoom_in.clicked.connect(lambda: self.view.scale(1.25, 1.25))
        toolbar.addWidget(self.zoom_in, 1, 4)
        self.fit_button = QPushButton("Vừa khung")
        self.fit_button.setToolTip("Căn ảnh vừa vùng xem")
        self.fit_button.clicked.connect(self.fit_image)
        toolbar.addWidget(self.fit_button, 1, 5)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.view.setObjectName("ImageViewer")
        self.view.setBackgroundBrush(QBrush(QColor("#202724")))
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        splitter.addWidget(self.view)

        inspector = QWidget()
        inspector.setObjectName("InspectorPanel")
        inspector.setMinimumWidth(230)
        inspector.setMaximumWidth(300)
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(18, 16, 18, 16)
        inspector_layout.setSpacing(10)
        inspector_title = QLabel("Thông tin")
        inspector_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(inspector_title)
        self.model_value = _value_label()
        self.size_value = _value_label()
        self.coverage_value = _value_label()
        self.tiles_value = _value_label()
        self.source_value = _value_label()
        metrics = QGridLayout()
        metrics.setHorizontalSpacing(10)
        metrics.setVerticalSpacing(7)
        for row, (label, value) in enumerate((
            ("Mô hình", self.model_value),
            ("Kích thước", self.size_value),
            ("Tỷ lệ cỏ dại", self.coverage_value),
            ("Số tile", self.tiles_value),
            ("Ảnh nguồn", self.source_value),
        )):
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            metrics.addWidget(name, row, 0)
            metrics.addWidget(value, row, 1)
        metrics.setColumnStretch(1, 1)
        inspector_layout.addLayout(metrics)
        inspector_layout.addSpacing(8)
        legend_title = QLabel("Chú giải")
        legend_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(legend_title)
        legend = QHBoxLayout()
        swatch = QFrame()
        swatch.setObjectName("WeedSwatch")
        swatch.setFixedSize(16, 16)
        legend.addWidget(swatch)
        legend.addWidget(QLabel("Cỏ dại"))
        legend.addStretch()
        inspector_layout.addLayout(legend)
        self.message = QLabel("Chọn một job hoàn thành để xem kết quả.")
        self.message.setObjectName("MutedLabel")
        self.message.setWordWrap(True)
        inspector_layout.addWidget(self.message)
        inspector_layout.addStretch()
        splitter.addWidget(inspector)
        splitter.setStretchFactor(0, 1)
        root.addWidget(splitter, 1)
        self._update_opacity_visibility()

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
            self.message.setText(entry_error or "Job chưa có kết quả đã xuất bản.")
            self._clear_inspector()
            return
        self.image_combo.setCurrentIndex(0)
        self._render()

    def fit_image(self) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.view.fitInView(
                self._pixmap_item.boundingRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )

    def _render(self, *_args: object) -> None:
        index = self.image_combo.currentIndex()
        if not 0 <= index < len(self._entries):
            return
        entry = self._entries[index]
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
        self._update_opacity_visibility()
        self._render()

    def _opacity_changed(self, value: int) -> None:
        self.opacity_label.setText(f"Độ đậm {value}%")
        if self._current_mode() is LayerMode.OVERLAY:
            self._render()

    def _current_mode(self) -> LayerMode:
        return LayerMode(self.layer_tabs.tabData(self.layer_tabs.currentIndex()))

    def _update_opacity_visibility(self) -> None:
        visible = self._current_mode() is LayerMode.OVERLAY
        self.opacity.setVisible(visible)
        self.opacity_label.setVisible(visible)

    def _update_inspector(self, entry: ResultImageEntry) -> None:
        self.model_value.setText(self._job.config.model_id if self._job else "—")
        self.size_value.setText(f"{entry.width} × {entry.height}")
        self.coverage_value.setText(f"{entry.weed_coverage_percent:.2f}%")
        self.tiles_value.setText(str(entry.tile_count))
        self.source_value.setText(entry.source_path.name)
        self.source_value.setToolTip(str(entry.source_path))

    def _clear_inspector(self) -> None:
        for label in (
            self.model_value,
            self.size_value,
            self.coverage_value,
            self.tiles_value,
            self.source_value,
        ):
            label.setText("—")


def _value_label() -> QLabel:
    label = QLabel("—")
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label
