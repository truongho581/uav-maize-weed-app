"""Qt models for mission, drone coverage, and job tables."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt

from uav_crop_analysis.application.workspace import (
    DroneCoverage,
    JobSummary,
    MissionDataStatus,
    MissionSummary,
    MissionWorkflowStatus,
)
from uav_crop_analysis.application.data_workspace import DataQualityIssue, ImageDataRow
from uav_crop_analysis.jobs.models import AnalysisJob, JobStatus
from uav_crop_analysis.model_names import display_model_name
from uav_crop_analysis.geospatial import (
    SpatialAccuracy,
    SpatialProduct,
    SpatialProductKind,
)
from uav_crop_analysis.reporting import (
    ReportAnalysis,
    ReportDroneSummary,
    ReportImageRecord,
)


MISSION_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 1
STATUS_ROLE = int(Qt.ItemDataRole.UserRole) + 2
IMAGE_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 3
SOURCE_PATH_ROLE = int(Qt.ItemDataRole.UserRole) + 4
JOB_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 5
SPATIAL_PRODUCT_ROLE = int(Qt.ItemDataRole.UserRole) + 6
ModelIndex = QModelIndex | QPersistentModelIndex


DATA_STATUS_TEXT = {
    MissionDataStatus.EMPTY: "Chưa có ảnh",
    MissionDataStatus.INCOMPLETE: "Thiếu dữ liệu",
    MissionDataStatus.READY: "Sẵn sàng",
}

JOB_STATUS_TEXT = {
    JobStatus.QUEUED: "Đang chờ",
    JobStatus.RUNNING: "Đang chạy",
    JobStatus.CANCEL_REQUESTED: "Đang hủy",
    JobStatus.CANCELLED: "Đã hủy",
    JobStatus.FAILED: "Lỗi",
    JobStatus.COMPLETED: "Hoàn thành",
}

WORKFLOW_STATUS_TEXT = {
    MissionWorkflowStatus.CREATED: "Mới tạo · chưa có đường bay",
    MissionWorkflowStatus.PLANNED_NO_MEDIA: "Đã có đường bay · chưa có media",
    MissionWorkflowStatus.MEDIA_NO_PLAN: "Đã có media · chưa có đường bay",
    MissionWorkflowStatus.PLANNED_WITH_MEDIA: "Đã có đường bay và media · chưa xử lý",
    MissionWorkflowStatus.ANALYZED_NO_HEATMAP: "Đã xử lý · chưa có heatmap",
    MissionWorkflowStatus.COMPLETE: "Hoàn tất · đã có heatmap",
}

SPATIAL_KIND_TEXT = {
    SpatialProductKind.PREVIEW_MOSAIC: "Ảnh xem nhanh 3 làn",
    SpatialProductKind.ORTHOMOSAIC: "Ảnh ghép có tọa độ",
    SpatialProductKind.WEED_HEATMAP: "Bản đồ mật độ cỏ dại",
}

SPATIAL_ACCURACY_TEXT = {
    SpatialAccuracy.PREVIEW_ONLY: "Không có tọa độ",
    SpatialAccuracy.GEOREFERENCED: "Đã định vị",
}


class MissionTableModel(QAbstractTableModel):
    HEADERS = ("Nhiệm vụ", "Thời gian", "Ảnh", "GPS", "Drone", "Trạng thái")

    def __init__(self, rows: Sequence[MissionSummary] = ()) -> None:
        super().__init__()
        self._rows = tuple(rows)

    def set_rows(self, rows: Sequence[MissionSummary]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        if (
            role == Qt.ItemDataRole.TextAlignmentRole
            and orientation == Qt.Orientation.Horizontal
            and section in {2, 3, 4}
        ):
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def data(
        self,
        index: ModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        item = self._rows[index.row()]
        if role == MISSION_ID_ROLE:
            return item.mission_id
        if role == STATUS_ROLE:
            return item.workflow_status.value
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in {2, 3, 4}:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            item.name,
            _format_datetime(item.created_at),
            f"{item.image_count:,}",
            _format_percent(item.gps_coverage),
            str(item.drone_count),
            WORKFLOW_STATUS_TEXT[item.workflow_status],
        )
        return values[index.column()]


class DroneTableModel(QAbstractTableModel):
    HEADERS = ("Drone", "Làn", "Ảnh", "GPS ảnh", "Độ cao", "Mẫu hành trình")

    def __init__(self, rows: Sequence[DroneCoverage] = ()) -> None:
        super().__init__()
        self._rows = tuple(rows)

    def set_rows(self, rows: Sequence[DroneCoverage]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: ModelIndex, role: int = 0) -> Any:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        item = self._rows[index.row()]
        values = (
            item.drone_id,
            str(item.lane_index + 1),
            f"{item.image_count:,}",
            _format_percent(item.gps_coverage),
            _format_percent(item.altitude_coverage),
            f"{item.telemetry_count:,}",
        )
        return values[index.column()]


class JobTableModel(QAbstractTableModel):
    HEADERS = ("Tác vụ", "Mô hình", "Trạng thái", "Tiến độ", "Cập nhật")

    def __init__(self, rows: Sequence[JobSummary] = ()) -> None:
        super().__init__()
        self._rows = tuple(rows)

    def set_rows(self, rows: Sequence[JobSummary]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: ModelIndex, role: int = 0) -> Any:
        if not index.isValid():
            return None
        item = self._rows[index.row()]
        if role == Qt.ItemDataRole.ToolTipRole and item.error_message:
            return item.error_message
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            item.job_id,
            display_model_name(item.model_id),
            JOB_STATUS_TEXT[item.status],
            _format_percent(item.progress),
            _format_datetime(item.updated_at),
        )
        return values[index.column()]


class ImageDataTableModel(QAbstractTableModel):
    HEADERS = ("#", "Tệp ảnh", "Thời gian", "Kích thước", "GPS", "Độ cao", "Lệch", "Dữ liệu")

    def __init__(self, rows: Sequence[ImageDataRow] = ()) -> None:
        super().__init__()
        self._rows = tuple(rows)

    def set_rows(self, rows: Sequence[ImageDataRow]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        if (
            role == Qt.ItemDataRole.TextAlignmentRole
            and orientation == Qt.Orientation.Horizontal
            and section in {0, 3, 5, 6}
        ):
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def data(self, index: ModelIndex, role: int = 0) -> Any:
        if not index.isValid():
            return None
        item = self._rows[index.row()]
        if role == IMAGE_ID_ROLE:
            return item.image_id
        if role == SOURCE_PATH_ROLE or role == Qt.ItemDataRole.ToolTipRole:
            return str(item.source_path)
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in {0, 3, 5, 6}:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        gps = (
            f"{item.latitude:.6f}, {item.longitude:.6f}"
            if item.latitude is not None and item.longitude is not None
            else "Thiếu"
        )
        values = (
            str(item.sequence_index + 1),
            item.source_path.name,
            _format_datetime(item.captured_at),
            f"{item.width_px} × {item.height_px}",
            gps,
            f"{item.relative_altitude_m:.2f} m"
            if item.relative_altitude_m is not None
            else "Thiếu",
            f"{item.telemetry_offset_ms} ms"
            if item.telemetry_offset_ms is not None
            else "—",
            "Có lỗi" if item.has_issues else "Hợp lệ",
        )
        return values[index.column()]


class QualityIssueTableModel(QAbstractTableModel):
    HEADERS = ("Mức", "Drone", "Ảnh", "Mã lỗi", "Chi tiết")

    def __init__(self, rows: Sequence[DataQualityIssue] = ()) -> None:
        super().__init__()
        self._rows = tuple(rows)

    def set_rows(self, rows: Sequence[DataQualityIssue]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: ModelIndex, role: int = 0) -> Any:
        if not index.isValid():
            return None
        item = self._rows[index.row()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(item.source_path) if item.source_path else item.message
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            "Lỗi" if item.severity == "error" else "Cảnh báo",
            item.drone_id,
            item.image_id or "—",
            item.code,
            item.message,
        )
        return values[index.column()]


class AnalysisJobTableModel(QAbstractTableModel):
    HEADERS = ("Tác vụ", "Trạng thái", "Cập nhật")

    def __init__(self, rows: Sequence[AnalysisJob] = ()) -> None:
        super().__init__()
        self._rows = tuple(rows)

    def set_rows(self, rows: Sequence[AnalysisJob]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def job_at(self, row: int) -> AnalysisJob | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    @property
    def rows(self) -> tuple[AnalysisJob, ...]:
        return self._rows

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        if (
            role == Qt.ItemDataRole.TextAlignmentRole
            and orientation == Qt.Orientation.Horizontal
            and section == 1
        ):
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def data(self, index: ModelIndex, role: int = 0) -> Any:
        if not index.isValid():
            return None
        item = self._rows[index.row()]
        if role == JOB_ID_ROLE:
            return item.job_id
        if role == Qt.ItemDataRole.ToolTipRole:
            error = f"\nLỗi: {item.error.message}" if item.error else ""
            return (
                f"Tác vụ: {item.job_id}\n"
                f"Mô hình: {display_model_name(item.config.model_id)}{error}"
            )
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 1:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            f"{display_model_name(item.config.model_id)} · {len(item.config.inputs)} ảnh",
            f"{JOB_STATUS_TEXT[item.status]} · {_format_percent(item.progress)}",
            _format_datetime(item.updated_at),
        )
        return values[index.column()]


class SpatialProductTableModel(QAbstractTableModel):
    HEADERS = ("Lớp bản đồ", "Định vị", "Hệ tọa độ", "Kích thước", "GSD", "Tạo lúc")

    def __init__(self, rows: Sequence[SpatialProduct] = ()) -> None:
        super().__init__()
        self._rows = tuple(rows)

    def set_rows(self, rows: Sequence[SpatialProduct]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def product_at(self, row: int) -> SpatialProduct | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: ModelIndex, role: int = 0) -> Any:
        if not index.isValid():
            return None
        product = self._rows[index.row()]
        if role == SPATIAL_PRODUCT_ROLE:
            return product
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(product.path)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        raster = product.raster
        values = (
            SPATIAL_KIND_TEXT[product.kind],
            SPATIAL_ACCURACY_TEXT[product.accuracy],
            raster.crs if raster else "—",
            f"{raster.width} × {raster.height}" if raster else "—",
            f"{raster.resolution[0]:.4g} × {raster.resolution[1]:.4g}" if raster else "—",
            _format_datetime(product.created_at),
        )
        return values[index.column()]


class ReportDroneTableModel(QAbstractTableModel):
    HEADERS = ("Drone", "Làn", "Ảnh", "Hợp lệ", "Có lỗi", "Đã AI", "GPS", "Cỏ dại TB")

    def __init__(self, rows: Sequence[ReportDroneSummary] = ()) -> None:
        super().__init__()
        self._rows = tuple(rows)

    def set_rows(self, rows: Sequence[ReportDroneSummary]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: ModelIndex, role: int = 0) -> Any:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        item = self._rows[index.row()]
        values = (
            item.drone_id,
            str(item.lane_index + 1),
            f"{item.image_count:,}",
            f"{item.valid_image_count:,}",
            f"{item.issue_image_count:,}",
            f"{item.analyzed_image_count:,}",
            _format_percent(item.gps_coverage),
            (
                f"{item.mean_weed_coverage_percent:.2f}%"
                if item.mean_weed_coverage_percent is not None
                else "—"
            ),
        )
        return values[index.column()]


class ReportImageTableModel(QAbstractTableModel):
    HEADERS = ("Drone", "Ảnh", "Thời gian", "Chất lượng", "Cỏ dại", "Cây ngô")

    def __init__(self, rows: Sequence[ReportImageRecord] = ()) -> None:
        super().__init__()
        self._rows = tuple(rows)

    def set_rows(self, rows: Sequence[ReportImageRecord]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: ModelIndex, role: int = 0) -> Any:
        if not index.isValid():
            return None
        item = self._rows[index.row()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return (
                f"{item.source_path}\n"
                f"Mô hình: "
                f"{display_model_name(item.model_id) if item.model_id else '—'} · "
                f"{item.model_version or '—'}\n"
                f"{', '.join(item.issue_codes) or 'hợp lệ'}"
            )
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            item.drone_id,
            item.image_id,
            _format_datetime(item.captured_at),
            {
                "valid": "Hợp lệ",
                "warning": "Cảnh báo",
                "issue": "Có vấn đề",
                "error": "Lỗi",
            }.get(item.quality_status, item.quality_status),
            (
                f"{item.weed_coverage_percent:.2f}%"
                if item.weed_coverage_percent is not None
                else "—"
            ),
            "Chờ trọng số" if item.maize_instance_count is None else str(item.maize_instance_count),
        )
        return values[index.column()]


class ReportAnalysisTableModel(QAbstractTableModel):
    HEADERS = ("Tác vụ", "Trạng thái", "Mô hình", "Phiên bản", "Ảnh", "Ngưỡng")

    def __init__(self, rows: Sequence[ReportAnalysis] = ()) -> None:
        super().__init__()
        self._rows = tuple(rows)

    def set_rows(self, rows: Sequence[ReportAnalysis]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: ModelIndex, role: int = 0) -> Any:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        item = self._rows[index.row()]
        values = (
            item.job_id,
            item.status,
            display_model_name(item.model_id),
            item.model_version or "—",
            str(item.image_count),
            f"{item.weed_threshold:.2f}",
        )
        return values[index.column()]


def _format_percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def _format_datetime(value: datetime) -> str:
    return value.astimezone().strftime("%d/%m/%Y %H:%M")
