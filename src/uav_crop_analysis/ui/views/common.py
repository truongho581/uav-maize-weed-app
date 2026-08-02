"""Small layout helpers shared by shell pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QTableView,
    QVBoxLayout,
    QWidget,
)


def divider(*, vertical: bool = False) -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.Shape.VLine if vertical else QFrame.Shape.HLine)
    if vertical:
        line.setFixedWidth(1)
    else:
        line.setFixedHeight(1)
    return line


def configure_table(table: QTableView, *, row_height: int = 44) -> None:
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setShowGrid(False)
    table.setSortingEnabled(False)
    table.setMouseTracking(True)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    header = table.horizontalHeader()
    header.setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    header.setHighlightSections(False)
    header.setStretchLastSection(True)


def message_panel(title: str, detail: str) -> QWidget:
    panel = QFrame()
    panel.setObjectName("MessagePanel")
    panel.setMaximumWidth(520)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(32, 28, 32, 28)
    layout.setSpacing(8)
    title_label = QLabel(title)
    title_label.setObjectName("SectionTitle")
    title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    detail_label = QLabel(detail)
    detail_label.setObjectName("MutedLabel")
    detail_label.setWordWrap(True)
    detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title_label)
    layout.addWidget(detail_label)

    body = QWidget()
    body_layout = QVBoxLayout(body)
    body_layout.addStretch()
    body_layout.addWidget(panel, 0, Qt.AlignmentFlag.AlignCenter)
    body_layout.addStretch()
    return body


def stretch_columns(table: QTableView, stretch_column: int = 0) -> None:
    header = table.horizontalHeader()
    for column in range(header.count()):
        mode = (
            QHeaderView.ResizeMode.Stretch
            if column == stretch_column
            else QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(column, mode)
