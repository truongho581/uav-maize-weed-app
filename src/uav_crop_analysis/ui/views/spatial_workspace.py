"""Spatial products, orthomosaic processing, and georeferenced heatmaps."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPixmap, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStyle,
    QTableView,
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
from uav_crop_analysis.ui.models import SpatialProductTableModel
from uav_crop_analysis.ui.views.common import configure_table, divider, stretch_columns


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
        self._scene.addItem(self._pixmap_item)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Không gian")
        title.setObjectName("PageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("MutedLabel")
        title_box.addWidget(title)
        title_box.addWidget(self.subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.preview_button = QPushButton("Tạo preview")
        self.preview_button.setToolTip("Tạo contact sheet theo ba làn bay; không có tọa độ")
        self.preview_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        )
        self.preview_button.clicked.connect(self._preview)
        header.addWidget(self.preview_button)
        self.import_button = QPushButton("Nhập GeoTIFF")
        self.import_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.import_button.clicked.connect(self._import)
        header.addWidget(self.import_button)
        self.nodeodm_button = QPushButton("Chạy NodeODM")
        self.nodeodm_button.setObjectName("PrimaryButton")
        self.nodeodm_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self.nodeodm_button.clicked.connect(self._nodeodm)
        header.addWidget(self.nodeodm_button)
        root.addLayout(header)

        readiness = QGridLayout()
        self.image_value = _metric_value()
        self.gps_value = _metric_value()
        self.altitude_value = _metric_value()
        self.engine_value = _metric_value()
        for column, (label, value) in enumerate(
            (
                ("Ảnh đầu vào", self.image_value),
                ("Có GPS", self.gps_value),
                ("Có độ cao", self.altitude_value),
                ("NodeODM", self.engine_value),
            )
        ):
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            readiness.addWidget(name, 0, column)
            readiness.addWidget(value, 1, column)
            readiness.setColumnStretch(column, 1)
        root.addLayout(readiness)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self.progress_label = QLabel()
        self.progress_label.setObjectName("MutedLabel")
        self.progress_label.setVisible(False)
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_label)
        root.addLayout(progress_row)
        root.addWidget(divider())

        self.product_table = QTableView()
        self.product_table.setModel(self.product_model)
        self.product_table.setAccessibleName("Sản phẩm không gian")
        self.product_table.setMaximumHeight(190)
        configure_table(self.product_table, row_height=40)
        stretch_columns(self.product_table, 0)
        self.product_table.selectionModel().selectionChanged.connect(
            self._selection_changed
        )
        root.addWidget(self.product_table)
        self.empty_products = QLabel("Chưa có sản phẩm không gian.")
        self.empty_products.setObjectName("MutedLabel")
        root.addWidget(self.empty_products)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.view = QGraphicsView(self._scene)
        self.view.setObjectName("ImageViewer")
        self.view.setBackgroundBrush(QBrush(QColor("#202724")))
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        splitter.addWidget(self.view)

        inspector = QWidget()
        inspector.setObjectName("InspectorPanel")
        inspector.setMinimumWidth(300)
        inspector.setMaximumWidth(360)
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(18, 16, 18, 16)
        inspector_layout.setSpacing(8)
        inspector_title = QLabel("Thông tin không gian")
        inspector_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(inspector_title)
        self.accuracy_value = _value_label()
        self.crs_value = _value_label()
        self.bounds_value = _value_label()
        self.resolution_value = _value_label()
        self.source_value = _value_label()
        details = QGridLayout()
        details.setVerticalSpacing(7)
        for row, (label, value) in enumerate(
            (
                ("Độ chính xác", self.accuracy_value),
                ("CRS", self.crs_value),
                ("Phạm vi", self.bounds_value),
                ("Độ phân giải", self.resolution_value),
                ("Nguồn", self.source_value),
            )
        ):
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            details.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
            details.addWidget(value, row, 1)
        details.setColumnStretch(1, 1)
        inspector_layout.addLayout(details)
        provenance_title = QLabel("Provenance")
        provenance_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(provenance_title)
        self.provenance_value = QLabel("—")
        self.provenance_value.setObjectName("MutedLabel")
        self.provenance_value.setWordWrap(True)
        self.provenance_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        inspector_layout.addWidget(self.provenance_value)
        inspector_layout.addStretch()
        splitter.addWidget(inspector)
        splitter.setStretchFactor(0, 1)
        root.addWidget(splitter, 1)

        analysis = QGridLayout()
        analysis.setHorizontalSpacing(10)
        analysis.setVerticalSpacing(6)
        analysis_title = QLabel("Phân tích semantic trên orthomosaic")
        analysis_title.setObjectName("SectionTitle")
        analysis.addWidget(analysis_title, 0, 0, 1, 5)
        self.model_combo = QComboBox()
        self.artifact_combo = QComboBox()
        self.device_combo = QComboBox()
        self.device_combo.addItem("CPU", "cpu")
        self.device_combo.addItem("Apple MPS", "mps")
        self.device_combo.addItem("CUDA", "cuda")
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.05, 0.95)
        self.threshold.setSingleStep(0.05)
        self.threshold.setValue(0.5)
        self.run_button = QPushButton("Phân tích")
        self.run_button.setObjectName("PrimaryButton")
        self.run_button.clicked.connect(self._analyze)
        for column, (label, widget) in enumerate(
            (
                ("Mô hình", self.model_combo),
                ("Checkpoint", self.artifact_combo),
                ("Thiết bị", self.device_combo),
                ("Ngưỡng weed", self.threshold),
            )
        ):
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            analysis.addWidget(name, 1, column)
            analysis.addWidget(widget, 2, column)
            analysis.setColumnStretch(column, 1)
        analysis.addWidget(self.run_button, 2, 4)
        self.job_combo = QComboBox()
        self.job_combo.currentIndexChanged.connect(self._update_actions)
        self.export_button = QPushButton("Xuất heatmap")
        self.export_button.clicked.connect(self._export_heatmap)
        analysis.addWidget(QLabel("Job orthomosaic"), 3, 0)
        analysis.addWidget(self.job_combo, 3, 1, 1, 3)
        analysis.addWidget(self.export_button, 3, 4)
        root.addLayout(analysis)
        self.message = QLabel()
        self.message.setObjectName("MutedLabel")
        root.addWidget(self.message)

        self.model_combo.currentIndexChanged.connect(self._model_changed)
        self._selection_changed()

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
        self.gps_value.setText(
            f"{workspace.geotagged_image_count:,}/{workspace.image_count:,}"
        )
        self.altitude_value.setText(
            f"{workspace.altitude_image_count:,}/{workspace.image_count:,}"
        )
        self.engine_value.setText("Sẵn sàng" if workspace.nodeodm_configured else "Chưa cấu hình")
        self.product_model.set_rows(workspace.products)
        self.empty_products.setVisible(not workspace.products)
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

    def has_active_jobs(self) -> bool:
        return any(
            job.status in {
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.CANCEL_REQUESTED,
            }
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

    def fit_image(self) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.view.fitInView(
                self._pixmap_item.boundingRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )

    def _set_models(self, models: tuple[AnalysisModelOption, ...]) -> None:
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for model in models:
            self.model_combo.addItem(model.model_id, model)
        self.model_combo.blockSignals(False)
        self._model_changed()

    def _model_changed(self, *_args: object) -> None:
        model = self.model_combo.currentData()
        self.artifact_combo.clear()
        if not isinstance(model, AnalysisModelOption):
            self._update_actions()
            return
        for artifact in model.artifacts:
            self.artifact_combo.addItem(artifact.role, artifact)
            item_model = self.artifact_combo.model()
            if isinstance(item_model, QStandardItemModel):
                item = item_model.item(self.artifact_combo.count() - 1)
                if item is not None:
                    item.setEnabled(artifact.available)
        self._update_actions()

    def _selection_changed(self, *_args: object) -> None:
        product = self.selected_product()
        if product is None:
            self._pixmap_item.setPixmap(QPixmap())
            self._clear_inspector()
            self.job_combo.clear()
            self._update_actions()
            return
        pixmap = QPixmap(str(product.preview_path))
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.fit_image()
        self._show_product(product)
        self.job_combo.clear()
        for job in self._product_jobs.get(product.product_id, ()):
            self.job_combo.addItem(
                f"{job.job_id} · {job.status.value} · {job.config.model_id}",
                job,
            )
        self._update_actions()

    def _show_product(self, product: SpatialProduct) -> None:
        raster = product.raster
        self.accuracy_value.setText(
            "Có georeference"
            if product.accuracy is SpatialAccuracy.GEOREFERENCED
            else "PREVIEW - KHÔNG GEOREFERENCE"
        )
        self.accuracy_value.setObjectName(
            "StatusReady"
            if product.accuracy is SpatialAccuracy.GEOREFERENCED
            else "StatusFailed"
        )
        self.accuracy_value.style().unpolish(self.accuracy_value)
        self.accuracy_value.style().polish(self.accuracy_value)
        self.crs_value.setText(raster.crs if raster else "—")
        self.bounds_value.setText(
            ", ".join(f"{value:.3f}" for value in raster.bounds) if raster else "—"
        )
        self.resolution_value.setText(
            f"{raster.resolution[0]:.5g} × {raster.resolution[1]:.5g}"
            if raster
            else "—"
        )
        self.source_value.setText(product.path.name)
        self.source_value.setToolTip(str(product.path))
        self.provenance_value.setText(
            json.dumps(dict(product.provenance), ensure_ascii=False, indent=2)
        )

    def _clear_inspector(self) -> None:
        for label in (
            self.accuracy_value,
            self.crs_value,
            self.bounds_value,
            self.resolution_value,
            self.source_value,
            self.provenance_value,
        ):
            label.setText("—")

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
            and workspace.nodeodm_configured
            and workspace.geospatial_ready
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


def _metric_value() -> QLabel:
    label = QLabel("—")
    label.setObjectName("MetricValue")
    return label


def _value_label() -> QLabel:
    label = QLabel("—")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label
