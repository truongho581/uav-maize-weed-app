"""Public AI contracts and registry without eager framework initialization."""

from .contracts import (
    ColorSpace,
    ImageInput,
    InstanceBatchPrediction,
    InstancePrediction,
    InstanceSegmenter,
    PredictionProvenance,
    SemanticPrediction,
    SemanticSegmenter,
)
from .factory import SegmenterFactory
from .registry import (
    MODEL_REGISTRY_SCHEMA_VERSION,
    ModelArtifact,
    ModelManifest,
    ModelRegistry,
    ModelTask,
    PreprocessingSpec,
    ResolvedModel,
    RuntimeKind,
)

__all__ = [
    "MODEL_REGISTRY_SCHEMA_VERSION",
    "ColorSpace",
    "ImageInput",
    "InstanceBatchPrediction",
    "InstancePrediction",
    "InstanceSegmenter",
    "ModelArtifact",
    "ModelManifest",
    "ModelRegistry",
    "ModelTask",
    "PredictionProvenance",
    "PreprocessingSpec",
    "ResolvedModel",
    "RuntimeKind",
    "SegmenterFactory",
    "SemanticPrediction",
    "SemanticSegmenter",
]
