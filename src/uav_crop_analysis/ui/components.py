"""Reusable presentation-only widgets for the desktop shell."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.ui.tokens import COLORS


class KpiCard(QFrame):
    """Compact metric card with a stable label/value hierarchy."""

    def __init__(self, label: str, value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("KpiCard")
        self.setMinimumSize(150, 76)
        self.setMaximumHeight(84)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.label = QLabel(label)
        self.label.setObjectName("MetricLabel")
        self.value = QLabel(value)
        self.value.setObjectName("MetricValue")
        layout.addWidget(self.label)
        layout.addWidget(self.value)


class StatusBadge(QLabel):
    """Text badge for an existing status value."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("StatusBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_status(text)

    def set_status(self, text: str, kind: str | None = None) -> None:
        self.setText(text)
        self.setProperty("statusKind", kind or status_kind(text))
        self.style().unpolish(self)
        self.style().polish(self)


class StatusBadgeDelegate(QStyledItemDelegate):
    """Paint status text as a restrained badge without changing table models."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        base = QStyleOptionViewItem(option)
        self.initStyleOption(base, index)
        base.text = ""
        style = base.widget.style() if base.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, base, painter, base.widget)
        if not text:
            return
        foreground, background = status_colors(text)
        painter.save()
        font = QFont(base.font)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width = min(metrics.horizontalAdvance(text) + 16, option.rect.width() - 10)
        badge = QRectF(
            option.rect.x() + 6,
            option.rect.center().y() - 11,
            max(width, 28),
            22,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(badge, 4, 4)
        painter.setPen(QColor(foreground))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, metrics.elidedText(
            text, Qt.TextElideMode.ElideRight, max(8, int(badge.width()) - 12)
        ))
        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        size = super().sizeHint(option, index)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        width = option.fontMetrics.horizontalAdvance(text) + 30
        return QSize(max(size.width(), width), max(40, size.height()))


class ProgressBarDelegate(QStyledItemDelegate):
    """Render an existing percentage value as a compact progress bar."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        base = QStyleOptionViewItem(option)
        self.initStyleOption(base, index)
        base.text = ""
        style = base.widget.style() if base.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, base, painter, base.widget)
        try:
            value = max(0.0, min(100.0, float(text.rstrip("%"))))
        except ValueError:
            value = 0.0
        painter.save()
        track = QRectF(option.rect.x() + 8, option.rect.center().y() - 3, option.rect.width() - 48, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["surface_alt"]))
        painter.drawRoundedRect(track, 3, 3)
        fill = QRectF(track)
        fill.setWidth(track.width() * value / 100)
        painter.setBrush(QColor(COLORS["brand"]))
        painter.drawRoundedRect(fill, 3, 3)
        painter.setPen(option.palette.color(QPalette.ColorRole.Text))
        painter.drawText(
            QRectF(option.rect.right() - 38, option.rect.y(), 34, option.rect.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        painter.restore()


def status_kind(text: str) -> str:
    value = text.casefold()
    if any(token in value for token in ("lỗi", "thất bại")):
        return "danger"
    if any(token in value for token in ("cảnh báo", "thiếu", "hủy", "vấn đề")):
        return "warning"
    if any(token in value for token in ("đang chạy", "đang chờ", "đang xử lý")):
        return "info"
    if any(
        token in value
        for token in ("hoàn thành", "hoàn tất", "sẵn sàng", "hợp lệ", "đã định vị")
    ):
        return "success"
    return "neutral"


def status_colors(text: str) -> tuple[str, str]:
    return {
        "success": (COLORS["success"], COLORS["success_soft"]),
        "info": (COLORS["info"], COLORS["info_soft"]),
        "warning": (COLORS["warning"], COLORS["warning_soft"]),
        "danger": (COLORS["danger"], COLORS["danger_soft"]),
        "neutral": (COLORS["muted"], COLORS["surface_alt"]),
    }[status_kind(text)]


def metric_row(label: str, value: QLabel) -> QWidget:
    """Create a stable two-column metadata row."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    name = QLabel(label)
    name.setObjectName("MetricLabel")
    name.setMinimumWidth(88)
    value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    layout.addWidget(name)
    layout.addWidget(value, 1)
    return row
