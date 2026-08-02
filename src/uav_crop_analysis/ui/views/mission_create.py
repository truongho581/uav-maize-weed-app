"""Create-mission dialog and persistent reusable setup templates."""

from __future__ import annotations

from datetime import datetime
import json
import re
import unicodedata

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from uav_crop_analysis.domain import CameraProfile, FlightProfile
from uav_crop_analysis.ui.viewmodels import MissionCreateDraft


_TEMPLATE_KEY = "missions/setup_templates"
_NEW_CAMERA = "__new_camera__"


class MissionCreateDialog(QDialog):
    def __init__(
        self,
        camera_profiles: tuple[CameraProfile, ...],
        settings: QSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._camera_profiles = camera_profiles
        self._templates = _load_templates(settings)
        self.setWindowTitle("Tạo nhiệm vụ khảo sát")
        self.setMinimumWidth(520)
        self.resize(560, 700)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(0, 0, 6, 0)
        content.setSpacing(12)

        template_form = QFormLayout()
        self.template_combo = QComboBox()
        self.template_combo.addItem("Cấu hình mới", None)
        for value in self._templates:
            self.template_combo.addItem(str(value.get("template_name", "Mẫu")), value)
        self.template_combo.currentIndexChanged.connect(self._apply_template)
        template_form.addRow("Mẫu cấu hình", self.template_combo)
        content.addLayout(template_form)

        mission_group = QGroupBox("Thông tin nhiệm vụ")
        mission_form = QFormLayout(mission_group)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Ví dụ: Khảo sát ngô khu A")
        self.name.textEdited.connect(self._suggest_id)
        self.mission_id = QLineEdit()
        self.mission_id.setPlaceholderText("Mã duy nhất của nhiệm vụ")
        mission_form.addRow("Tên nhiệm vụ", self.name)
        mission_form.addRow("Mã nhiệm vụ", self.mission_id)
        content.addWidget(mission_group)

        setup_group = QGroupBox("Tổ hợp và cấu hình bay")
        setup_form = QFormLayout(setup_group)
        self.drone_count = QSpinBox()
        self.drone_count.setRange(1, 3)
        self.drone_count.setValue(3)
        self.drone_count.valueChanged.connect(self._update_drone_fields)
        self.drone_fields = tuple(
            QLineEdit(f"drone-{index:02d}") for index in range(1, 4)
        )
        self.altitude = _number_field(10.0, 20.0, 10.0, " m")
        self.forward_overlap = _number_field(0.0, 95.0, 75.0, "%", decimals=0)
        self.side_overlap = _number_field(0.0, 95.0, 65.0, "%", decimals=0)
        gimbal = QLabel("-90° · thẳng đứng")
        gimbal.setObjectName("MutedLabel")
        setup_form.addRow("Số drone", self.drone_count)
        for index, field in enumerate(self.drone_fields, start=1):
            setup_form.addRow(f"Drone {index}", field)
        setup_form.addRow("Độ cao AGL", self.altitude)
        setup_form.addRow("Chồng ảnh dọc", self.forward_overlap)
        setup_form.addRow("Chồng ảnh ngang", self.side_overlap)
        setup_form.addRow("Góc camera", gimbal)
        content.addWidget(setup_group)

        camera_group = QGroupBox("Máy ảnh")
        camera_form = QFormLayout(camera_group)
        self.camera_combo = QComboBox()
        self.camera_combo.addItem("Tạo hồ sơ máy ảnh mới", _NEW_CAMERA)
        for profile in camera_profiles:
            self.camera_combo.addItem(f"{profile.name} · {profile.profile_id}", profile)
        self.camera_combo.currentIndexChanged.connect(self._camera_changed)
        self.camera_id = QLineEdit("camera-rgb")
        self.camera_name = QLineEdit("Máy ảnh RGB")
        self.camera_make = QLineEdit()
        self.camera_model = QLineEdit()
        self.focal = _optional_field(0.01, 1000.0, " mm")
        self.hfov = _optional_field(0.01, 179.0, "°")
        self.vfov = _optional_field(0.01, 179.0, "°")
        camera_form.addRow("Hồ sơ", self.camera_combo)
        camera_form.addRow("Mã camera", self.camera_id)
        camera_form.addRow("Tên camera", self.camera_name)
        camera_form.addRow("Hãng", self.camera_make)
        camera_form.addRow("Mẫu máy", self.camera_model)
        camera_form.addRow("Tiêu cự", self.focal)
        camera_form.addRow("HFOV", self.hfov)
        camera_form.addRow("VFOV", self.vfov)
        content.addWidget(camera_group)

        self.save_template = QCheckBox("Lưu cấu hình này thành mẫu")
        self.save_template.toggled.connect(self._template_toggled)
        self.template_name = QLineEdit()
        self.template_name.setPlaceholderText("Tên mẫu cấu hình")
        self.template_name.setVisible(False)
        content.addWidget(self.save_template)
        content.addWidget(self.template_name)
        content.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("Tạo và lập đường bay")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText("Hủy")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._update_drone_fields(3)
        self._camera_changed(0)

    def value(self) -> MissionCreateDraft:
        camera = self._camera_value()
        return MissionCreateDraft(
            mission_id=self.mission_id.text().strip(),
            name=self.name.text().strip(),
            drone_ids=tuple(
                field.text().strip()
                for field in self.drone_fields[: self.drone_count.value()]
            ),
            flight_profile=FlightProfile(
                altitude_m=self.altitude.value(),
                gimbal_pitch_deg=-90.0,
                forward_overlap=self.forward_overlap.value() / 100.0,
                side_overlap=self.side_overlap.value() / 100.0,
            ),
            camera_profile=camera,
        )

    def _accept(self) -> None:
        try:
            draft = self.value()
            if not draft.name or not draft.mission_id:
                raise ValueError("Cần nhập tên và mã nhiệm vụ.")
            if any(not value for value in draft.drone_ids):
                raise ValueError("Mỗi drone cần có một mã định danh.")
            if len(set(draft.drone_ids)) != len(draft.drone_ids):
                raise ValueError("Mã các drone không được trùng nhau.")
            if draft.camera_profile is None:
                raise ValueError("Cần chọn hoặc tạo hồ sơ máy ảnh.")
            if (
                draft.camera_profile.horizontal_fov_deg is None
                and draft.camera_profile.vertical_fov_deg is None
            ):
                raise ValueError("Cần nhập HFOV hoặc VFOV để tính đường bay.")
            if self.save_template.isChecked() and not self.template_name.text().strip():
                raise ValueError("Cần đặt tên cho mẫu cấu hình.")
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Chưa thể tạo nhiệm vụ", str(exc))
            return
        if self.save_template.isChecked():
            _save_template(self._settings, self.template_name.text().strip(), self._payload())
        self.accept()

    def _camera_value(self) -> CameraProfile | None:
        selected = self.camera_combo.currentData()
        if isinstance(selected, CameraProfile):
            return selected
        return CameraProfile(
            profile_id=self.camera_id.text().strip(),
            name=self.camera_name.text().strip(),
            make=self.camera_make.text().strip() or None,
            model=self.camera_model.text().strip() or None,
            focal_length_mm=self.focal.value() or None,
            horizontal_fov_deg=self.hfov.value() or None,
            vertical_fov_deg=self.vfov.value() or None,
        )

    def _camera_changed(self, _index: int) -> None:
        selected = self.camera_combo.currentData()
        editable = not isinstance(selected, CameraProfile)
        if isinstance(selected, CameraProfile):
            self.camera_id.setText(selected.profile_id)
            self.camera_name.setText(selected.name)
            self.camera_make.setText(selected.make or "")
            self.camera_model.setText(selected.model or "")
            self.focal.setValue(selected.focal_length_mm or 0.0)
            self.hfov.setValue(selected.horizontal_fov_deg or 0.0)
            self.vfov.setValue(selected.vertical_fov_deg or 0.0)
        for field in (
            self.camera_id,
            self.camera_name,
            self.camera_make,
            self.camera_model,
            self.focal,
            self.hfov,
            self.vfov,
        ):
            field.setEnabled(editable)

    def _apply_template(self, _index: int) -> None:
        value = self.template_combo.currentData()
        if not isinstance(value, dict):
            return
        self.drone_count.setValue(int(value.get("drone_count", 3)))
        drone_ids = value.get("drone_ids", [])
        if isinstance(drone_ids, list):
            for field, drone_id in zip(self.drone_fields, drone_ids, strict=False):
                field.setText(str(drone_id))
        self.altitude.setValue(float(value.get("altitude_m", 10.0)))
        self.forward_overlap.setValue(float(value.get("forward_overlap", 75.0)))
        self.side_overlap.setValue(float(value.get("side_overlap", 65.0)))
        profile_id = str(value.get("camera_profile_id", ""))
        matched = self.camera_combo.findData(profile_id)
        if matched < 0:
            matched = next(
                (
                    index
                    for index, profile in enumerate(self._camera_profiles, start=1)
                    if profile.profile_id == profile_id
                ),
                0,
            )
        self.camera_combo.setCurrentIndex(matched)
        if matched == 0:
            self.camera_id.setText(profile_id or "camera-rgb")
            self.camera_name.setText(str(value.get("camera_name", "Máy ảnh RGB")))
            self.camera_make.setText(str(value.get("camera_make", "")))
            self.camera_model.setText(str(value.get("camera_model", "")))
            self.focal.setValue(float(value.get("focal_length_mm", 0.0)))
            self.hfov.setValue(float(value.get("horizontal_fov_deg", 0.0)))
            self.vfov.setValue(float(value.get("vertical_fov_deg", 0.0)))

    def _payload(self) -> dict[str, object]:
        camera = self._camera_value()
        return {
            "drone_count": self.drone_count.value(),
            "drone_ids": [field.text().strip() for field in self.drone_fields],
            "altitude_m": self.altitude.value(),
            "forward_overlap": self.forward_overlap.value(),
            "side_overlap": self.side_overlap.value(),
            "camera_profile_id": camera.profile_id if camera else "",
            "camera_name": camera.name if camera else "",
            "camera_make": camera.make or "" if camera else "",
            "camera_model": camera.model or "" if camera else "",
            "focal_length_mm": camera.focal_length_mm or 0.0 if camera else 0.0,
            "horizontal_fov_deg": camera.horizontal_fov_deg or 0.0 if camera else 0.0,
            "vertical_fov_deg": camera.vertical_fov_deg or 0.0 if camera else 0.0,
        }

    def _suggest_id(self, value: str) -> None:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")
        suffix = datetime.now().strftime("%Y%m%d-%H%M")
        self.mission_id.setText(f"{slug or 'mission'}-{suffix}")

    def _update_drone_fields(self, count: int) -> None:
        for index, field in enumerate(self.drone_fields, start=1):
            label = self._label_for_field(field)
            visible = index <= count
            field.setVisible(visible)
            if label is not None:
                label.setVisible(visible)

    def _label_for_field(self, field: QWidget) -> QWidget | None:
        parent = field.parentWidget()
        layout = parent.layout() if parent is not None else None
        if isinstance(layout, QFormLayout):
            return layout.labelForField(field)
        return None

    def _template_toggled(self, enabled: bool) -> None:
        self.template_name.setVisible(enabled)
        if enabled:
            self.template_name.setFocus(Qt.FocusReason.OtherFocusReason)


def _number_field(
    minimum: float,
    maximum: float,
    value: float,
    suffix: str,
    *,
    decimals: int = 1,
) -> QDoubleSpinBox:
    field = QDoubleSpinBox()
    field.setRange(minimum, maximum)
    field.setDecimals(decimals)
    field.setSuffix(suffix)
    field.setValue(value)
    return field


def _optional_field(minimum: float, maximum: float, suffix: str) -> QDoubleSpinBox:
    field = QDoubleSpinBox()
    field.setRange(0.0, maximum)
    field.setDecimals(3)
    field.setSuffix(suffix)
    field.setSpecialValueText("Không rõ")
    field.setValue(0.0)
    return field


def _load_templates(settings: QSettings) -> list[dict[str, object]]:
    raw = settings.value(_TEMPLATE_KEY, "[]")
    try:
        values = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [value for value in values if isinstance(value, dict)] if isinstance(values, list) else []


def _save_template(
    settings: QSettings,
    name: str,
    payload: dict[str, object],
) -> None:
    templates = _load_templates(settings)
    value = {"template_name": name, **payload}
    templates = [item for item in templates if item.get("template_name") != name]
    templates.append(value)
    settings.setValue(_TEMPLATE_KEY, json.dumps(templates, ensure_ascii=False))
    settings.sync()
