"""Mission dashboard and portable report export workspace."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyle,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.reporting import MissionReport, ReportExport
from uav_crop_analysis.ui.models import (
    ReportAnalysisTableModel,
    ReportDroneTableModel,
    ReportImageTableModel,
)
from uav_crop_analysis.ui.views.common import configure_table, divider, stretch_columns


class ReportWorkspacePage(QWidget):
    exportRequested = Signal(str)
    openReportRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageSurface")
        self._mission_id: str | None = None
        self._export: ReportExport | None = None
        self.drone_model = ReportDroneTableModel()
        self.image_model = ReportImageTableModel()
        self.analysis_model = ReportAnalysisTableModel()

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        self.title = QLabel("Báo cáo")
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("MutedLabel")
        title_box.addWidget(self.title)
        title_box.addWidget(self.subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.open_button = QPushButton("Mở HTML")
        self.open_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.open_button.clicked.connect(self._open_report)
        self.open_button.setEnabled(False)
        header.addWidget(self.open_button)
        self.export_button = QPushButton("Xuất báo cáo")
        self.export_button.setObjectName("PrimaryButton")
        self.export_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.export_button.clicked.connect(self._export_report)
        header.addWidget(self.export_button)
        root.addLayout(header)

        metrics = QGridLayout()
        self.image_value = _metric_value()
        self.valid_value = _metric_value()
        self.analyzed_value = _metric_value()
        self.weed_value = _metric_value()
        for column, (label, value) in enumerate(
            (
                ("Ảnh", self.image_value),
                ("Ảnh hợp lệ", self.valid_value),
                ("Đã phân tích", self.analyzed_value),
                ("Weed trung bình", self.weed_value),
            )
        ):
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            metrics.addWidget(name, 0, column)
            metrics.addWidget(value, 1, column)
            metrics.setColumnStretch(column, 1)
        root.addLayout(metrics)
        root.addWidget(divider())

        drone_title = QLabel("Tổng hợp theo drone")
        drone_title.setObjectName("SectionTitle")
        root.addWidget(drone_title)
        self.drone_table = QTableView()
        self.drone_table.setModel(self.drone_model)
        self.drone_table.setAccessibleName("Tổng hợp báo cáo theo drone")
        configure_table(self.drone_table, row_height=38)
        stretch_columns(self.drone_table, 0)
        self.drone_table.setFixedHeight(154)
        root.addWidget(self.drone_table)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        tabs = QTabWidget()
        self.image_table = QTableView()
        self.image_table.setModel(self.image_model)
        configure_table(self.image_table, row_height=38)
        stretch_columns(self.image_table, 1)
        tabs.addTab(self.image_table, "Chi tiết ảnh")
        self.analysis_table = QTableView()
        self.analysis_table.setModel(self.analysis_model)
        configure_table(self.analysis_table, row_height=38)
        stretch_columns(self.analysis_table, 2)
        tabs.addTab(self.analysis_table, "Job AI")
        splitter.addWidget(tabs)

        inspector = QWidget()
        inspector.setObjectName("InspectorPanel")
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(18, 14, 18, 14)
        inspector_layout.setSpacing(8)
        camera_title = QLabel("Camera và GSD")
        camera_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(camera_title)
        self.camera_value = QLabel("—")
        self.camera_value.setWordWrap(True)
        inspector_layout.addWidget(self.camera_value)
        spatial_title = QLabel("Sản phẩm không gian")
        spatial_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(spatial_title)
        self.spatial_value = QLabel("—")
        self.spatial_value.setWordWrap(True)
        inspector_layout.addWidget(self.spatial_value)
        self.heatmap_preview = QLabel()
        self.heatmap_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.heatmap_preview.setMinimumHeight(100)
        self.heatmap_preview.setMaximumHeight(180)
        inspector_layout.addWidget(self.heatmap_preview)
        limitations_title = QLabel("Giới hạn kết quả")
        limitations_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(limitations_title)
        self.limitations_value = QLabel("—")
        self.limitations_value.setObjectName("MutedLabel")
        self.limitations_value.setWordWrap(True)
        inspector_layout.addWidget(self.limitations_value)
        inspector_layout.addStretch()
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        inspector_scroll.setMinimumWidth(310)
        inspector_scroll.setMaximumWidth(380)
        inspector_scroll.setWidget(inspector)
        splitter.addWidget(inspector_scroll)
        splitter.setStretchFactor(0, 1)
        root.addWidget(splitter, 1)

        status_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(180)
        self.progress.setVisible(False)
        status_row.addWidget(self.progress)
        self.message = QLabel()
        self.message.setObjectName("MutedLabel")
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        status_row.addWidget(self.message, 1)
        root.addLayout(status_row)

    def set_report(self, report: MissionReport) -> None:
        self._mission_id = report.mission_id
        self.title.setText(report.mission_name)
        self.subtitle.setText(
            f"{report.mission_id} · schema {report.schema_version} · template {report.template_version}"
        )
        self.image_value.setText(f"{report.image_count:,}")
        self.valid_value.setText(f"{report.valid_image_count:,}")
        self.analyzed_value.setText(f"{report.analyzed_image_count:,}")
        self.weed_value.setText(
            f"{report.mean_weed_coverage_percent:.2f}%"
            if report.mean_weed_coverage_percent is not None
            else "—"
        )
        self.drone_model.set_rows(report.drones)
        self.image_model.set_rows(report.images)
        self.analysis_model.set_rows(report.analyses)
        self.camera_value.setText(
            "\n".join(
                f"{item.name}: "
                + (
                    f"{item.estimated_gsd_cm_px:.4f} cm/px ({item.gsd_method})"
                    if item.estimated_gsd_cm_px is not None
                    else "GSD chưa đủ thông số"
                )
                for item in report.cameras
            )
            or "Chưa có camera profile."
        )
        self.spatial_value.setText(
            "\n".join(
                f"{item.kind} · {item.crs or 'không CRS'}" for item in report.spatial_products
            )
            or "Chưa có sản phẩm không gian."
        )
        heatmap = next(
            (
                item.preview_path
                for item in report.spatial_products
                if item.kind == "weed_heatmap" and item.preview_path.is_file()
            ),
            None,
        )
        self._set_heatmap(heatmap)
        self.limitations_value.setText(
            "\n".join(f"• {item}" for item in report.limitations)
        )
        self.export_button.setEnabled(True)

    def set_busy(self, busy: bool) -> None:
        self.export_button.setEnabled(not busy and self._mission_id is not None)
        self.progress.setVisible(busy)
        if busy:
            self.show_message("Đang tạo JSON, CSV, HTML và manifest...")

    def set_export(self, exported: ReportExport) -> None:
        self._export = exported
        self.open_button.setEnabled(True)
        self.show_message(f"Đã xuất: {exported.directory}")

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

    def _set_heatmap(self, path: Path | None) -> None:
        if path is None:
            self.heatmap_preview.clear()
            self.heatmap_preview.setText("Chưa có heatmap.")
            return
        pixmap = QPixmap(str(path))
        self.heatmap_preview.setPixmap(
            pixmap.scaled(
                330,
                170,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _export_report(self) -> None:
        if self._mission_id is not None:
            self.exportRequested.emit(self._mission_id)

    def _open_report(self) -> None:
        if self._export is not None:
            self.openReportRequested.emit(str(self._export.report_html))


def _metric_value() -> QLabel:
    label = QLabel("—")
    label.setObjectName("MetricValue")
    return label
