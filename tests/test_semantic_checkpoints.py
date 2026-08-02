from __future__ import annotations

from pathlib import Path

import pytest

from uav_crop_analysis.inference import ModelRegistry
from uav_crop_analysis.inference.torch_semantic import TorchSemanticSegmenter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ModelRegistry.from_file(PROJECT_ROOT / "models/model_inventory.json")
MODEL_CASES = (
    (
        "segformer-b0-v72-maizemask-weedsgalore",
        "best_joint_seed_42",
        3_714_915,
    ),
)


@pytest.mark.external_golden
@pytest.mark.parametrize(("model_id", "artifact_role", "parameter_count"), MODEL_CASES)
def test_semantic_checkpoint_loads_strictly(
    model_id: str, artifact_role: str, parameter_count: int
) -> None:
    manifest = REGISTRY.get(model_id)
    if not manifest.artifacts:
        pytest.skip("external checkpoint is not configured")
    path = (REGISTRY.artifact_root / manifest.artifacts[0].path).resolve()
    if not path.is_file():
        pytest.skip(f"external checkpoint is unavailable: {path}")

    segmenter = TorchSemanticSegmenter.load(
        REGISTRY.resolve(model_id, artifact_role),
        device="cpu",
    )

    assert sum(item.numel() for item in segmenter.model.parameters()) == parameter_count
