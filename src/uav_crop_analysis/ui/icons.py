"""Lucide icon rendering helpers for Qt buttons."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton


ICON_COLOR = "#44524B"
ICON_ON_DARK = "#DDE7E2"
ICON_ON_PRIMARY = "#FFFFFF"
ICON_DISABLED = "#98A19C"
_ICON_ROOT = Path(__file__).resolve().parents[1] / "resources" / "icons"


def lucide_icon(name: str, *, color: str = ICON_COLOR, size: int = 18) -> QIcon:
    """Render a bundled Lucide SVG with a palette-aware stroke color."""
    icon = QIcon()
    icon.addPixmap(_render_icon(name, color, size), QIcon.Mode.Normal)
    icon.addPixmap(_render_icon(name, color, size), QIcon.Mode.Active)
    icon.addPixmap(_render_icon(name, ICON_DISABLED, size), QIcon.Mode.Disabled)
    return icon


def set_button_icon(
    button: QAbstractButton,
    name: str,
    *,
    color: str = ICON_COLOR,
    size: int = 18,
) -> None:
    button.setIcon(lucide_icon(name, color=color, size=size))
    button.setIconSize(QSize(size, size))


def configure_icon_button(
    button: QAbstractButton,
    name: str,
    tooltip: str,
    *,
    color: str = ICON_COLOR,
    size: int = 18,
) -> None:
    """Configure a stable square icon-only command with accessible text."""
    button.setText("")
    button.setObjectName("IconButton")
    button.setFixedSize(36, 36)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    set_button_icon(button, name, color=color, size=size)


@lru_cache(maxsize=128)
def _render_icon(name: str, color: str, size: int) -> QPixmap:
    path = _ICON_ROOT / f"{name}.svg"
    svg = path.read_text(encoding="utf-8").replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixel_size = size * 2
    pixmap = QPixmap(pixel_size, pixel_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, pixel_size, pixel_size))
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap
