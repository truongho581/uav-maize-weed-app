from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableView
from pytestqt.qtbot import QtBot

from uav_crop_analysis.model_names import display_model_name
from uav_crop_analysis.ui.models import (
    AnalysisJobTableModel,
    ImageDataTableModel,
    MissionTableModel,
)
from uav_crop_analysis.ui.views.common import configure_table


def test_registered_models_use_compact_display_names() -> None:
    assert (
        display_model_name("segformer-b0-v72-maizemask-weedsgalore")
        == "segformer-b0-v72"
    )
    assert display_model_name("yolov8-seg-v72-instance") == "yolov8-seg-v72"
    assert (
        display_model_name("mask-rcnn-r50-fpn-v72-instance")
        == "mask-rcnn-r50-v72"
    )
    assert display_model_name("custom-model") == "custom-model"


def test_table_headers_align_with_their_column_contents(qtbot: QtBot) -> None:
    table = QTableView()
    qtbot.addWidget(table)
    configure_table(table)

    assert table.horizontalHeader().defaultAlignment() & Qt.AlignmentFlag.AlignLeft
    role = int(Qt.ItemDataRole.TextAlignmentRole)
    horizontal = Qt.Orientation.Horizontal
    assert MissionTableModel().headerData(2, horizontal, role) == int(
        Qt.AlignmentFlag.AlignCenter
    )
    assert ImageDataTableModel().headerData(3, horizontal, role) == int(
        Qt.AlignmentFlag.AlignCenter
    )
    assert AnalysisJobTableModel().headerData(1, horizontal, role) == int(
        Qt.AlignmentFlag.AlignCenter
    )
