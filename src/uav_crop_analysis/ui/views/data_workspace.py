"""Mission data workspace for image and metadata inspection by drone."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTabBar,
    QTabWidget,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application.data_workspace import MissionDataWorkspace
from uav_crop_analysis.domain import CameraProfile
from uav_crop_analysis.ui.icons import (
    ICON_ON_PRIMARY,
    configure_icon_button,
    set_button_icon,
)
from uav_crop_analysis.ui.components import StatusBadgeDelegate
from uav_crop_analysis.ui.models import ImageDataTableModel, QualityIssueTableModel
from uav_crop_analysis.ui.views.common import configure_table, divider, stretch_columns


class DataWorkspacePage(QWidget):
    analysisRequested = Signal(str)
    cameraProfileSaveRequested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageSurface")
        self._data: MissionDataWorkspace | None = None
        self.image_model = ImageDataTableModel()
        self.issue_model = QualityIssueTableModel()
        self.telemetry_model = QStandardItemModel()
        self.telemetry_model.setHorizontalHeaderLabels(
            ("Drone", "Làn", "Ảnh", "Mẫu hành trình", "Lệch TB", "Lệch lớn nhất", "Cảnh báo")
        )
        self._page = 0
        self._page_size = 50

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

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
        self.camera_button = QPushButton()
        configure_icon_button(
            self.camera_button,
            "camera",
            "Khai báo thông số máy ảnh và gán cho drone",
        )
        self.camera_button.clicked.connect(self._edit_camera)
        header.addWidget(self.camera_button)
        self.analysis_button = QPushButton("Xử lý ảnh")
        self.analysis_button.setObjectName("PrimaryButton")
        set_button_icon(self.analysis_button, "play", color=ICON_ON_PRIMARY)
        self.analysis_button.clicked.connect(self._request_analysis)
        header.addWidget(self.analysis_button)
        root.addLayout(header)
        root.addWidget(divider())

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm tên tệp, mã ảnh hoặc tọa độ…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(330)
        self.search.textChanged.connect(self._filter_changed)
        controls.addWidget(self.search)
        self.drone_tabs = QTabBar()
        self.drone_tabs.setObjectName("SegmentedTabs")
        self.drone_tabs.setExpanding(False)
        self.drone_tabs.setDrawBase(False)
        self.drone_tabs.setAccessibleName("Chọn drone")
        self.drone_tabs.currentChanged.connect(self._select_drone)
        controls.addWidget(self.drone_tabs)
        controls.addStretch()
        self.issue_type_filter = QComboBox()
        self.issue_type_filter.setAccessibleName("Lọc loại lỗi dữ liệu")
        self.issue_type_filter.addItem("Mọi loại lỗi", "all")
        self.issue_type_filter.addItem("Lỗi nghiêm trọng", "error")
        self.issue_type_filter.addItem("Cảnh báo", "warning")
        self.issue_type_filter.currentIndexChanged.connect(self._refresh_issues)
        controls.addWidget(self.issue_type_filter)
        self.only_issues = QCheckBox("Chỉ ảnh có lỗi")
        self.only_issues.toggled.connect(self._refresh_images)
        controls.addWidget(self.only_issues)
        root.addLayout(controls)

        self.drone_summary = QLabel()
        self.drone_summary.setObjectName("MutedLabel")
        root.addWidget(self.drone_summary)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        self.workspace_splitter = splitter
        self.image_table = QTableView()
        self.image_table.setModel(self.image_model)
        self.image_table.setAccessibleName("Ảnh và thông tin đi kèm của drone")
        configure_table(self.image_table, row_height=42)
        self.image_table.setItemDelegateForColumn(7, StatusBadgeDelegate(self.image_table))
        stretch_columns(self.image_table, 1)
        image_panel = QWidget()
        image_layout = QVBoxLayout(image_panel)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(6)
        image_layout.addWidget(self.image_table)
        pager = QHBoxLayout()
        self.page_summary = QLabel()
        self.page_summary.setObjectName("MutedLabel")
        pager.addWidget(self.page_summary)
        pager.addStretch()
        self.previous_page = QPushButton()
        configure_icon_button(self.previous_page, "chevron-left", "Trang trước")
        self.previous_page.clicked.connect(lambda: self._change_page(-1))
        pager.addWidget(self.previous_page)
        self.next_page = QPushButton()
        configure_icon_button(self.next_page, "chevron-right", "Trang sau")
        self.next_page.clicked.connect(lambda: self._change_page(1))
        pager.addWidget(self.next_page)
        image_layout.addLayout(pager)
        splitter.addWidget(image_panel)

        lower_tabs = QTabWidget()
        lower_tabs.tabBar().setObjectName("ContentTabs")
        self.lower_tabs = lower_tabs
        self.issues_expanded = True
        self.issues_toggle = QToolButton()
        configure_icon_button(self.issues_toggle, "eye-off", "Thu gọn bảng phía dưới")
        self.issues_toggle.setFixedSize(28, 28)
        self.issues_toggle.clicked.connect(self._toggle_issues)
        lower_tabs.setCornerWidget(self.issues_toggle, Qt.Corner.TopRightCorner)
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
        self.issue_table.setItemDelegateForColumn(0, StatusBadgeDelegate(self.issue_table))
        stretch_columns(self.issue_table, 4)
        issue_layout.addWidget(self.issue_table)
        self.no_issues = QLabel("Không phát hiện vấn đề dữ liệu.")
        self.no_issues.setObjectName("StatusReady")
        issue_layout.addWidget(self.no_issues)
        lower_tabs.addTab(issue_panel, "Cảnh báo")
        telemetry_panel = QWidget()
        telemetry_layout = QVBoxLayout(telemetry_panel)
        telemetry_layout.setContentsMargins(0, 8, 0, 0)
        self.telemetry_table = QTableView()
        self.telemetry_table.setModel(self.telemetry_model)
        self.telemetry_table.setAccessibleName("Tóm tắt hành trình các drone")
        configure_table(self.telemetry_table, row_height=40)
        stretch_columns(self.telemetry_table, 0)
        telemetry_layout.addWidget(self.telemetry_table)
        lower_tabs.addTab(telemetry_panel, "Hành trình")
        splitter.addWidget(lower_tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes((430, 180))
        root.addWidget(splitter, 1)

        self.camera_summary = QLabel()
        self.camera_summary.setObjectName("CameraStatusBar")
        self.camera_summary.setWordWrap(False)
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
        self.issue_type_filter.blockSignals(True)
        while self.issue_type_filter.count() > 3:
            self.issue_type_filter.removeItem(3)
        for code in sorted({issue.code for issue in data.issues}):
            self.issue_type_filter.addItem(_issue_name(code), code)
        self.issue_type_filter.blockSignals(False)
        self._refresh_issues()
        self._refresh_telemetry()
        self.camera_summary.setText(_camera_summary(data))
        self.analysis_button.setEnabled(data.image_count > 0)
        self.camera_button.setEnabled(bool(data.drones))
        self.drone_tabs.setCurrentIndex(0)
        self._select_drone(0)
        self._set_issues_expanded(bool(data.issues) and self.height() >= 720)

    def show_error(self, message: str) -> None:
        self.title.setText("Không thể tải dữ liệu")
        self.subtitle.setText(message)
        self.image_model.set_rows(())
        self.issue_model.set_rows(())
        self.telemetry_model.removeRows(0, self.telemetry_model.rowCount())
        self.analysis_button.setEnabled(False)

    def _select_drone(self, index: int) -> None:
        if self._data is None or not 0 <= index < len(self._data.drones):
            self.image_model.set_rows(())
            return
        drone = self._data.drones[index]
        self.drone_summary.setText(
            f"{len(drone.images):,} ảnh  ·  {drone.telemetry_count:,} mẫu hành trình  ·  "
            f"{drone.issue_count:,} vấn đề"
        )
        self._page = 0
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
        query = self.search.text().strip().casefold()
        if query:
            images = tuple(
                image
                for image in images
                if query
                in " ".join(
                    (
                        image.image_id,
                        image.source_path.name,
                        str(image.source_path),
                        str(image.latitude or ""),
                        str(image.longitude or ""),
                    )
                ).casefold()
            )
        total = len(images)
        page_count = max(1, (total + self._page_size - 1) // self._page_size)
        self._page = min(self._page, page_count - 1)
        start = self._page * self._page_size
        self.image_model.set_rows(images[start : start + self._page_size])
        self.page_summary.setText(
            f"{start + 1 if total else 0}–{min(start + self._page_size, total)} / {total:,} ảnh"
        )
        self.previous_page.setEnabled(self._page > 0)
        self.next_page.setEnabled(self._page + 1 < page_count)

    def _filter_changed(self, *_args: object) -> None:
        self._page = 0
        self._refresh_images()

    def _change_page(self, offset: int) -> None:
        self._page = max(0, self._page + offset)
        self._refresh_images()

    def _refresh_issues(self, *_args: object) -> None:
        if self._data is None:
            self.issue_model.set_rows(())
            return
        selected = self.issue_type_filter.currentData()
        issues = self._data.issues
        if selected in {"error", "warning"}:
            issues = tuple(issue for issue in issues if issue.severity == selected)
        elif isinstance(selected, str) and selected != "all":
            issues = tuple(issue for issue in issues if issue.code == selected)
        self.issue_model.set_rows(issues)
        self.issue_count.setText(str(len(issues)))
        self.issue_table.setVisible(bool(issues))
        self.no_issues.setVisible(not issues)

    def _refresh_telemetry(self) -> None:
        self.telemetry_model.removeRows(0, self.telemetry_model.rowCount())
        if self._data is None:
            return
        for drone in self._data.drones:
            offsets = [
                image.telemetry_offset_ms
                for image in drone.images
                if image.telemetry_offset_ms is not None
            ]
            mean_offset = sum(offsets) / len(offsets) if offsets else None
            maximum = max(offsets) if offsets else None
            values = (
                drone.drone_id,
                str(drone.lane_index + 1),
                f"{len(drone.images):,}",
                f"{drone.telemetry_count:,}",
                f"{mean_offset:.0f} ms" if mean_offset is not None else "—",
                f"{maximum} ms" if maximum is not None else "—",
                f"{drone.issue_count:,}",
            )
            self.telemetry_model.appendRow([QStandardItem(value) for value in values])

    def _toggle_issues(self) -> None:
        self._set_issues_expanded(not self.issues_expanded)

    def _set_issues_expanded(self, expanded: bool) -> None:
        self.issues_expanded = expanded
        self.lower_tabs.setMaximumHeight(240 if expanded else 38)
        self.lower_tabs.setMinimumHeight(120 if expanded else 38)
        set_button_icon(self.issues_toggle, "eye-off" if expanded else "eye")
        self.issues_toggle.setToolTip(
            "Thu gọn bảng phía dưới" if expanded else "Mở bảng cảnh báo và hành trình"
        )

    def _request_analysis(self) -> None:
        if self._data is not None and self._data.image_count:
            self.analysisRequested.emit(self._data.mission.mission_id.value)

    def _edit_camera(self) -> None:
        if self._data is None:
            return
        dialog = _CameraProfileDialog(self._data, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.cameraProfileSaveRequested.emit(dialog.value())


class _CameraProfileDialog(QDialog):
    def __init__(self, data: MissionDataWorkspace, parent: QWidget) -> None:
        super().__init__(parent)
        self._data = data
        self.setWindowTitle("Thông số máy ảnh")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        current = data.cameras[0] if data.cameras else None
        self.profile_id = QLineEdit(current.profile_id if current else "camera-rgb")
        self.name = QLineEdit(current.name if current else "Máy ảnh RGB")
        self.make = QLineEdit(current.make or "" if current else "")
        self.model = QLineEdit(current.model or "" if current else "")
        self._image_width = current.image_width_px if current else None
        self._image_height = current.image_height_px if current else None
        self.focal = _float_field(current.focal_length_mm if current else None, 0.01, 1000.0)
        self.hfov = _float_field(current.horizontal_fov_deg if current else None, 0.01, 179.0)
        self.vfov = _float_field(current.vertical_fov_deg if current else None, 0.01, 179.0)
        self.assignment = QComboBox()
        self.assignment.addItem("Cả 3 drone", tuple(item.drone_id for item in data.drones))
        for item in data.drones:
            self.assignment.addItem(f"Drone {item.lane_index + 1}", (item.drone_id,))
        self.saved_profiles = QComboBox()
        self.saved_profiles.addItem("Tạo hồ sơ mới", None)
        for profile in data.camera_catalog:
            self.saved_profiles.addItem(f"{profile.name} · {profile.profile_id}", profile)
        self.saved_profiles.currentIndexChanged.connect(self._load_saved_profile)
        for label, widget in (
            ("Máy ảnh đã lưu", self.saved_profiles),
            ("Mã hồ sơ", self.profile_id),
            ("Tên", self.name),
            ("Hãng", self.make),
            ("Mẫu máy", self.model),
            ("Tiêu cự (mm)", self.focal),
            ("HFOV (độ)", self.hfov),
            ("VFOV (độ)", self.vfov),
            ("Áp dụng cho", self.assignment),
        ):
            layout.addRow(label, widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_button is not None:
            save_button.setText("Lưu")
        if cancel_button is not None:
            cancel_button.setText("Hủy")
        layout.addRow(buttons)

    def _load_saved_profile(self, _index: int) -> None:
        profile = self.saved_profiles.currentData()
        if not isinstance(profile, CameraProfile):
            return
        self.profile_id.setText(profile.profile_id)
        self.name.setText(profile.name)
        self.make.setText(profile.make or "")
        self.model.setText(profile.model or "")
        self._image_width = profile.image_width_px
        self._image_height = profile.image_height_px
        self.focal.setValue(profile.focal_length_mm or 0.0)
        self.hfov.setValue(profile.horizontal_fov_deg or 0.0)
        self.vfov.setValue(profile.vertical_fov_deg or 0.0)

    def value(self) -> tuple[CameraProfile, tuple[str, ...]]:
        profile = CameraProfile(
            profile_id=self.profile_id.text(),
            name=self.name.text(),
            make=self.make.text() or None,
            model=self.model.text() or None,
            image_width_px=self._image_width,
            image_height_px=self._image_height,
            focal_length_mm=self.focal.value() or None,
            horizontal_fov_deg=self.hfov.value() or None,
            vertical_fov_deg=self.vfov.value() or None,
        )
        return profile, tuple(self.assignment.currentData())


def _float_field(value: float | None, minimum: float, maximum: float) -> QDoubleSpinBox:
    field = QDoubleSpinBox()
    field.setRange(0.0, maximum)
    field.setDecimals(3)
    field.setSpecialValueText("Không rõ")
    field.setValue(value or 0.0)
    return field


def _camera_summary(data: MissionDataWorkspace) -> str:
    if not data.cameras:
        return "Máy ảnh: chưa có hồ sơ máy ảnh."
    values = []
    for camera in data.cameras:
        resolution = (
            f"{camera.image_width_px}×{camera.image_height_px}"
            if camera.image_width_px and camera.image_height_px
            else "chưa rõ độ phân giải"
        )
        focal = f"{camera.focal_length_mm:g} mm" if camera.focal_length_mm else "chưa rõ tiêu cự"
        values.append(f"{camera.name} · {resolution} · {focal}")
    return "Máy ảnh: " + "; ".join(values)


def _issue_name(code: str) -> str:
    return {
        "source_missing": "Thiếu tệp ảnh",
        "missing_gps": "Thiếu GPS",
        "missing_altitude": "Thiếu độ cao",
        "telemetry_skew": "Lệch thời gian hành trình",
    }.get(code, code.replace("_", " "))
