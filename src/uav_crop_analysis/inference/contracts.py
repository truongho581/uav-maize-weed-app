"""Framework-neutral contracts for semantic and instance segmentation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Protocol

import numpy as np
from numpy.typing import NDArray

from uav_crop_analysis.errors import InferenceInputError


class ColorSpace(str, Enum):
    RGB = "rgb"
    BGR = "bgr"


@dataclass(frozen=True, slots=True)
class ImageInput:
    """An unambiguous image payload; spatial convention is always HWC."""

    pixels: NDArray[np.uint8]
    color_space: ColorSpace = ColorSpace.RGB

    def __post_init__(self) -> None:
        if self.pixels.dtype != np.uint8:
            raise InferenceInputError(
                "image pixels must use uint8 dtype",
                context={"dtype": str(self.pixels.dtype)},
            )
        if self.pixels.ndim != 3 or self.pixels.shape[2] != 3:
            raise InferenceInputError(
                "image pixels must have HWC shape with three channels",
                context={"shape": self.pixels.shape},
            )
        if self.pixels.shape[0] < 1 or self.pixels.shape[1] < 1:
            raise InferenceInputError("image dimensions must be positive")

    @property
    def size_hw(self) -> tuple[int, int]:
        return int(self.pixels.shape[0]), int(self.pixels.shape[1])


@dataclass(frozen=True, slots=True)
class PredictionProvenance:
    model_id: str
    model_version: str
    artifact_role: str
    artifact_sha256: str
    runtime: str
    device: str
    preprocessing_fingerprint: str


@dataclass(frozen=True, slots=True)
class SemanticPrediction:
    """Semantic output in source-image coordinates."""

    class_names: tuple[str, ...]
    class_map: NDArray[np.int32]
    probabilities: NDArray[np.float32]
    target_masks: Mapping[str, NDArray[np.bool_]]
    provenance: PredictionProvenance
    latency_ms: float

    def __post_init__(self) -> None:
        if self.class_map.dtype != np.int32 or self.class_map.ndim != 2:
            raise InferenceInputError("class_map must be an int32 HxW array")
        expected = (len(self.class_names), *self.class_map.shape)
        if self.probabilities.dtype != np.float32 or self.probabilities.shape != expected:
            raise InferenceInputError(
                "probabilities must be float32 CxHxW",
                context={"expected": expected, "actual": self.probabilities.shape},
            )
        if not np.isfinite(self.probabilities).all():
            raise InferenceInputError("probabilities contain non-finite values")
        for name, mask in self.target_masks.items():
            if name not in self.class_names:
                raise InferenceInputError(f"unknown target mask class: {name}")
            if mask.dtype != np.bool_ or mask.shape != self.class_map.shape:
                raise InferenceInputError(f"target mask {name} must be bool HxW")
        object.__setattr__(self, "target_masks", MappingProxyType(dict(self.target_masks)))


@dataclass(frozen=True, slots=True)
class InstancePrediction:
    """One maize instance in source-image pixel coordinates."""

    class_index: int
    class_name: str
    score: float
    box_xyxy: tuple[float, float, float, float]
    mask: NDArray[np.bool_]

    def __post_init__(self) -> None:
        if self.class_index < 0 or not self.class_name:
            raise InferenceInputError("instance class is invalid")
        if not 0.0 <= self.score <= 1.0:
            raise InferenceInputError("instance score must be in [0, 1]")
        x1, y1, x2, y2 = self.box_xyxy
        if x2 < x1 or y2 < y1:
            raise InferenceInputError("instance box must follow xyxy convention")
        if self.mask.dtype != np.bool_ or self.mask.ndim != 2:
            raise InferenceInputError("instance mask must be a bool HxW array")


@dataclass(frozen=True, slots=True)
class InstanceBatchPrediction:
    image_size_hw: tuple[int, int]
    instances: tuple[InstancePrediction, ...]
    provenance: PredictionProvenance
    latency_ms: float

    def __post_init__(self) -> None:
        if any(item.mask.shape != self.image_size_hw for item in self.instances):
            raise InferenceInputError("all instance masks must match source image size")


class SemanticSegmenter(Protocol):
    def predict(self, image: ImageInput) -> SemanticPrediction: ...


class InstanceSegmenter(Protocol):
    def predict(self, image: ImageInput) -> InstanceBatchPrediction: ...
