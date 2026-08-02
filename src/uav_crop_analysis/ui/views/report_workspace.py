"""Mission dashboard and portable report export workspace."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.reporting import MissionReport, ReportExport
from uav_crop_analysis.ui.icons import (
    ICON_ON_PRIMARY,
    configure_icon_button,
    set_button_icon,
)
from uav_crop_analysis.ui.components import KpiCard, StatusBadgeDelegate
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
        self._orthomosaic_path: Path | None = None
        self._heatmap_path: Path | None = None
        self.drone_model = ReportDroneTableModel()
        self.image_model = ReportImageTableModel()
        self.analysis_model = ReportAnalysisTableModel()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
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
        self.inspector_toggle = QPushButton()
        configure_icon_button(
            self.inspector_toggle,
            "eye-off",
            "Thu gọn thông tin báo cáo",
        )
        self.inspector_toggle.clicked.connect(self._toggle_inspector)
        header.addWidget(self.inspector_toggle)
        self.open_button = QPushButton()
        configure_icon_button(
            self.open_button,
            "external-link",
            "Mở báo cáo HTML đã xuất",
        )
        self.open_button.clicked.connect(self._open_report)
        self.open_button.setEnabled(False)
        header.addWidget(self.open_button)
        self.export_button = QPushButton("Xuất báo cáo")
        self.export_button.setObjectName("PrimaryButton")
        set_button_icon(self.export_button, "download", color=ICON_ON_PRIMARY)
        self.export_button.clicked.connect(self._export_report)
        header.addWidget(self.export_button)
        root.addLayout(header)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        cards = [
            KpiCard("Ảnh"),
            KpiCard("Ảnh hợp lệ"),
            KpiCard("Đã phân tích"),
            KpiCard("Ngô trung bình"),
            KpiCard("Cỏ dại trung bình"),
        ]
        (
            self.image_value,
            self.valid_value,
            self.analyzed_value,
            self.crop_value,
            self.weed_value,
        ) = (card.value for card in cards)
        for card in cards:
            metrics.addWidget(card)
        metrics.addStretch()
        root.addLayout(metrics)

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

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        tabs = QTabWidget()
        tabs.tabBar().setObjectName("ContentTabs")
        self.image_table = QTableView()
        self.image_table.setModel(self.image_model)
        configure_table(self.image_table, row_height=38)
        self.image_table.setItemDelegateForColumn(3, StatusBadgeDelegate(self.image_table))
        stretch_columns(self.image_table, 1)
        tabs.addTab(self.image_table, "Chi tiết ảnh")
        self.analysis_table = QTableView()
        self.analysis_table.setModel(self.analysis_model)
        configure_table(self.analysis_table, row_height=38)
        stretch_columns(self.analysis_table, 2)
        self.analysis_table.setItemDelegateForColumn(1, StatusBadgeDelegate(self.analysis_table))
        tabs.addTab(self.analysis_table, "Tác vụ xử lý")
        self.splitter.addWidget(tabs)

        inspector = QWidget()
        inspector.setObjectName("InspectorPanel")
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(12, 12, 12, 12)
        inspector_layout.setSpacing(10)
        inspector_title = QLabel("Thông tin báo cáo")
        inspector_title.setObjectName("PanelTitle")
        inspector_layout.addWidget(inspector_title)

        camera_title = QLabel("Máy ảnh và GSD")
        camera_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(camera_title)
        self.camera_value = QLabel("—")
        self.camera_value.setWordWrap(True)
        inspector_layout.addWidget(self.camera_value)
        inspector_layout.addWidget(divider())

        spatial_title = QLabel("Bản đồ")
        spatial_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(spatial_title)
        self.spatial_value = QLabel("—")
        self.spatial_value.setWordWrap(True)
        inspector_layout.addWidget(self.spatial_value)
        map_pair = QHBoxLayout()
        map_pair.setSpacing(8)
        self.orthomosaic_preview = self._map_preview_panel(
            map_pair,
            "Ảnh ghép GeoTIFF",
        )
        self.heatmap_preview = self._map_preview_panel(
            map_pair,
            "Heatmap cỏ dại",
        )
        inspector_layout.addLayout(map_pair)
        inspector_layout.addWidget(divider())

        limitations_title = QLabel("Giới hạn kết quả")
        limitations_title.setObjectName("SectionTitle")
        inspector_layout.addWidget(limitations_title)
        self.limitations_value = QLabel("—")
        self.limitations_value.setObjectName("MutedLabel")
        self.limitations_value.setWordWrap(True)
        inspector_layout.addWidget(self.limitations_value)
        inspector_layout.addStretch()
        self.inspector_scroll = QScrollArea()
        self.inspector_scroll.setObjectName("ReportInspectorScroll")
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.inspector_scroll.setMinimumWidth(320)
        self.inspector_scroll.setMaximumWidth(380)
        self.inspector_scroll.setWidget(inspector)
        self.splitter.addWidget(self.inspector_scroll)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setSizes((860, 360))
        root.addWidget(self.splitter, 1)
        self.inspector_expanded = True
        self._compact_width = False

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
            f"{report.mission_id} · định dạng {report.schema_version} · mẫu {report.template_version}"
        )
        self.image_value.setText(f"{report.image_count:,}")
        self.valid_value.setText(f"{report.valid_image_count:,}")
        self.analyzed_value.setText(f"{report.analyzed_image_count:,}")
        self.crop_value.setText(
            f"{report.mean_crop_coverage_percent:.2f}%".replace(".", ",")
            if report.mean_crop_coverage_percent is not None
            else "—"
        )
        self.weed_value.setText(
            f"{report.mean_weed_coverage_percent:.2f}%".replace(".", ",")
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
                    f"{item.estimated_gsd_cm_px:.4f} cm/px"
                    if item.estimated_gsd_cm_px is not None
                    else "GSD chưa đủ thông số"
                )
                for item in report.cameras
            )
            or "Chưa có hồ sơ máy ảnh."
        )
        self.spatial_value.setText(
            "\n".join(
                f"{_spatial_kind_text(item.kind)} · {item.crs or 'không có hệ tọa độ'}"
                for item in report.spatial_products
            )
            or "Chưa có bản đồ."
        )
        heatmap = next(
            (
                item
                for item in report.spatial_products
                if item.kind == "weed_heatmap" and item.preview_path.is_file()
            ),
            None,
        )
        orthomosaic = next(
            (
                item
                for item in report.spatial_products
                if item.kind == "orthomosaic"
                and item.preview_path.is_file()
                and (heatmap is None or item.product_id == heatmap.source_product_id)
            ),
            None,
        )
        self._set_map_pair(
            orthomosaic.preview_path if orthomosaic is not None else None,
            heatmap.preview_path if heatmap is not None else None,
        )
        self.limitations_value.setText(
            "\n".join(f"• {item}" for item in report.limitations)
        )
        self.export_button.setEnabled(True)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = event.size().width() < 1130
        if compact != self._compact_width:
            self._compact_width = compact
            self._set_inspector_expanded(not compact)
        self._refresh_map_previews()

    def _toggle_inspector(self) -> None:
        self._set_inspector_expanded(not self.inspector_expanded)

    def _set_inspector_expanded(self, expanded: bool) -> None:
        self.inspector_expanded = expanded
        self.inspector_scroll.setVisible(expanded)
        set_button_icon(self.inspector_toggle, "eye-off" if expanded else "eye")
        self.inspector_toggle.setToolTip(
            "Thu gọn thông tin báo cáo" if expanded else "Mở thông tin báo cáo"
        )

    def set_busy(self, busy: bool) -> None:
        self.export_button.setEnabled(not busy and self._mission_id is not None)
        self.progress.setVisible(busy)
        if busy:
            self.show_message("Đang tạo các tệp dữ liệu và báo cáo HTML...")

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

    @staticmethod
    def _map_preview_panel(layout: QHBoxLayout, title: str) -> QLabel:
        panel = QVBoxLayout()
        panel.setSpacing(5)
        heading = QLabel(title)
        heading.setObjectName("MutedLabel")
        preview = QLabel()
        preview.setObjectName("ReportMapPreview")
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Expanding,
        )
        preview.setMinimumHeight(118)
        preview.setMaximumHeight(190)
        panel.addWidget(heading)
        panel.addWidget(preview, 1)
        layout.addLayout(panel, 1)
        return preview

    def _set_map_pair(
        self,
        orthomosaic_path: Path | None,
        heatmap_path: Path | None,
    ) -> None:
        self._orthomosaic_path = orthomosaic_path
        self._heatmap_path = heatmap_path
        self._refresh_map_previews()

    def _refresh_map_previews(self) -> None:
        self._set_map_preview(
            self.orthomosaic_preview,
            self._orthomosaic_path,
            "Chưa có ảnh ghép.",
        )
        self._set_map_preview(
            self.heatmap_preview,
            self._heatmap_path,
            "Chưa có heatmap.",
        )

    @staticmethod
    def _set_map_preview(label: QLabel, path: Path | None, empty_text: str) -> None:
        if path is None:
            label.clear()
            label.setText(empty_text)
            return
        width = max(label.width() - 4, 120)
        height = max(label.height() - 4, 110)
        label.setPixmap(
            QPixmap(str(path)).scaled(
                width,
                height,
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


def _spatial_kind_text(kind: str) -> str:
    return {
        "preview_mosaic": "Ảnh xem nhanh 3 làn",
        "orthomosaic": "Ảnh ghép có tọa độ",
        "weed_heatmap": "Bản đồ mật độ cỏ dại",
    }.get(kind, kind)
