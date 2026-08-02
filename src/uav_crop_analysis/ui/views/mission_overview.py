"""Mission overview for flight profile, capture coverage, and recent jobs."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application.workspace import MissionDataStatus, MissionOverview
from uav_crop_analysis.ui.icons import ICON_ON_PRIMARY, configure_icon_button
from uav_crop_analysis.ui.components import (
    KpiCard,
    ProgressBarDelegate,
    StatusBadge,
    StatusBadgeDelegate,
)
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
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(16)

        header = QHBoxLayout()
        self.back_button = QPushButton()
        configure_icon_button(
            self.back_button,
            "arrow-left",
            "Quay lại danh sách",
        )
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
        self.status = StatusBadge()
        header.addWidget(self.status)
        self.data_button = QPushButton()
        configure_icon_button(
            self.data_button,
            "images",
            "Mở ảnh và thông tin đi kèm",
        )
        self.data_button.clicked.connect(self._request_data)
        header.addWidget(self.data_button)
        self.spatial_button = QPushButton()
        configure_icon_button(
            self.spatial_button,
            "map",
            "Mở ảnh ghép và bản đồ mật độ cỏ dại",
        )
        self.spatial_button.clicked.connect(self._request_spatial)
        header.addWidget(self.spatial_button)
        self.report_button = QPushButton()
        configure_icon_button(
            self.report_button,
            "file-chart-column",
            "Mở phần tổng hợp và xuất báo cáo nhiệm vụ",
        )
        self.report_button.clicked.connect(self._request_report)
        header.addWidget(self.report_button)
        self.analysis_button = QPushButton()
        configure_icon_button(
            self.analysis_button,
            "scan-search",
            "Mở khu vực xử lý ảnh cho nhiệm vụ",
            color=ICON_ON_PRIMARY,
        )
        self.analysis_button.setObjectName("PrimaryIconButton")
        self.analysis_button.clicked.connect(self._request_analysis)
        header.addWidget(self.analysis_button)
        root.addLayout(header)
        root.addWidget(divider())

        self.metrics = QHBoxLayout()
        self.metrics.setSpacing(12)
        self.metric_values: list[QLabel] = []
        for label in ("Ảnh", "GPS ảnh", "Độ cao", "Máy ảnh"):
            card = KpiCard(label)
            self.metrics.addWidget(card)
            self.metric_values.append(card.value)
        self.metrics.addStretch()
        root.addLayout(self.metrics)

        self.warning_banner = QWidget()
        self.warning_banner.setObjectName("WarningBanner")
        warning_layout = QHBoxLayout(self.warning_banner)
        warning_layout.setContentsMargins(12, 8, 8, 8)
        self.warning_text = QLabel("Một số ảnh thiếu GPS hoặc dữ liệu hành trình.")
        warning_layout.addWidget(self.warning_text, 1)
        self.warning_action = QPushButton("Xem dữ liệu")
        self.warning_action.clicked.connect(self._request_data)
        warning_layout.addWidget(self.warning_action)
        root.addWidget(self.warning_banner)

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

        job_title = QLabel("Xử lý gần đây")
        job_title.setObjectName("SectionTitle")
        root.addWidget(job_title)
        self.job_table = QTableView()
        self.job_table.setModel(self.job_model)
        self.job_table.setAccessibleName("Các tác vụ xử lý gần đây")
        configure_table(self.job_table, row_height=42)
        self.job_table.setItemDelegateForColumn(2, StatusBadgeDelegate(self.job_table))
        self.job_table.setItemDelegateForColumn(3, ProgressBarDelegate(self.job_table))
        stretch_columns(self.job_table, 1)
        self.job_table.setMinimumHeight(158)
        self.no_jobs = QLabel("Chưa có tác vụ xử lý.")
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
        self.status.set_status(DATA_STATUS_TEXT[overview.data_status])
        self.warning_banner.setVisible(overview.data_status is MissionDataStatus.INCOMPLETE)
        self.metric_values[0].setText(f"{overview.image_count:,}")
        self.metric_values[1].setText(f"{overview.gps_coverage * 100:.0f}%")
        self.metric_values[2].setText(f"{overview.altitude_coverage * 100:.0f}%")
        self.metric_values[3].setText(str(overview.camera_count))
        profile = overview.mission.flight_profile
        self.flight_profile.setText(
            f"{profile.altitude_m:g} m  ·  Góc máy {profile.gimbal_pitch_deg:g}°  ·  "
            f"Chồng phủ dọc {profile.forward_overlap * 100:.0f}%  ·  "
            f"Chồng phủ ngang {profile.side_overlap * 100:.0f}%  ·  Đứng yên chụp"
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
            self.analysis_button.setToolTip("Mở khu vực xử lý ảnh cho nhiệm vụ")
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
