from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from uav_crop_analysis.inference import ImageInput, ModelRegistry
from uav_crop_analysis.inference.ultralytics_instance import (
    UltralyticsInstanceSegmenter,
    _resolve_ultralytics_device,
)


class _Boxes:
    cls = np.array([0, 2], dtype=np.float32)
    conf = np.array([0.9, 0.7], dtype=np.float32)
    xyxy = np.array(((0, 0, 2, 2), (1, 1, 4, 3)), dtype=np.float32)


class _Masks:
    data = np.array(
        (
            ((1, 0), (0, 0)),
            ((0, 1), (1, 1)),
        ),
        dtype=np.float32,
    )


class _Result:
    boxes = _Boxes()
    masks = _Masks()


class _Model:
    names = {0: "maize2", 1: "maize4", 2: "maize6"}

    def predict(self, **_kwargs: object) -> list[_Result]:
        return [_Result()]


def test_ultralytics_adapter_preserves_registered_maize_class_map() -> None:
    root = Path(__file__).parents[1]
    registry = ModelRegistry.from_file(root / "models/model_inventory.json")
    resolved = registry.resolve("yolov8-seg-v72-instance", "best_fixed_seed_42")
    adapter = UltralyticsInstanceSegmenter(resolved, _Model(), "cpu")

    prediction = adapter.predict(ImageInput(np.zeros((3, 4, 3), dtype=np.uint8)))

    assert [item.class_name for item in prediction.instances] == ["maize2", "maize6"]
    assert all(item.mask.shape == (3, 4) for item in prediction.instances)
    assert prediction.provenance.runtime == "ultralytics"


def test_ultralytics_auto_device_prefers_mps_on_apple_silicon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)

    assert _resolve_ultralytics_device("auto") == "mps"


def test_ultralytics_auto_device_falls_back_to_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)

    assert _resolve_ultralytics_device("auto") == "cpu"
