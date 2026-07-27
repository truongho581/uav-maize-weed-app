"""Analysis configuration, persisted job queue, and result viewer."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStyle,
    QTabBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application.analysis_workspace import (
    AnalysisModelOption,
    AnalysisRequest,
    AnalysisTask,
)
from uav_crop_analysis.jobs.models import AnalysisJob, JobStatus
from uav_crop_analysis.ui.models import AnalysisJobTableModel
from uav_crop_analysis.ui.views.common import configure_table, divider, stretch_columns
from uav_crop_analysis.ui.views.result_viewer import ResultViewer


class AnalysisWorkspacePage(QWidget):
    submitRequested = Signal(object)
    cancelRequested = Signal(str)
    retryRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageSurface")
        self._mission_id: str | None = None
        self._semantic_models: tuple[AnalysisModelOption, ...] = ()
        self._instance_models: tuple[AnalysisModelOption, ...] = ()
        self.job_model = AnalysisJobTableModel()

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        self.title = QLabel("Phân tích")
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("MutedLabel")
        title_box.addWidget(self.title)
        title_box.addWidget(self.subtitle)
        header.addLayout(title_box)
        header.addStretch()
        root.addLayout(header)

        self.task_tabs = QTabBar()
        self.task_tabs.setExpanding(False)
        semantic_index = self.task_tabs.addTab("Cỏ dại · Semantic")
        instance_index = self.task_tabs.addTab("Ngô · Instance")
        self.task_tabs.setTabData(semantic_index, AnalysisTask.SEMANTIC.value)
        self.task_tabs.setTabData(instance_index, AnalysisTask.MAIZE_INSTANCE.value)
        self.task_tabs.currentChanged.connect(self._task_changed)
        root.addWidget(self.task_tabs)

        config = QGridLayout()
        config.setHorizontalSpacing(12)
        config.setVerticalSpacing(6)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        self.artifact_combo = QComboBox()
        self.artifact_combo.setMinimumWidth(180)
        self.device_combo = QComboBox()
        self.device_combo.addItem("CPU", "cpu")
        self.device_combo.addItem("Apple MPS", "mps")
        self.device_combo.addItem("CUDA", "cuda")
        self.tile_size = QSpinBox()
        self.tile_size.setRange(256, 2048)
        self.tile_size.setSingleStep(64)
        self.tile_size.setValue(640)
        self.overlap = QSpinBox()
        self.overlap.setRange(0, 512)
        self.overlap.setSingleStep(16)
        self.overlap.setValue(64)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.05, 0.95)
        self.threshold.setSingleStep(0.05)
        self.threshold.setValue(0.5)
        self.run_button = QPushButton("Chạy phân tích")
        self.run_button.setObjectName("PrimaryButton")
        self.run_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self.run_button.clicked.connect(self._submit)
        controls = (
            ("Mô hình", self.model_combo, 0),
            ("Checkpoint", self.artifact_combo, 1),
            ("Thiết bị", self.device_combo, 2),
        )
        for label, widget, column in controls:
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            config.addWidget(name, 0, column)
            config.addWidget(widget, 1, column)
        config.addWidget(self.run_button, 1, 3)
        for label, numeric_widget, column in (
            ("Tile", self.tile_size, 0),
            ("Overlap", self.overlap, 1),
            ("Ngưỡng cỏ dại", self.threshold, 2),
        ):
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            config.addWidget(name, 2, column)
            config.addWidget(numeric_widget, 3, column)
        config.setColumnStretch(0, 1)
        config.setColumnStretch(1, 1)
        root.addLayout(config)
        self.model_status = QLabel()
        self.model_status.setObjectName("MutedLabel")
        root.addWidget(self.model_status)
        root.addWidget(divider())

        queue_header = QHBoxLayout()
        queue_title = QLabel("Hàng đợi phân tích")
        queue_title.setObjectName("SectionTitle")
        queue_header.addWidget(queue_title)
        queue_header.addStretch()
        self.cancel_button = QPushButton("Hủy")
        self.cancel_button.clicked.connect(self._cancel)
        queue_header.addWidget(self.cancel_button)
        self.retry_button = QPushButton("Chạy lại")
        self.retry_button.clicked.connect(self._retry)
        queue_header.addWidget(self.retry_button)
        self.open_result_button = QPushButton("Mở kết quả")
        self.open_result_button.clicked.connect(self._open_result)
        queue_header.addWidget(self.open_result_button)
        root.addLayout(queue_header)

        splitter = QSplitter()
        queue_panel = QWidget()
        queue_layout = QVBoxLayout(queue_panel)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        self.job_table = QTableView()
        self.job_table.setModel(self.job_model)
        self.job_table.setAccessibleName("Hàng đợi phân tích")
        configure_table(self.job_table, row_height=42)
        stretch_columns(self.job_table, 1)
        self.job_table.selectionModel().selectionChanged.connect(self._selection_changed)
        queue_layout.addWidget(self.job_table)
        self.empty_jobs = QLabel("Chưa có job phân tích.")
        self.empty_jobs.setObjectName("MutedLabel")
        queue_layout.addWidget(self.empty_jobs)
        splitter.addWidget(queue_panel)
        self.viewer = ResultViewer()
        splitter.addWidget(self.viewer)
        splitter.setOrientation(Qt.Orientation.Vertical)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)
        self._selection_changed()

    def set_workspace(
        self,
        mission_id: str,
        semantic_models: tuple[AnalysisModelOption, ...],
        instance_models: tuple[AnalysisModelOption, ...],
        jobs: tuple[AnalysisJob, ...],
    ) -> None:
        self._mission_id = mission_id
        self.subtitle.setText(mission_id)
        self.model_status.setObjectName("MutedLabel")
        self.model_status.style().unpolish(self.model_status)
        self.model_status.style().polish(self.model_status)
        self._semantic_models = semantic_models
        self._instance_models = instance_models
        self._populate_models()
        self.set_jobs(jobs)

    def set_jobs(self, jobs: tuple[AnalysisJob, ...]) -> None:
        selected = self._selected_job()
        selected_id = selected.job_id if selected else None
        self.job_model.set_rows(jobs)
        self.empty_jobs.setVisible(not jobs)
        if jobs:
            row = next(
                (index for index, job in enumerate(jobs) if job.job_id == selected_id),
                0,
            )
            self.job_table.selectRow(row)
        self._selection_changed()

    def show_error(self, message: str) -> None:
        self.model_status.setObjectName("StatusFailed")
        self.model_status.setText(message)
        self.model_status.style().unpolish(self.model_status)
        self.model_status.style().polish(self.model_status)

    def has_active_jobs(self) -> bool:
        return any(
            job.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}
            for job in self.job_model.rows
        )

    def _task_changed(self, _index: int) -> None:
        self._populate_models()

    def _populate_models(self) -> None:
        task = AnalysisTask(self.task_tabs.tabData(self.task_tabs.currentIndex()))
        models = self._semantic_models if task is AnalysisTask.SEMANTIC else self._instance_models
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
            self.model_status.setText("Không có model phù hợp.")
            self.run_button.setEnabled(False)
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
        semantic = model.task is AnalysisTask.SEMANTIC
        self.run_button.setEnabled(semantic and model.available and bool(self._mission_id))
        if semantic:
            self.model_status.setText(
                f"{model.family} · {model.runtime} · output: weed semantic · {model.status}"
            )
        else:
            self.model_status.setText(
                "Checkpoint instance chưa được đăng ký; không thể chạy phân tích ngô."
            )

    def _submit(self) -> None:
        model = self.model_combo.currentData()
        artifact = self.artifact_combo.currentData()
        if (
            self._mission_id is None
            or not isinstance(model, AnalysisModelOption)
            or artifact is None
        ):
            return
        overlap = min(self.overlap.value(), self.tile_size.value() - 1)
        self.submitRequested.emit(
            AnalysisRequest(
                mission_id=self._mission_id,
                model_id=model.model_id,
                artifact_role=artifact.role,
                device=str(self.device_combo.currentData()),
                tile_size=self.tile_size.value(),
                overlap=overlap,
                weed_threshold=self.threshold.value(),
            )
        )

    def _selected_job(self) -> AnalysisJob | None:
        rows = self.job_table.selectionModel().selectedRows()
        return self.job_model.job_at(rows[0].row()) if rows else None

    def _selection_changed(self, *_args: object) -> None:
        job = self._selected_job()
        self.cancel_button.setEnabled(
            job is not None and job.status in {JobStatus.QUEUED, JobStatus.RUNNING}
        )
        self.retry_button.setEnabled(
            job is not None and job.status in {JobStatus.FAILED, JobStatus.CANCELLED}
        )
        self.open_result_button.setEnabled(
            job is not None and job.status is JobStatus.COMPLETED
        )

    def _cancel(self) -> None:
        job = self._selected_job()
        if job is not None:
            self.cancelRequested.emit(job.job_id)

    def _retry(self) -> None:
        job = self._selected_job()
        if job is not None:
            self.retryRequested.emit(job.job_id)

    def _open_result(self) -> None:
        self.viewer.set_job(self._selected_job())
