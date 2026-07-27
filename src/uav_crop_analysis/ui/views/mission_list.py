"""Mission list with explicit empty, error, and data states."""

from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QStyle,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.application.workspace import MissionSummary
from uav_crop_analysis.ui.models import MISSION_ID_ROLE, MissionTableModel
from uav_crop_analysis.ui.views.common import configure_table, message_panel, stretch_columns


class MissionListPage(QWidget):
    missionSelected = Signal(str)
    refreshRequested = Signal()
    importRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageSurface")
        self.model = MissionTableModel()
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("Nhiệm vụ")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm nhiệm vụ")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        self.search.setAccessibleName("Tìm nhiệm vụ")
        self.search.textChanged.connect(self.proxy_model.setFilterFixedString)
        header.addWidget(self.search)
        self.import_button = QPushButton("Nhập mission")
        self.import_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.import_button.setToolTip("Nhập dữ liệu từ mission.json")
        self.import_button.clicked.connect(self.importRequested)
        header.addWidget(self.import_button)
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("IconButton")
        self.refresh_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.refresh_button.setToolTip("Làm mới danh sách")
        self.refresh_button.setAccessibleName("Làm mới danh sách")
        self.refresh_button.clicked.connect(self.refreshRequested)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        self.stack = QStackedWidget()
        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setAccessibleName("Danh sách nhiệm vụ")
        configure_table(self.table, row_height=48)
        stretch_columns(self.table)
        self.table.clicked.connect(self._emit_selected)
        self.table.doubleClicked.connect(self._emit_selected)
        self.empty_state = message_panel(
            "Chưa có nhiệm vụ",
            "Danh sách sẽ hiển thị sau khi dữ liệu bay được nhập.",
        )
        self.error_state = message_panel(
            "Không thể tải dữ liệu",
            "Kiểm tra cơ sở dữ liệu rồi thử làm mới.",
        )
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.error_state)
        root.addWidget(self.stack, 1)

    def set_missions(self, missions: tuple[MissionSummary, ...]) -> None:
        self.model.set_rows(missions)
        self.stack.setCurrentWidget(self.table if missions else self.empty_state)
        if missions:
            self.table.selectRow(0)

    def show_error(self) -> None:
        self.stack.setCurrentWidget(self.error_state)

    def set_import_busy(self, busy: bool) -> None:
        self.import_button.setEnabled(not busy)
        self.import_button.setText("Đang nhập..." if busy else "Nhập mission")

    def focus_search(self) -> None:
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    def _emit_selected(self, index: object) -> None:
        if not hasattr(index, "data"):
            return
        mission_id = index.data(MISSION_ID_ROLE)
        if mission_id:
            self.missionSelected.emit(str(mission_id))
