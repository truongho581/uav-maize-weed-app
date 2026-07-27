from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from uav_crop_analysis.inference import ImageInput, ModelRegistry
from uav_crop_analysis.inference.torch_semantic import TorchSemanticSegmenter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ModelRegistry.from_file(PROJECT_ROOT / "models/model_inventory.json")
MODEL_CASES = (
    ("attention-unet-v72-loso", 31_389_295),
    ("deeplabv3plus-r50-v72-loso", 39_757_219),
    ("segformer-b0-v72-loso", 3_714_915),
)


@pytest.mark.external_golden
@pytest.mark.parametrize(("model_id", "parameter_count"), MODEL_CASES)
def test_semantic_checkpoint_loads_strictly(model_id: str, parameter_count: int) -> None:
    if model_id.startswith("segformer") and find_spec("transformers") is None:
        pytest.skip("transformers optional dependency is not installed")
    manifest = REGISTRY.get(model_id)
    if not manifest.artifacts:
        pytest.skip("external checkpoint is not configured")
    path = (REGISTRY.artifact_root / manifest.artifacts[0].path).resolve()
    if not path.is_file():
        pytest.skip(f"external checkpoint is unavailable: {path}")

    segmenter = TorchSemanticSegmenter.load(
        REGISTRY.resolve(model_id, "best_test_D1_seed_42"),
        device="cpu",
    )

    assert sum(item.numel() for item in segmenter.model.parameters()) == parameter_count


@pytest.mark.external_golden
def test_attention_unet_matches_exported_evaluation_mask() -> None:
    resolved = REGISTRY.resolve("attention-unet-v72-loso", "best_test_D1_seed_42")
    run_directory = resolved.artifact_path.parent
    prediction_directory = run_directory / "predictions/test"
    rgb_paths = sorted(prediction_directory.glob("*_rgb.png"))
    if not rgb_paths:
        pytest.skip("external golden images are unavailable")
    rgb_path = rgb_paths[0]
    expected_path = Path(str(rgb_path).replace("_rgb.png", "_pred_attention_unet.png"))
    image = np.asarray(Image.open(rgb_path).convert("RGB"), dtype=np.uint8)
    expected_rgb = np.asarray(Image.open(expected_path).convert("RGB"), dtype=np.uint8)
    palette = np.asarray([[0, 0, 0], [34, 197, 94], [239, 68, 68]], dtype=np.uint8)
    distances = (
        expected_rgb[:, :, None, :].astype(np.int32) - palette[None, None, :, :].astype(np.int32)
    ) ** 2
    expected = distances.sum(axis=3).argmin(axis=2)
    segmenter = TorchSemanticSegmenter.load(resolved, device="cpu")

    prediction = segmenter.predict(ImageInput(image))

    assert np.mean(prediction.class_map == expected) >= 0.9999
    np.testing.assert_array_equal(prediction.target_masks["weed"], expected == 2)
