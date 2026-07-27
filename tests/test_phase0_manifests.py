import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_model_inventory_has_unique_ids_and_valid_checksums() -> None:
    inventory = json.loads((PROJECT_ROOT / "models/model_inventory.json").read_text())
    models = inventory["models"]
    ids = [model["id"] for model in models]

    assert inventory["schema_version"] == 2
    assert len(ids) == len(set(ids))
    assert {model["task"] for model in models} >= {
        "semantic_segmentation",
        "maize_instance_segmentation",
    }

    for model in models:
        assert model["version"]
        assert model["target_classes"]
        assert model["runtime"]["output_adapter"]
        assert model["preprocessing"]["color_space"] == "rgb"
        for artifact in model["artifacts"]:
            assert len(artifact["sha256"]) == 64
            int(artifact["sha256"], 16)
            assert artifact["format"] in {"pytorch", "onnx", "ultralytics"}
