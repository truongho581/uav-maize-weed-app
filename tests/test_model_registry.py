from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from uav_crop_analysis.errors import (
    CheckpointIntegrityError,
    ModelManifestError,
    ModelUnavailableError,
)
from uav_crop_analysis.inference import ModelRegistry, ModelTask


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = PROJECT_ROOT / "models/model_inventory.json"


def test_registry_encodes_weed_semantic_and_maize_instance_contracts() -> None:
    registry = ModelRegistry.from_file(INVENTORY_PATH)

    semantic = registry.list_models(ModelTask.SEMANTIC)
    instance = registry.list_models(ModelTask.MAIZE_INSTANCE)

    assert len(semantic) == 3
    assert all(model.class_names == ("background", "crop", "weed") for model in semantic)
    assert all(model.target_classes == ("weed",) for model in semantic)
    assert len(instance) == 2
    assert all("weed" not in model.class_names for model in instance)
    assert all(not model.artifacts for model in instance)


def test_registry_reports_pending_instance_checkpoint() -> None:
    registry = ModelRegistry.from_file(INVENTORY_PATH)

    with pytest.raises(ModelUnavailableError) as caught:
        registry.resolve("yolov8-seg-v72-instance", "best")

    assert caught.value.code == "model_unavailable"


def test_registry_rejects_checksum_mismatch(tmp_path: Path) -> None:
    registry = ModelRegistry.from_file(INVENTORY_PATH)
    manifest = registry.get("attention-unet-v72-loso")
    checkpoint = tmp_path / "model.pth"
    checkpoint.write_bytes(b"not the registered model")
    artifact = replace(
        manifest.artifacts[0],
        path=checkpoint.name,
        sha256="0" * 64,
    )
    isolated = ModelRegistry((replace(manifest, artifacts=(artifact,)),), tmp_path)

    with pytest.raises(CheckpointIntegrityError):
        isolated.resolve(manifest.model_id, artifact.role)


def test_registry_rejects_semantic_crop_as_business_output(tmp_path: Path) -> None:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    payload["models"][0]["target_classes"] = ["crop"]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ModelManifestError, match="weed only"):
        ModelRegistry.from_file(path)
