"""Mission data workspace for three-drone image and metadata inspection."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QStyle,
    QTabBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application.data_workspace import MissionDataWorkspace
from uav_crop_analysis.ui.models import ImageDataTableModel, QualityIssueTableModel
from uav_crop_analysis.ui.views.common import configure_table, divider, stretch_columns


class DataWorkspacePage(QWidget):
    analysisRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageSurface")
        self._data: MissionDataWorkspace | None = None
        self.image_model = ImageDataTableModel()
        self.issue_model = QualityIssueTableModel()

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title = QLabel("Dữ liệu nhiệm vụ")
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("MutedLabel")
        title_box.addWidget(self.title)
        title_box.addWidget(self.subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.analysis_button = QPushButton("Phân tích")
        self.analysis_button.setObjectName("PrimaryButton")
        self.analysis_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self.analysis_button.clicked.connect(self._request_analysis)
        header.addWidget(self.analysis_button)
        root.addLayout(header)
        root.addWidget(divider())

        controls = QHBoxLayout()
        self.drone_tabs = QTabBar()
        self.drone_tabs.setExpanding(False)
        self.drone_tabs.setDrawBase(False)
        self.drone_tabs.setAccessibleName("Chọn drone")
        self.drone_tabs.currentChanged.connect(self._select_drone)
        controls.addWidget(self.drone_tabs)
        controls.addStretch()
        self.only_issues = QCheckBox("Chỉ ảnh có lỗi")
        self.only_issues.toggled.connect(self._refresh_images)
        controls.addWidget(self.only_issues)
        root.addLayout(controls)

        self.drone_summary = QLabel()
        self.drone_summary.setObjectName("MutedLabel")
        root.addWidget(self.drone_summary)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.image_table = QTableView()
        self.image_table.setModel(self.image_model)
        self.image_table.setAccessibleName("Ảnh và metadata của drone")
        configure_table(self.image_table, row_height=42)
        stretch_columns(self.image_table, 1)
        splitter.addWidget(self.image_table)

        issue_panel = QWidget()
        issue_layout = QVBoxLayout(issue_panel)
        issue_layout.setContentsMargins(0, 8, 0, 0)
        issue_layout.setSpacing(8)
        issue_header = QHBoxLayout()
        issue_title = QLabel("Vấn đề dữ liệu")
        issue_title.setObjectName("SectionTitle")
        self.issue_count = QLabel()
        self.issue_count.setObjectName("MutedLabel")
        issue_header.addWidget(issue_title)
        issue_header.addWidget(self.issue_count)
        issue_header.addStretch()
        issue_layout.addLayout(issue_header)
        self.issue_table = QTableView()
        self.issue_table.setModel(self.issue_model)
        self.issue_table.setAccessibleName("Các vấn đề chất lượng dữ liệu")
        configure_table(self.issue_table, row_height=40)
        stretch_columns(self.issue_table, 4)
        issue_layout.addWidget(self.issue_table)
        self.no_issues = QLabel("Không phát hiện vấn đề dữ liệu.")
        self.no_issues.setObjectName("StatusReady")
        issue_layout.addWidget(self.no_issues)
        splitter.addWidget(issue_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        self.camera_summary = QLabel()
        self.camera_summary.setObjectName("MutedLabel")
        self.camera_summary.setWordWrap(True)
        root.addWidget(self.camera_summary)

    def set_data(self, data: MissionDataWorkspace) -> None:
        self._data = data
        self.title.setText(data.mission.name)
        self.subtitle.setText(f"{data.mission.mission_id.value}  ·  {data.image_count:,} ảnh")
        self.drone_tabs.blockSignals(True)
        while self.drone_tabs.count():
            self.drone_tabs.removeTab(0)
        for drone in data.drones:
            self.drone_tabs.addTab(f"Drone {drone.lane_index + 1}  ·  {drone.drone_id}")
        self.drone_tabs.blockSignals(False)
        self.issue_model.set_rows(data.issues)
        self.issue_count.setText(f"{len(data.issues)}")
        self.issue_table.setVisible(bool(data.issues))
        self.no_issues.setVisible(not data.issues)
        self.camera_summary.setText(_camera_summary(data))
        self.analysis_button.setEnabled(data.image_count > 0)
        self.drone_tabs.setCurrentIndex(0)
        self._select_drone(0)

    def show_error(self, message: str) -> None:
        self.title.setText("Không thể tải dữ liệu")
        self.subtitle.setText(message)
        self.image_model.set_rows(())
        self.issue_model.set_rows(())
        self.analysis_button.setEnabled(False)

    def _select_drone(self, index: int) -> None:
        if self._data is None or not 0 <= index < len(self._data.drones):
            self.image_model.set_rows(())
            return
        drone = self._data.drones[index]
        self.drone_summary.setText(
            f"{len(drone.images):,} ảnh  ·  {drone.telemetry_count:,} telemetry  ·  "
            f"{drone.issue_count:,} vấn đề"
        )
        self._refresh_images()

    def _refresh_images(self) -> None:
        if self._data is None:
            self.image_model.set_rows(())
            return
        index = self.drone_tabs.currentIndex()
        if not 0 <= index < len(self._data.drones):
            return
        images = self._data.drones[index].images
        if self.only_issues.isChecked():
            images = tuple(image for image in images if image.has_issues)
        self.image_model.set_rows(images)

    def _request_analysis(self) -> None:
        if self._data is not None and self._data.image_count:
            self.analysisRequested.emit(self._data.mission.mission_id.value)


def _camera_summary(data: MissionDataWorkspace) -> str:
    if not data.cameras:
        return "Camera: chưa có profile camera."
    values = []
    for camera in data.cameras:
        resolution = (
            f"{camera.image_width_px}×{camera.image_height_px}"
            if camera.image_width_px and camera.image_height_px
            else "chưa rõ độ phân giải"
        )
        focal = f"{camera.focal_length_mm:g} mm" if camera.focal_length_mm else "chưa rõ tiêu cự"
        values.append(f"{camera.name} · {resolution} · {focal}")
    return "Camera: " + "; ".join(values)
