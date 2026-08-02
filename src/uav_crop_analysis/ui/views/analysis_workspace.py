"""Analysis configuration, persisted job queue, and result viewer."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabBar,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application.analysis_workspace import (
    AnalysisModelOption,
    AnalysisRequest,
    AnalysisTask,
)
from uav_crop_analysis.jobs.models import AnalysisJob, JobStatus
from uav_crop_analysis.model_names import display_model_name
from uav_crop_analysis.ui.icons import (
    ICON_ON_PRIMARY,
    configure_icon_button,
    set_button_icon,
)
from uav_crop_analysis.ui.components import StatusBadgeDelegate
from uav_crop_analysis.ui.models import AnalysisJobTableModel
from uav_crop_analysis.ui.views.common import configure_table, divider, stretch_columns
from uav_crop_analysis.ui.views.result_viewer import ResultViewer


class AnalysisWorkspacePage(QWidget):
    submitRequested = Signal(object)
    cancelRequested = Signal(str)
    retryRequested = Signal(str)
    deleteRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageSurface")
        self._mission_id: str | None = None
        self._semantic_models: tuple[AnalysisModelOption, ...] = ()
        self._instance_models: tuple[AnalysisModelOption, ...] = ()
        self.job_model = AnalysisJobTableModel()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(9)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        self.title = QLabel("Xử lý ảnh")
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("MutedLabel")
        title_box.addWidget(self.title)
        title_box.addWidget(self.subtitle)
        header.addLayout(title_box)
        header.addStretch()
        root.addLayout(header)

        self.task_tabs = QTabBar()
        self.task_tabs.setObjectName("SegmentedTabs")
        self.task_tabs.setExpanding(True)
        self.task_tabs.setUsesScrollButtons(False)
        semantic_index = self.task_tabs.addTab("Phân vùng ngô - cỏ")
        instance_index = self.task_tabs.addTab("Đếm cây ngô")
        self.task_tabs.setTabToolTip(semantic_index, "Phân vùng semantic ngô và cỏ dại")
        self.task_tabs.setTabToolTip(instance_index, "Đếm và phân tầng từng cây ngô")
        self.task_tabs.setTabData(semantic_index, AnalysisTask.SEMANTIC.value)
        self.task_tabs.setTabData(instance_index, AnalysisTask.MAIZE_INSTANCE.value)
        self.task_tabs.currentChanged.connect(self._task_changed)
        self.model_combo = QComboBox()
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        self.settings_dialog = _AnalysisSettingsDialog(self)
        self.artifact_combo = self.settings_dialog.artifact_combo
        self.device_combo = self.settings_dialog.device_combo
        self.tile_size = self.settings_dialog.tile_size
        self.overlap = self.settings_dialog.overlap
        self.threshold = self.settings_dialog.threshold
        self.device_combo.currentIndexChanged.connect(self._update_settings_summary)
        self.tile_size.valueChanged.connect(self._update_settings_summary)
        self.overlap.valueChanged.connect(self._update_settings_summary)
        self.threshold.valueChanged.connect(self._update_settings_summary)
        self.run_button = QPushButton("Chạy phân tích")
        self.run_button.setObjectName("PrimaryButton")
        set_button_icon(self.run_button, "play", color=ICON_ON_PRIMARY)
        self.run_button.clicked.connect(self._submit)
        self.settings_summary = QLabel()
        self.settings_summary.setObjectName("MutedLabel")
        self.settings_summary.setVisible(False)
        self.device_value = QLabel("—")
        self.tile_value = QLabel("—")
        self.overlap_value = QLabel("—")
        self.threshold_value = QLabel("—")
        for value in (
            self.device_value,
            self.tile_value,
            self.overlap_value,
            self.threshold_value,
        ):
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.settings_button = QPushButton()
        configure_icon_button(
            self.settings_button,
            "settings-2",
            "Thiết lập mô hình và cách xử lý ảnh",
        )
        self.settings_button.clicked.connect(self._open_settings)
        self.model_status = QLabel()
        self.model_status.setObjectName("MutedLabel")
        self.model_status.setWordWrap(True)

        self.cancel_button = QToolButton()
        configure_icon_button(
            self.cancel_button,
            "circle-stop",
            "Hủy tác vụ đang chạy",
        )
        self.cancel_button.clicked.connect(self._cancel)
        self.retry_button = QToolButton()
        configure_icon_button(
            self.retry_button,
            "rotate-ccw",
            "Chạy lại tác vụ lỗi hoặc đã hủy",
        )
        self.retry_button.clicked.connect(self._retry)
        self.delete_button = QToolButton()
        configure_icon_button(
            self.delete_button,
            "trash-2",
            "Xóa tác vụ cùng toàn bộ kết quả",
        )
        self.delete_button.clicked.connect(self._delete)
        self.open_result_button = QToolButton()
        configure_icon_button(
            self.open_result_button,
            "image",
            "Mở kết quả tác vụ hoàn thành",
        )
        self.open_result_button.clicked.connect(self._open_result)
        self.queue_toggle = QToolButton()
        configure_icon_button(
            self.queue_toggle,
            "eye-off",
            "Thu gọn hàng đợi xử lý",
        )
        self.queue_toggle.clicked.connect(self._toggle_queue)
        self.queue_expanded = True
        self._compact_height = False

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setChildrenCollapsible(False)
        settings_panel = QWidget()
        settings_panel.setObjectName("WorkspacePanel")
        settings_panel.setMinimumWidth(230)
        settings_panel.setMaximumWidth(285)
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(14, 14, 14, 14)
        settings_layout.setSpacing(9)
        settings_title = QLabel("Thiết lập mô hình")
        settings_title.setObjectName("SectionTitle")
        settings_layout.addWidget(settings_title)
        settings_layout.addWidget(self.task_tabs)
        model_label = QLabel("Mô hình")
        model_label.setObjectName("MetricLabel")
        settings_layout.addWidget(model_label)
        settings_layout.addWidget(self.model_combo)
        settings_layout.addWidget(self.model_status)
        settings_layout.addWidget(divider())
        settings_header = QHBoxLayout()
        settings_label = QLabel("Thông số xử lý")
        settings_label.setObjectName("SectionTitle")
        settings_header.addWidget(settings_label)
        settings_header.addStretch()
        settings_header.addWidget(self.settings_button)
        settings_layout.addLayout(settings_header)
        settings_grid = QGridLayout()
        settings_grid.setHorizontalSpacing(12)
        settings_grid.setVerticalSpacing(6)
        for row, (label, value) in enumerate(
            (
                ("Thiết bị", self.device_value),
                ("Kích thước ô", self.tile_value),
                ("Chồng phủ", self.overlap_value),
                ("Ngưỡng", self.threshold_value),
            )
        ):
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            settings_grid.addWidget(name, row, 0)
            settings_grid.addWidget(value, row, 1)
        settings_grid.setColumnStretch(1, 1)
        settings_layout.addLayout(settings_grid)
        settings_layout.addStretch()
        settings_layout.addWidget(self.run_button)
        self.workspace_splitter.addWidget(settings_panel)
        self.viewer = ResultViewer()
        self.viewer.setMinimumHeight(330)
        self.workspace_splitter.addWidget(self.viewer)
        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setSizes((260, 1080))
        root.addWidget(self.workspace_splitter, 1)

        self.queue_panel = QWidget()
        self.queue_panel.setObjectName("WorkspacePanel")
        self.queue_panel.setMinimumHeight(40)
        self.queue_panel.setMaximumHeight(170)
        queue_layout = QVBoxLayout(self.queue_panel)
        queue_layout.setContentsMargins(12, 8, 12, 10)
        queue_layout.setSpacing(6)
        queue_header = QHBoxLayout()
        self.queue_title = QLabel("Hàng đợi xử lý · 0 tác vụ")
        self.queue_title.setObjectName("SectionTitle")
        queue_header.addWidget(self.queue_title)
        queue_header.addStretch()
        queue_header.addWidget(self.queue_toggle)
        queue_header.addWidget(self.cancel_button)
        queue_header.addWidget(self.retry_button)
        queue_header.addWidget(self.delete_button)
        queue_header.addWidget(self.open_result_button)
        queue_layout.addLayout(queue_header)
        self.job_table = QTableView()
        self.job_table.setModel(self.job_model)
        self.job_table.setAccessibleName("Hàng đợi xử lý")
        configure_table(self.job_table, row_height=42)
        self.job_table.setItemDelegateForColumn(1, StatusBadgeDelegate(self.job_table))
        stretch_columns(self.job_table, 0)
        self.job_table.selectionModel().selectionChanged.connect(self._selection_changed)
        queue_layout.addWidget(self.job_table)
        self.empty_jobs = QLabel("Chưa có tác vụ xử lý.")
        self.empty_jobs.setObjectName("MutedLabel")
        self.empty_jobs.setVisible(False)
        queue_layout.addWidget(self.empty_jobs)
        root.addWidget(self.queue_panel)
        self._update_settings_summary()
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
        self.queue_title.setText(f"Hàng đợi xử lý · {len(jobs)} tác vụ")
        self.empty_jobs.setVisible(self.queue_expanded and not jobs)
        if jobs:
            row = next(
                (index for index, job in enumerate(jobs) if job.job_id == selected_id),
                0,
            )
            self.job_table.selectRow(row)
        self._selection_changed()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().height() < 760
        if compact != self._compact_height:
            self._compact_height = compact
            self._set_queue_expanded(not compact)

    def _toggle_queue(self) -> None:
        self._set_queue_expanded(not self.queue_expanded)

    def _set_queue_expanded(self, expanded: bool) -> None:
        self.queue_expanded = expanded
        self.job_table.setVisible(expanded)
        self.empty_jobs.setVisible(expanded and not self.job_model.rows)
        self.queue_panel.setMaximumHeight(170 if expanded else 42)
        set_button_icon(self.queue_toggle, "eye-off" if expanded else "eye")
        self.queue_toggle.setToolTip(
            "Thu gọn hàng đợi xử lý" if expanded else "Mở hàng đợi xử lý"
        )

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
        self._update_settings_summary()

    def _populate_models(self) -> None:
        task = AnalysisTask(self.task_tabs.tabData(self.task_tabs.currentIndex()))
        models = self._semantic_models if task is AnalysisTask.SEMANTIC else self._instance_models
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
            self.model_status.setText("Không có mô hình phù hợp.")
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
        model_name = display_model_name(model.model_id)
        self.run_button.setEnabled(model.available and bool(self._mission_id))
        if semantic:
            self.model_status.setText(
                f"{model_name} · Phân vùng ngô - cỏ dại · "
                f"{'sẵn sàng' if model.available else 'chưa có trọng số'}"
            )
        elif model.available:
            self.model_status.setText(
                f"{model_name} · Tách từng cây ngô · sẵn sàng"
            )
        else:
            self.model_status.setText(
                "Chưa đăng ký trọng số mô hình đối tượng; chưa thể xử lý cây ngô."
            )
        self.threshold.setEnabled(semantic)
        self.settings_dialog.threshold_label.setEnabled(semantic)

    def _open_settings(self) -> None:
        self.settings_dialog.open_for_edit()
        self._update_settings_summary()

    def _update_settings_summary(self, *_args: object) -> None:
        task = AnalysisTask(self.task_tabs.tabData(self.task_tabs.currentIndex()))
        threshold = (
            f"ngưỡng cỏ dại {self.threshold.value():.2f}"
            if task is AnalysisTask.SEMANTIC
            else "điểm tin cậy theo trọng số"
        )
        self.settings_summary.setText(
            f"{self.device_combo.currentText()} · ô ảnh {self.tile_size.value()} px · "
            f"chồng phủ {self.overlap.value()} px · {threshold}"
        )
        self.device_value.setText(self.device_combo.currentText())
        self.tile_value.setText(f"{self.tile_size.value()} px")
        self.overlap_value.setText(f"{self.overlap.value()} px")
        self.threshold_value.setText(
            f"{self.threshold.value():.2f}" if task is AnalysisTask.SEMANTIC else "Theo mô hình"
        )
        self.settings_button.setToolTip("Thiết lập hiện tại: " + self.settings_summary.text())

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
        self.open_result_button.setEnabled(job is not None and job.status is JobStatus.COMPLETED)
        self.delete_button.setEnabled(
            job is not None
            and job.status
            in {JobStatus.QUEUED, JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED}
        )
        if job is not None and job.status is JobStatus.COMPLETED:
            self.viewer.set_job(job)

    def _cancel(self) -> None:
        job = self._selected_job()
        if job is not None:
            self.cancelRequested.emit(job.job_id)

    def _retry(self) -> None:
        job = self._selected_job()
        if job is not None:
            self.retryRequested.emit(job.job_id)

    def _delete(self) -> None:
        job = self._selected_job()
        if job is not None:
            self.deleteRequested.emit(job.job_id)

    def _open_result(self) -> None:
        self.viewer.set_job(self._selected_job())


class _AnalysisSettingsDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Thiết lập phân tích")
        self.setMinimumWidth(380)
        self.artifact_combo = QComboBox()
        self.artifact_combo.setMinimumWidth(220)
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
        layout = QFormLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        self.tile_size.setToolTip(
            "Ảnh lớn được chia thành các ô vuông có kích thước này trước khi xử lý"
        )
        self.overlap.setToolTip("Số điểm ảnh dùng chung giữa hai ô kề nhau để giảm đường nối")
        layout.addRow("Trọng số mô hình", self.artifact_combo)
        layout.addRow("Thiết bị tính toán", self.device_combo)
        layout.addRow("Kích thước ô ảnh (px)", self.tile_size)
        layout.addRow("Độ chồng phủ (px)", self.overlap)
        self.threshold_label = QLabel("Ngưỡng cỏ dại")
        layout.addRow(self.threshold_label, self.threshold)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_button is not None:
            save_button.setText("Lưu")
        if cancel_button is not None:
            cancel_button.setText("Hủy")
        layout.addRow(self.buttons)
        self._snapshot: tuple[int, int, int, int, float] | None = None

    def open_for_edit(self) -> None:
        self._snapshot = (
            self.artifact_combo.currentIndex(),
            self.device_combo.currentIndex(),
            self.tile_size.value(),
            self.overlap.value(),
            self.threshold.value(),
        )
        self.exec()

    def reject(self) -> None:
        if self._snapshot is not None:
            artifact, device, tile, overlap, threshold = self._snapshot
            self.artifact_combo.setCurrentIndex(artifact)
            self.device_combo.setCurrentIndex(device)
            self.tile_size.setValue(tile)
            self.overlap.setValue(overlap)
            self.threshold.setValue(threshold)
        super().reject()
