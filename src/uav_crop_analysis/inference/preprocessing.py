"""Shared preprocessing used by PyTorch and ONNX semantic adapters."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from uav_crop_analysis.inference.contracts import ColorSpace, ImageInput
from uav_crop_analysis.inference.registry import PreprocessingSpec


def prepare_semantic_input(
    image: ImageInput,
    input_size_hw: tuple[int, int],
    spec: PreprocessingSpec,
) -> NDArray[np.float32]:
    pixels = image.pixels
    if image.color_space is ColorSpace.BGR:
        pixels = pixels[..., ::-1]
    height, width = input_size_hw
    pil_image = Image.fromarray(np.ascontiguousarray(pixels), mode="RGB")
    resized = pil_image.resize((width, height), Image.Resampling.BILINEAR)
    array = np.asarray(resized, dtype=np.float32) * np.float32(spec.value_scale)
    mean = np.asarray(spec.mean, dtype=np.float32)
    std = np.asarray(spec.std, dtype=np.float32)
    array = (array - mean) / std
    return np.ascontiguousarray(array.transpose(2, 0, 1)[None, ...], dtype=np.float32)
