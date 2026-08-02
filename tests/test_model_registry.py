from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from uav_crop_analysis.errors import (
    CheckpointIntegrityError,
    ModelManifestError,
)
from uav_crop_analysis.inference import ModelRegistry, ModelTask


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = PROJECT_ROOT / "models/model_inventory.json"


def test_registry_encodes_crop_weed_semantic_and_maize_instance_contracts() -> None:
    registry = ModelRegistry.from_file(INVENTORY_PATH)

    semantic = registry.list_models(ModelTask.SEMANTIC)
    instance = registry.list_models(ModelTask.MAIZE_INSTANCE)

    assert len(semantic) == 1
    assert all(model.class_names == ("background", "crop", "weed") for model in semantic)
    assert all(model.target_classes == ("crop", "weed") for model in semantic)
    assert len(instance) == 2
    assert all("weed" not in model.class_names for model in instance)
    production = registry.get("segformer-b0-v72-maizemask-weedsgalore")
    assert production.status == "production_default"
    assert production.artifacts[0].role == "best_joint_seed_42"
    assert production.artifacts[0].path.startswith("models/checkpoints/")
    maize = registry.get("yolov8-seg-v72-instance")
    assert maize.status == "production_default"
    assert maize.artifacts[0].role == "best_fixed_seed_42"


def test_registry_resolves_registered_instance_checkpoint() -> None:
    registry = ModelRegistry.from_file(INVENTORY_PATH)

    resolved = registry.resolve("yolov8-seg-v72-instance", "best_fixed_seed_42")

    assert resolved.artifact.format == "ultralytics"


def test_registry_rejects_checksum_mismatch(tmp_path: Path) -> None:
    registry = ModelRegistry.from_file(INVENTORY_PATH)
    manifest = registry.get("segformer-b0-v72-maizemask-weedsgalore")
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


def test_registry_rejects_semantic_model_missing_crop_or_weed(tmp_path: Path) -> None:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    payload["models"][0]["target_classes"] = ["crop"]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ModelManifestError, match="include crop and weed"):
        ModelRegistry.from_file(path)
