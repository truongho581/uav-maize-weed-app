"""Application-facing model factory; callers switch models through IDs and roles."""

from __future__ import annotations

from uav_crop_analysis.errors import ModelManifestError
from uav_crop_analysis.inference.contracts import InstanceSegmenter, SemanticSegmenter
from uav_crop_analysis.inference.onnx_semantic import OnnxSemanticSegmenter
from uav_crop_analysis.inference.registry import ModelRegistry, ModelTask, RuntimeKind
from uav_crop_analysis.inference.torch_semantic import TorchSemanticSegmenter


class SegmenterFactory:
    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def load_semantic(
        self,
        model_id: str,
        artifact_role: str,
        *,
        device: str = "auto",
        verify_checksum: bool = True,
    ) -> SemanticSegmenter:
        resolved = self.registry.resolve(
            model_id,
            artifact_role,
            verify_checksum=verify_checksum,
        )
        if resolved.manifest.runtime is RuntimeKind.ONNX:
            return OnnxSemanticSegmenter.load(resolved)
        return TorchSemanticSegmenter.load(resolved, device=device)

    def load_instance(
        self,
        model_id: str,
        artifact_role: str,
        *,
        device: str = "auto",
        verify_checksum: bool = True,
    ) -> InstanceSegmenter:
        """Load a maize-only instance segmenter through the registered runtime."""
        resolved = self.registry.resolve(
            model_id,
            artifact_role,
            verify_checksum=verify_checksum,
        )
        if resolved.manifest.task is not ModelTask.MAIZE_INSTANCE:
            raise ModelManifestError("requested model is not an instance segmentation model")
        if resolved.manifest.runtime is not RuntimeKind.ULTRALYTICS:
            raise ModelManifestError(
                f"instance runtime is not implemented: {resolved.manifest.runtime.value}"
            )
        # Keep Ultralytics lazy so importing the public inference contracts does not
        # initialize the heavyweight YOLO stack.
        from uav_crop_analysis.inference.ultralytics_instance import (
            UltralyticsInstanceSegmenter,
        )

        return UltralyticsInstanceSegmenter.load(resolved, device=device)
