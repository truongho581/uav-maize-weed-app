"""Access to the JSON Schema shipped for GreenEye mission-plan integration."""

from __future__ import annotations

from importlib.resources import files
import json
from typing import Any


def load_mission_plan_schema() -> dict[str, Any]:
    resource = files("uav_crop_analysis").joinpath(
        "resources/schemas/greeneye-mission-plan.schema.json"
    )
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("GreenEye mission-plan schema root must be an object")
    return value
