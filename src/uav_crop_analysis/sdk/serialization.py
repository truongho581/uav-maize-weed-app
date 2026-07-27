"""JSON conversion kept stable at SDK/API boundaries."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


def to_json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return to_json_value(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (dict, Mapping, MappingProxyType)):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_json_value(item) for item in value]
    return value
