"""Versioned contextual help widgets for the desktop shell."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis import __version__
from uav_crop_analysis.ui.branding import (
    APP_DISPLAY_NAME,
    HELP_CONTENT_VERSION,
)
from uav_crop_analysis.ui.icons import ICON_ON_DARK, set_button_icon


@dataclass(frozen=True, slots=True)
class HelpContent:
    key: str
    title: str
    body: str
    version: str = HELP_CONTENT_VERSION


HELP_CONTENTS = {
    "missions": HelpContent(
        "missions",
        "Bắt đầu một nhiệm vụ",
        "<ol><li>Chọn <b>Tạo nhiệm vụ</b>, đặt tên và mã nhiệm vụ.</li>"
        "<li>Chọn số drone, camera và cấu hình bay; có thể lưu thành mẫu.</li>"
        "<li>App mở màn <b>Lập đường bay</b> để vẽ vùng và tính đường bay.</li>"
        "<li>Sau chuyến bay, quay lại nhiệm vụ này để nhập media.</li></ol>"
        "Cột Trạng thái cho biết nhiệm vụ đang ở bước nào; bấm một dòng để mở lại nhiệm vụ đó.",
    ),
    "overview": HelpContent(
        "overview",
        "Tổng quan nhiệm vụ",
        "Đây là điểm kiểm tra nhanh của một nhiệm vụ đã chọn. Làm theo thứ tự: "
        "<b>Lập đường bay</b> để tạo đường bay, <b>Dữ liệu</b> để nhập và kiểm tra ảnh, "
        "<b>Xử lý ảnh</b> để chạy semantic/instance, <b>Bản đồ</b> để tạo heatmap, rồi "
        "<b>Báo cáo</b> để xuất kết quả. Không có ảnh thì chưa thể xử lý.",
    ),
    "model_test": HelpContent(
        "model_test",
        "Công cụ kiểm tra mô hình",
        "Màn này độc lập với nhiệm vụ, dùng trước khi bay hoặc trước khi xử lý dữ liệu thật. "
        "Chọn một ảnh/video, chọn mô hình rồi chạy thử. Semantic trả vùng ngô và cỏ dại; "
        "instance chỉ phát hiện từng cây ngô để đếm cây. Kết quả ở đây không được thêm vào mission.",
    ),
    "planning": HelpContent(
        "planning",
        "Lập đường bay",
        "<ol><li>Chọn biểu tượng vẽ, bấm các đỉnh theo ranh giới ruộng rồi bấm lại để kết thúc.</li>"
        "<li>Chọn camera, độ cao và overlap cho khu khảo sát.</li>"
        "<li>Bấm <b>Tính đường bay</b>, kiểm tra các làn và điểm dừng chụp.</li>"
        "<li>Bấm <b>Xuất nhiệm vụ</b> để lấy tệp plan nạp vào phần mềm điều khiển.</li></ol>"
        "Đường nét đứt từ đỉnh cuối giúp dóng điểm tiếp theo. Mọi thay đổi vùng hoặc thông số đều cần tính lại.",
    ),
    "data": HelpContent(
        "data",
        "Nhập và kiểm tra media",
        "Chọn từng drone để xem ảnh đã nhập. Kiểm tra số ảnh, GPS, độ cao và cảnh báo trước "
        "khi xử lý. Nút camera dùng để lưu camera dùng lâu dài và gán nó cho drone của nhiệm vụ. "
        "Kích thước ảnh được đọc từ file, không phải nhập tay.",
    ),
    "analysis": HelpContent(
        "analysis",
        "Xử lý ảnh",
        "Chọn <b>Semantic</b> để phân vùng đồng thời ngô và cỏ dại, đo tỷ lệ/diện tích và tạo "
        "dữ liệu heatmap. Chọn <b>Instance ngô</b> khi cần đếm cây hoặc xem cây còi. Mỗi lần đổi "
        "threshold, tile hay overlap sẽ tạo job mới; chọn job cũ trong hàng đợi để xem hoặc xóa.",
    ),
    "spatial": HelpContent(
        "spatial",
        "Bản đồ và heatmap",
        "Đầu tiên tạo hoặc nhập orthomosaic GeoTIFF để có ảnh ghép mang tọa độ. Sau đó chạy "
        "semantic trên orthomosaic và tạo heatmap cỏ dại. Bấm vùng trên bản đồ để xem toạ độ, "
        "diện tích và tỷ lệ cỏ. NodeODM cần Docker Desktop đang chạy; GreenEye sẽ tự khởi động container.",
    ),
    "report": HelpContent(
        "report",
        "Xuất báo cáo",
        "Kiểm tra nhiệm vụ đã có kết quả semantic và heatmap trước khi xuất. Báo cáo gồm diện tích "
        "ngô-cỏ, số cây instance, camera/GSD, orthomosaic, heatmap và tệp dữ liệu đi kèm. "
        "Bản HTML mở để xem nhanh; JSON/CSV/GeoTIFF phục vụ lưu trữ và sử dụng tiếp.",
    ),
}


class HelpDialog(QDialog):
    """Small non-blocking help dialog with visible content provenance."""

    def __init__(self, content: HelpContent, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HelpDialog")
        self.setModal(False)
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        self.title_label = QLabel()
        self.title_label.setObjectName("PanelTitle")
        layout.addWidget(self.title_label)
        self.body_label = QLabel()
        self.body_label.setWordWrap(True)
        self.body_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.body_label.setMinimumHeight(100)
        layout.addWidget(self.body_label)
        self.version_label = QLabel()
        self.version_label.setObjectName("MutedLabel")
        layout.addWidget(self.version_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Đóng")
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.set_content(content)

    def set_content(self, content: HelpContent) -> None:
        self.setWindowTitle(f"{APP_DISPLAY_NAME} · {content.title}")
        self.title_label.setText(content.title)
        self.body_label.setText(content.body)
        self.version_label.setText(
            f"Nội dung trợ giúp {content.version} · {APP_DISPLAY_NAME} {__version__}"
        )


class InfoButton(QPushButton):
    """Context help command that can adapt to compact or expanded sidebars."""

    def __init__(
        self,
        content_provider: Callable[[], HelpContent],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._content_provider = content_provider
        self._dialog: HelpDialog | None = None
        self.setObjectName("SidebarActionButton")
        self.setAccessibleName("Trợ giúp")
        self.setToolTip("Trợ giúp theo màn hình")
        self.setFixedHeight(44)
        set_button_icon(self, "info", color=ICON_ON_DARK, size=20)
        self.clicked.connect(self.show_help)
        self.set_expanded(False)

    @property
    def dialog(self) -> HelpDialog | None:
        return self._dialog

    def set_expanded(self, expanded: bool) -> None:
        self.setText("Trợ giúp" if expanded else "")
        self.setFixedWidth(200 if expanded else 44)
        self.setProperty("sidebarExpanded", expanded)
        self.style().unpolish(self)
        self.style().polish(self)

    def show_help(self) -> None:
        content = self._content_provider()
        if self._dialog is None:
            self._dialog = HelpDialog(content, self.window())
        else:
            self._dialog.set_content(content)
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
