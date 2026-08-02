from __future__ import annotations

from typing import Any

from pytestqt.qtbot import QtBot

from uav_crop_analysis.ui.views.mission_create import MissionCreateDialog


class MemorySettings:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def value(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)

    def setValue(self, key: str, value: object) -> None:  # noqa: N802
        self.values[key] = value

    def sync(self) -> None:
        pass


def test_create_dialog_builds_mission_and_restores_template(qtbot: QtBot) -> None:
    settings = MemorySettings()
    dialog = MissionCreateDialog((), settings)  # type: ignore[arg-type]
    qtbot.addWidget(dialog)
    dialog.name.setText("Khảo sát khu A")
    dialog.mission_id.setText("mission-khu-a")
    dialog.drone_count.setValue(2)
    dialog.hfov.setValue(82.0)
    dialog.vfov.setValue(62.0)
    dialog.save_template.setChecked(True)
    dialog.template_name.setText("Tổ hợp 2 drone")

    dialog._accept()  # noqa: SLF001

    draft = dialog.value()
    assert draft.mission_id == "mission-khu-a"
    assert draft.drone_ids == ("drone-01", "drone-02")
    assert draft.camera_profile is not None
    assert draft.camera_profile.horizontal_fov_deg == 82.0

    restored = MissionCreateDialog((), settings)  # type: ignore[arg-type]
    qtbot.addWidget(restored)
    assert restored.template_combo.count() == 2
    restored.template_combo.setCurrentIndex(1)
    assert restored.drone_count.value() == 2
    assert restored.hfov.value() == 82.0
