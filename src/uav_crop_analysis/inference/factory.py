"""Application-facing model factory; callers switch models through IDs and roles."""

from __future__ import annotations

from uav_crop_analysis.inference.contracts import SemanticSegmenter
from uav_crop_analysis.inference.onnx_semantic import OnnxSemanticSegmenter
from uav_crop_analysis.inference.registry import ModelRegistry, RuntimeKind
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
