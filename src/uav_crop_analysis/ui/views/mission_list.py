"""Mission list with explicit empty, error, and data states."""

from __future__ import annotations

from PySide6.QtCore import QSettings, QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application.workspace import MissionSummary
from uav_crop_analysis.domain import CameraProfile
from uav_crop_analysis.ui.icons import configure_icon_button, set_button_icon
from uav_crop_analysis.ui.components import StatusBadgeDelegate
from uav_crop_analysis.ui.icons import ICON_ON_PRIMARY
from uav_crop_analysis.ui.models import MISSION_ID_ROLE, MissionTableModel
from uav_crop_analysis.ui.views.common import configure_table, message_panel, stretch_columns
from uav_crop_analysis.ui.views.mission_create import MissionCreateDialog


class MissionListPage(QWidget):
    missionSelected = Signal(str)
    createRequested = Signal(object)
    refreshRequested = Signal()
    importRequested = Signal()

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self._settings = settings if settings is not None else QSettings()
        self._camera_profiles: tuple[CameraProfile, ...] = ()
        self.setObjectName("PageSurface")
        self.model = MissionTableModel()
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Nhiệm vụ")
        title.setObjectName("PageTitle")
        description = QLabel("Tạo đường bay, nhập media và theo dõi kết quả khảo sát")
        description.setObjectName("MutedLabel")
        title_box.addWidget(title)
        title_box.addWidget(description)
        header.addLayout(title_box)
        header.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm nhiệm vụ")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(320)
        self.search.setMaximumWidth(460)
        self.search.setAccessibleName("Tìm nhiệm vụ")
        self.search.textChanged.connect(self.proxy_model.setFilterFixedString)
        header.addWidget(self.search)
        self.create_button = QPushButton("Tạo nhiệm vụ")
        self.create_button.setObjectName("PrimaryButton")
        set_button_icon(self.create_button, "square-dashed", color=ICON_ON_PRIMARY)
        self.create_button.clicked.connect(self.open_create_dialog)
        header.addWidget(self.create_button)
        self.import_button = QPushButton("Nhập nhiệm vụ")
        set_button_icon(self.import_button, "file-up")
        self.import_button.setToolTip("Nhập dữ liệu từ tệp mission.json")
        self.import_button.clicked.connect(self.importRequested)
        header.addWidget(self.import_button)
        self.refresh_button = QPushButton()
        configure_icon_button(
            self.refresh_button,
            "refresh-cw",
            "Làm mới danh sách",
        )
        self.refresh_button.clicked.connect(self.refreshRequested)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        self.stack = QStackedWidget()
        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setAccessibleName("Danh sách nhiệm vụ")
        configure_table(self.table, row_height=42)
        self.table.setItemDelegateForColumn(5, StatusBadgeDelegate(self.table))
        stretch_columns(self.table)
        self.table.horizontalHeader().setSectionResizeMode(
            5,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.clicked.connect(self._emit_selected)
        self.table.doubleClicked.connect(self._emit_selected)
        self.empty_state = message_panel(
            "Chưa có nhiệm vụ",
            "Tạo nhiệm vụ đầu tiên để lập đường bay trước khi thu thập media.",
        )
        self.error_state = message_panel(
            "Không thể tải dữ liệu",
            "Kiểm tra cơ sở dữ liệu rồi thử làm mới.",
        )
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.error_state)
        root.addWidget(self.stack)
        root.addStretch(1)

    def set_missions(self, missions: tuple[MissionSummary, ...]) -> None:
        self.model.set_rows(missions)
        self.stack.setCurrentWidget(self.table if missions else self.empty_state)
        self.stack.setMaximumHeight(
            min(520, 44 + max(1, len(missions)) * 42) if missions else 260
        )
        if missions:
            self.table.selectRow(0)

    def set_camera_profiles(self, profiles: tuple[CameraProfile, ...]) -> None:
        self._camera_profiles = profiles

    def show_error(self) -> None:
        self.stack.setCurrentWidget(self.error_state)

    def set_import_busy(self, busy: bool) -> None:
        self.import_button.setEnabled(not busy)
        self.import_button.setText("Đang nhập..." if busy else "Nhập nhiệm vụ")

    def focus_search(self) -> None:
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    def _emit_selected(self, index: object) -> None:
        if not hasattr(index, "data"):
            return
        mission_id = index.data(MISSION_ID_ROLE)
        if mission_id:
            self.missionSelected.emit(str(mission_id))

    def open_create_dialog(self) -> None:
        dialog = MissionCreateDialog(
            self._camera_profiles,
            self._settings,
            self,
        )
        if dialog.exec() == MissionCreateDialog.DialogCode.Accepted:
            self.createRequested.emit(dialog.value())
