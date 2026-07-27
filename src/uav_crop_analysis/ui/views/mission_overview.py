"""Mission overview for flight profile, capture coverage, and recent jobs."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStyle,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application.workspace import MissionDataStatus, MissionOverview
from uav_crop_analysis.ui.models import DATA_STATUS_TEXT, DroneTableModel, JobTableModel
from uav_crop_analysis.ui.views.common import configure_table, divider, stretch_columns


STATUS_OBJECTS = {
    MissionDataStatus.READY: "StatusReady",
    MissionDataStatus.INCOMPLETE: "StatusIncomplete",
    MissionDataStatus.EMPTY: "StatusEmpty",
}


class MissionOverviewPage(QWidget):
    backRequested = Signal()
    dataRequested = Signal(str)
    analysisRequested = Signal(str)
    spatialRequested = Signal(str)
    reportRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageSurface")
        self._mission_id: str | None = None
        self.drone_model = DroneTableModel()
        self.job_model = JobTableModel()

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("OverviewScrollBody")
        root = QVBoxLayout(body)
        root.setContentsMargins(32, 24, 32, 28)
        root.setSpacing(18)

        header = QHBoxLayout()
        self.back_button = QPushButton()
        self.back_button.setObjectName("IconButton")
        self.back_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.back_button.setToolTip("Quay lại danh sách")
        self.back_button.setAccessibleName("Quay lại danh sách")
        self.back_button.clicked.connect(self.backRequested)
        header.addWidget(self.back_button)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title = QLabel("Nhiệm vụ")
        self.title.setObjectName("PageTitle")
        self.identifier = QLabel()
        self.identifier.setObjectName("MutedLabel")
        title_box.addWidget(self.title)
        title_box.addWidget(self.identifier)
        header.addLayout(title_box)
        header.addStretch()
        self.status = QLabel()
        header.addWidget(self.status)
        self.data_button = QPushButton("Dữ liệu")
        self.data_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self.data_button.setToolTip("Mở dữ liệu ảnh và metadata")
        self.data_button.clicked.connect(self._request_data)
        header.addWidget(self.data_button)
        self.spatial_button = QPushButton("Không gian")
        self.spatial_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
        )
        self.spatial_button.setToolTip("Mở orthomosaic và heatmap không gian")
        self.spatial_button.clicked.connect(self._request_spatial)
        header.addWidget(self.spatial_button)
        self.report_button = QPushButton("Báo cáo")
        self.report_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView)
        )
        self.report_button.setToolTip("Mở dashboard và xuất báo cáo nhiệm vụ")
        self.report_button.clicked.connect(self._request_report)
        header.addWidget(self.report_button)
        self.analysis_button = QPushButton("Phân tích")
        self.analysis_button.setObjectName("PrimaryButton")
        self.analysis_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self.analysis_button.setToolTip("Mở cấu hình phân tích cho nhiệm vụ")
        self.analysis_button.clicked.connect(self._request_analysis)
        header.addWidget(self.analysis_button)
        root.addLayout(header)
        root.addWidget(divider())

        self.metrics = QGridLayout()
        self.metrics.setHorizontalSpacing(28)
        self.metric_values: list[QLabel] = []
        for column, label in enumerate(("Ảnh", "GPS ảnh", "Độ cao", "Camera")):
            value_label = QLabel("—")
            value_label.setObjectName("MetricValue")
            label_widget = QLabel(label)
            label_widget.setObjectName("MetricLabel")
            self.metrics.addWidget(value_label, 0, column)
            self.metrics.addWidget(label_widget, 1, column)
            self.metric_values.append(value_label)
            self.metrics.setColumnStretch(column, 1)
        root.addLayout(self.metrics)
        root.addWidget(divider())

        flight_title = QLabel("Cấu hình bay")
        flight_title.setObjectName("SectionTitle")
        root.addWidget(flight_title)
        self.flight_profile = QLabel()
        self.flight_profile.setObjectName("MutedLabel")
        self.flight_profile.setWordWrap(True)
        root.addWidget(self.flight_profile)

        drone_title = QLabel("Dữ liệu theo drone")
        drone_title.setObjectName("SectionTitle")
        root.addWidget(drone_title)
        self.drone_table = QTableView()
        self.drone_table.setModel(self.drone_model)
        self.drone_table.setAccessibleName("Độ phủ dữ liệu theo drone")
        configure_table(self.drone_table, row_height=42)
        stretch_columns(self.drone_table)
        self.drone_table.setFixedHeight(174)
        root.addWidget(self.drone_table)

        job_title = QLabel("Phân tích gần đây")
        job_title.setObjectName("SectionTitle")
        root.addWidget(job_title)
        self.job_table = QTableView()
        self.job_table.setModel(self.job_model)
        self.job_table.setAccessibleName("Các job phân tích gần đây")
        configure_table(self.job_table, row_height=42)
        stretch_columns(self.job_table, 1)
        self.job_table.setMinimumHeight(158)
        self.no_jobs = QLabel("Chưa có job phân tích.")
        self.no_jobs.setObjectName("MutedLabel")
        root.addWidget(self.job_table)
        root.addWidget(self.no_jobs)
        root.addStretch()

        scroll.setWidget(body)
        page_layout.addWidget(scroll)

    def set_overview(self, overview: MissionOverview) -> None:
        self._mission_id = overview.mission.mission_id.value
        self.title.setText(overview.mission.name)
        self.identifier.setText(self._mission_id)
        self.status.setText(DATA_STATUS_TEXT[overview.data_status])
        self.status.setObjectName(STATUS_OBJECTS[overview.data_status])
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.metric_values[0].setText(f"{overview.image_count:,}")
        self.metric_values[1].setText(f"{overview.gps_coverage * 100:.0f}%")
        self.metric_values[2].setText(f"{overview.altitude_coverage * 100:.0f}%")
        self.metric_values[3].setText(str(overview.camera_count))
        profile = overview.mission.flight_profile
        self.flight_profile.setText(
            f"{profile.altitude_m:g} m  ·  Gimbal {profile.gimbal_pitch_deg:g}°  ·  "
            f"Overlap dọc {profile.forward_overlap * 100:.0f}%  ·  "
            f"Overlap ngang {profile.side_overlap * 100:.0f}%  ·  Đứng yên chụp"
        )
        self.drone_model.set_rows(overview.drones)
        self.job_model.set_rows(overview.recent_jobs)
        self.job_table.setVisible(bool(overview.recent_jobs))
        self.no_jobs.setVisible(not overview.recent_jobs)
        self.analysis_button.setEnabled(overview.can_analyze)
        self.data_button.setEnabled(True)
        self.spatial_button.setEnabled(overview.image_count > 0)
        self.report_button.setEnabled(True)
        if overview.can_analyze:
            self.analysis_button.setToolTip("Mở cấu hình phân tích cho nhiệm vụ")
        else:
            self.analysis_button.setToolTip("Nhiệm vụ chưa có ảnh để phân tích")

    def _request_analysis(self) -> None:
        if self._mission_id:
            self.analysisRequested.emit(self._mission_id)

    def _request_data(self) -> None:
        if self._mission_id:
            self.dataRequested.emit(self._mission_id)

    def _request_spatial(self) -> None:
        if self._mission_id:
            self.spatialRequested.emit(self._mission_id)

    def _request_report(self) -> None:
        if self._mission_id:
            self.reportRequested.emit(self._mission_id)
