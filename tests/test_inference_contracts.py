from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import torch

from uav_crop_analysis.errors import InferenceInputError
from uav_crop_analysis.inference import (
    ColorSpace,
    ImageInput,
    ModelArtifact,
    ModelRegistry,
    ResolvedModel,
    RuntimeKind,
)
from uav_crop_analysis.inference.onnx_semantic import OnnxSemanticSegmenter
from uav_crop_analysis.inference.preprocessing import prepare_semantic_input
from uav_crop_analysis.inference.torch_semantic import TorchSemanticSegmenter


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _StaticTorchModel(torch.nn.Module):
    def forward(self, images: torch.Tensor) -> torch.Tensor:
        _, _, height, width = images.shape
        logits = torch.zeros((1, 3, height, width), dtype=images.dtype, device=images.device)
        logits[:, 2, :, width // 2 :] = 5.0
        return logits


class _InputDescription:
    name = "images"


class _StaticOnnxSession:
    def get_inputs(self) -> list[_InputDescription]:
        return [_InputDescription()]

    def run(self, _output_names: object, feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        assert feeds["images"].shape == (1, 3, 2, 2)
        logits = np.zeros((1, 3, 2, 2), dtype=np.float32)
        logits[:, 2, :, 1] = 5.0
        return [logits]


def _resolved(runtime: RuntimeKind, artifact_format: str) -> ResolvedModel:
    manifest = ModelRegistry.from_file(PROJECT_ROOT / "models/model_inventory.json").get(
        "attention-unet-v72-loso"
    )
    manifest = replace(manifest, input_size_hw=(2, 2), runtime=runtime)
    artifact = ModelArtifact("unit", "unit.bin", "a" * 64, artifact_format)
    return ResolvedModel(manifest, artifact, PROJECT_ROOT / "unit.bin")


def test_image_input_rejects_ambiguous_shape_and_dtype() -> None:
    with pytest.raises(InferenceInputError):
        ImageInput(np.zeros((8, 8), dtype=np.uint8))
    with pytest.raises(InferenceInputError):
        ImageInput(np.zeros((8, 8, 3), dtype=np.float32))


def test_rgb_and_bgr_preprocessing_are_equivalent() -> None:
    manifest = _resolved(RuntimeKind.PYTORCH, "pytorch").manifest
    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    rgb[..., 0] = 255
    bgr = rgb[..., ::-1].copy()

    rgb_batch = prepare_semantic_input(ImageInput(rgb), (2, 2), manifest.preprocessing)
    bgr_batch = prepare_semantic_input(
        ImageInput(bgr, ColorSpace.BGR), (2, 2), manifest.preprocessing
    )

    np.testing.assert_array_equal(rgb_batch, bgr_batch)
    assert rgb_batch.shape == (1, 3, 2, 2)
    assert rgb_batch.dtype == np.float32


def test_torch_adapter_returns_source_coordinate_schema() -> None:
    resolved = _resolved(RuntimeKind.PYTORCH, "pytorch")
    segmenter = TorchSemanticSegmenter(resolved, _StaticTorchModel(), torch.device("cpu"))
    image = ImageInput(np.zeros((3, 4, 3), dtype=np.uint8))

    prediction = segmenter.predict(image)

    assert prediction.class_map.shape == (3, 4)
    assert prediction.probabilities.shape == (3, 3, 4)
    assert set(prediction.target_masks) == {"weed"}
    assert prediction.target_masks["weed"].dtype == np.bool_
    np.testing.assert_allclose(prediction.probabilities.sum(axis=0), 1.0, atol=1e-6)


def test_onnx_adapter_returns_same_prediction_contract() -> None:
    resolved = _resolved(RuntimeKind.ONNX, "onnx")
    segmenter = OnnxSemanticSegmenter(resolved, _StaticOnnxSession())
    image = ImageInput(np.zeros((3, 4, 3), dtype=np.uint8))

    prediction = segmenter.predict(image)

    assert prediction.class_map.shape == (3, 4)
    assert prediction.probabilities.shape == (3, 3, 4)
    assert prediction.provenance.runtime == "onnxruntime"
    assert prediction.target_masks["weed"][:, -1].all()
    np.testing.assert_allclose(prediction.probabilities.sum(axis=0), 1.0, atol=1e-6)
