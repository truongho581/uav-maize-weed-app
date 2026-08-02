"""Quick model verification workspace for an independent image or video."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application import (
    AnalysisModelOption,
    AnalysisTask,
    ModelTestRequest,
    ModelTestResult,
)
from uav_crop_analysis.model_names import display_model_name
from uav_crop_analysis.ui.icons import (
    ICON_ON_PRIMARY,
    configure_icon_button,
    set_button_icon,
)
from uav_crop_analysis.ui.views.common import divider
from uav_crop_analysis.ui.views.result_viewer import ResultViewer


class ModelTestWorkspacePage(QWidget):
    sourceRequested = Signal()
    testRequested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageSurface")
        self._source_path: Path | None = None
        self._semantic_models: tuple[AnalysisModelOption, ...] = ()
        self._instance_models: tuple[AnalysisModelOption, ...] = ()
        self._busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(9)
        self.title = QLabel("Kiểm tra mô hình")
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel("Chưa chọn tệp")
        self.subtitle.setObjectName("MutedLabel")
        root.addWidget(self.title)
        root.addWidget(self.subtitle)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        settings_panel = QWidget()
        settings_panel.setObjectName("WorkspacePanel")
        settings_panel.setMinimumWidth(230)
        settings_panel.setMaximumWidth(285)
        settings = QVBoxLayout(settings_panel)
        settings.setContentsMargins(14, 14, 14, 14)
        settings.setSpacing(9)
        heading = QLabel("Mô hình và dữ liệu")
        heading.setObjectName("SectionTitle")
        settings.addWidget(heading)

        self.task_tabs = QTabBar()
        self.task_tabs.setObjectName("SegmentedTabs")
        self.task_tabs.setExpanding(True)
        semantic = self.task_tabs.addTab("Ngô - cỏ")
        instance = self.task_tabs.addTab("Cây ngô")
        self.task_tabs.setTabToolTip(semantic, "Phân vùng semantic ngô và cỏ dại")
        self.task_tabs.setTabToolTip(instance, "Đếm và phân tầng từng cây ngô")
        self.task_tabs.setTabData(semantic, AnalysisTask.SEMANTIC.value)
        self.task_tabs.setTabData(instance, AnalysisTask.MAIZE_INSTANCE.value)
        self.task_tabs.currentChanged.connect(self._task_changed)
        settings.addWidget(self.task_tabs)

        model_label = QLabel("Mô hình")
        model_label.setObjectName("MetricLabel")
        settings.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        settings.addWidget(self.model_combo)
        self.model_status = QLabel("—")
        self.model_status.setObjectName("MutedLabel")
        self.model_status.setWordWrap(True)
        settings.addWidget(self.model_status)
        settings.addWidget(divider())

        source_header = QHBoxLayout()
        source_label = QLabel("Tệp kiểm tra")
        source_label.setObjectName("SectionTitle")
        source_header.addWidget(source_label)
        source_header.addStretch()
        self.source_button = QPushButton()
        configure_icon_button(self.source_button, "folder-input", "Chọn ảnh hoặc video")
        self.source_button.clicked.connect(self.sourceRequested)
        source_header.addWidget(self.source_button)
        settings.addLayout(source_header)
        self.source_value = QLabel("Chưa chọn tệp")
        self.source_value.setObjectName("MutedLabel")
        self.source_value.setWordWrap(True)
        settings.addWidget(self.source_value)
        settings.addWidget(divider())

        parameter_header = QHBoxLayout()
        parameter_title = QLabel("Thông số xử lý")
        parameter_title.setObjectName("SectionTitle")
        parameter_header.addWidget(parameter_title)
        parameter_header.addStretch()
        self.settings_button = QPushButton()
        configure_icon_button(self.settings_button, "settings-2", "Thiết lập kiểm tra")
        parameter_header.addWidget(self.settings_button)
        settings.addLayout(parameter_header)
        self.settings_dialog = _ModelTestSettingsDialog(self)
        self.settings_button.clicked.connect(self.settings_dialog.open)
        self.artifact_combo = self.settings_dialog.artifact_combo
        self.device_combo = self.settings_dialog.device_combo
        self.tile_size = self.settings_dialog.tile_size
        self.overlap = self.settings_dialog.overlap
        self.threshold = self.settings_dialog.threshold
        for control in (
            self.device_combo,
            self.tile_size,
            self.overlap,
            self.threshold,
            self.artifact_combo,
        ):
            signal = getattr(control, "currentIndexChanged", None) or getattr(
                control,
                "valueChanged",
            )
            signal.connect(self._update_summary)
        self.device_value = QLabel()
        self.tile_value = QLabel()
        self.overlap_value = QLabel()
        self.threshold_value = QLabel()
        summary_grid = QGridLayout()
        summary_grid.setHorizontalSpacing(12)
        summary_grid.setVerticalSpacing(6)
        for row, (name, value) in enumerate(
            (
                ("Thiết bị", self.device_value),
                ("Kích thước ô", self.tile_value),
                ("Chồng phủ", self.overlap_value),
                ("Ngưỡng", self.threshold_value),
            )
        ):
            label = QLabel(name)
            label.setObjectName("MetricLabel")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            summary_grid.addWidget(label, row, 0)
            summary_grid.addWidget(value, row, 1)
        summary_grid.setColumnStretch(1, 1)
        settings.addLayout(summary_grid)
        settings.addStretch()

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        settings.addWidget(self.progress)
        self.message = QLabel()
        self.message.setObjectName("MutedLabel")
        self.message.setWordWrap(True)
        settings.addWidget(self.message)
        self.run_button = QPushButton("Chạy kiểm tra")
        self.run_button.setObjectName("PrimaryButton")
        set_button_icon(self.run_button, "play", color=ICON_ON_PRIMARY)
        self.run_button.clicked.connect(self._submit)
        settings.addWidget(self.run_button)

        splitter.addWidget(settings_panel)
        self.viewer = ResultViewer()
        splitter.addWidget(self.viewer)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes((260, 1080))
        root.addWidget(splitter, 1)
        self._update_summary()
        self._update_run_state()

    def set_models(
        self,
        semantic_models: tuple[AnalysisModelOption, ...],
        instance_models: tuple[AnalysisModelOption, ...],
    ) -> None:
        self._semantic_models = semantic_models
        self._instance_models = instance_models
        self._task_changed()

    def set_source(self, path: Path) -> None:
        self._source_path = Path(path).expanduser().resolve()
        self.source_value.setText(self._source_path.name)
        self.source_value.setToolTip(str(self._source_path))
        self.subtitle.setText(str(self._source_path))
        self._update_run_state()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.progress.setVisible(busy)
        self.source_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.task_tabs.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        self._update_run_state()
        if busy:
            self.show_message("Đang nạp mô hình...")

    def set_progress(self, value: float, detail: str) -> None:
        self.progress.setValue(round(max(0.0, min(value, 1.0)) * 100))
        self.show_message(detail)

    def set_result(self, result: ModelTestResult) -> None:
        self.viewer.set_job(result.job)
        media = "video" if result.media_kind == "video" else "ảnh"
        self.show_message(f"Hoàn tất · {result.frame_count} khung {media}")

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

    def _task_changed(self, *_args: object) -> None:
        task = AnalysisTask(self.task_tabs.tabData(self.task_tabs.currentIndex()))
        models = (
            self._semantic_models
            if task is AnalysisTask.SEMANTIC
            else self._instance_models
        )
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for model in models:
            self.model_combo.addItem(_model_name(model), model)
        self.model_combo.blockSignals(False)
        self._model_changed()

    def _model_changed(self, *_args: object) -> None:
        model = self.model_combo.currentData()
        self.artifact_combo.blockSignals(True)
        self.artifact_combo.clear()
        if isinstance(model, AnalysisModelOption):
            for artifact in model.artifacts:
                self.artifact_combo.addItem(artifact.role, artifact)
            state = "Sẵn sàng" if model.available else "Thiếu trọng số"
            targets = ", ".join(_class_name(item) for item in model.target_classes)
            self.model_status.setText(f"{state} · {targets}")
        else:
            self.model_status.setText("Không có mô hình phù hợp")
        self.artifact_combo.blockSignals(False)
        self._update_summary()
        self._update_run_state()

    def _update_summary(self, *_args: object) -> None:
        self.device_value.setText(self.device_combo.currentText())
        self.tile_value.setText(f"{self.tile_size.value()} px")
        self.overlap_value.setText(f"{self.overlap.value()} px")
        self.threshold_value.setText(f"{self.threshold.value():.2f}")

    def _update_run_state(self) -> None:
        model = self.model_combo.currentData()
        artifact = self.artifact_combo.currentData()
        available = bool(
            isinstance(model, AnalysisModelOption)
            and model.available
            and artifact is not None
        )
        self.run_button.setEnabled(
            not self._busy and self._source_path is not None and available
        )

    def _submit(self) -> None:
        model = self.model_combo.currentData()
        artifact = self.artifact_combo.currentData()
        if (
            self._source_path is None
            or not isinstance(model, AnalysisModelOption)
            or artifact is None
        ):
            return
        self.testRequested.emit(
            ModelTestRequest(
                source_path=self._source_path,
                model_id=model.model_id,
                artifact_role=artifact.role,
                device=self.device_combo.currentData(),
                tile_size=self.tile_size.value(),
                overlap=self.overlap.value(),
                weed_threshold=self.threshold.value(),
            )
        )


class _ModelTestSettingsDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Thiết lập kiểm tra")
        self.setMinimumWidth(390)
        self.artifact_combo = QComboBox()
        self.device_combo = QComboBox()
        self.device_combo.addItem("Tự động", "auto")
        self.device_combo.addItem("CPU", "cpu")
        self.device_combo.addItem("Apple Silicon", "mps")
        self.device_combo.addItem("NVIDIA CUDA", "cuda")
        self.tile_size = QSpinBox()
        self.tile_size.setRange(128, 2048)
        self.tile_size.setSingleStep(64)
        self.tile_size.setValue(640)
        self.overlap = QSpinBox()
        self.overlap.setRange(0, 512)
        self.overlap.setValue(64)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.05, 0.95)
        self.threshold.setSingleStep(0.05)
        self.threshold.setValue(0.5)
        form = QFormLayout(self)
        form.setContentsMargins(22, 18, 22, 18)
        form.setSpacing(10)
        form.addRow("Trọng số", self.artifact_combo)
        form.addRow("Thiết bị", self.device_combo)
        form.addRow("Kích thước ô", self.tile_size)
        form.addRow("Chồng phủ", self.overlap)
        form.addRow("Ngưỡng cỏ dại", self.threshold)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setText("Đóng")
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


def _model_name(model: AnalysisModelOption) -> str:
    return display_model_name(model.model_id)


def _class_name(value: str) -> str:
    return {
        "crop": "ngô",
        "weed": "cỏ dại",
        "maize2": "ngô 2 lá",
        "maize4": "ngô 4 lá",
        "maize6": "ngô 6 lá",
    }.get(value, value)
