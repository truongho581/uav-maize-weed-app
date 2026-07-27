"""PyTorch adapter for Attention U-Net, DeepLabV3+ and SegFormer checkpoints."""

from __future__ import annotations

from time import perf_counter
from typing import Any

import numpy as np

from uav_crop_analysis.errors import InferenceRuntimeError, ModelManifestError
from uav_crop_analysis.inference.contracts import (
    ImageInput,
    PredictionProvenance,
    SemanticPrediction,
)
from uav_crop_analysis.inference.preprocessing import prepare_semantic_input
from uav_crop_analysis.inference.registry import ModelTask, ResolvedModel, RuntimeKind
from uav_crop_analysis.inference.torch_models import build_semantic_model


def select_torch_device(name: str = "auto") -> Any:
    import torch

    if name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def logits_from_output(output: Any, target_hw: tuple[int, int]) -> Any:
    import torch

    if isinstance(output, torch.Tensor):
        logits = output
    elif isinstance(output, dict) and "logits" in output:
        logits = output["logits"]
    elif hasattr(output, "logits"):
        logits = output.logits
    else:
        raise InferenceRuntimeError(f"unsupported semantic model output: {type(output)}")
    if logits.ndim != 4:
        raise InferenceRuntimeError(
            "semantic logits must use NCHW shape",
            context={"shape": tuple(logits.shape)},
        )
    if logits.shape[-2:] != target_hw:
        logits = torch.nn.functional.interpolate(
            logits,
            size=target_hw,
            mode="bilinear",
            align_corners=False,
        )
    return logits


class TorchSemanticSegmenter:
    def __init__(self, resolved: ResolvedModel, model: Any, device: Any) -> None:
        self.resolved = resolved
        self.model = model
        self.device = device

    @classmethod
    def load(cls, resolved: ResolvedModel, device: str = "auto") -> TorchSemanticSegmenter:
        import torch
        from torch.torch_version import TorchVersion

        manifest = resolved.manifest
        if manifest.task is not ModelTask.SEMANTIC:
            raise ModelManifestError(f"model is not semantic: {manifest.model_id}")
        if manifest.runtime is not RuntimeKind.PYTORCH or resolved.artifact.format != "pytorch":
            raise ModelManifestError(f"artifact is not a PyTorch semantic model: {manifest.model_id}")
        selected_device = select_torch_device(device)
        try:
            with torch.serialization.safe_globals([TorchVersion]):
                checkpoint = torch.load(
                    resolved.artifact_path,
                    map_location=selected_device,
                    weights_only=True,
                )
        except Exception as exc:
            raise InferenceRuntimeError(
                f"cannot load checkpoint: {resolved.artifact_path}",
                context={"model_id": manifest.model_id},
            ) from exc
        _validate_checkpoint(checkpoint, resolved)
        model = build_semantic_model(
            family=manifest.family,
            num_classes=len(manifest.class_names),
            norm=str(checkpoint.get("norm", "gn")),
        )
        try:
            model.load_state_dict(checkpoint["model_state_dict"], strict=True)
        except Exception as exc:
            raise InferenceRuntimeError(
                f"checkpoint weights are incompatible with {manifest.family}"
            ) from exc
        model.to(selected_device)
        model.eval()
        return cls(resolved, model, selected_device)

    def predict(self, image: ImageInput) -> SemanticPrediction:
        import torch

        manifest = self.resolved.manifest
        source_hw = image.size_hw
        batch = prepare_semantic_input(image, manifest.input_size_hw, manifest.preprocessing)
        tensor = torch.from_numpy(batch).to(self.device)
        started = perf_counter()
        try:
            with torch.inference_mode():
                output = self.model(tensor)
                logits = logits_from_output(output, source_hw)
                probabilities_tensor = torch.softmax(logits, dim=1)[0]
        except Exception as exc:
            raise InferenceRuntimeError(
                f"semantic inference failed for {manifest.model_id}",
                context={"device": str(self.device)},
            ) from exc
        latency_ms = (perf_counter() - started) * 1000.0
        probabilities = np.ascontiguousarray(
            probabilities_tensor.detach().cpu().numpy(), dtype=np.float32
        )
        class_map = np.ascontiguousarray(probabilities.argmax(axis=0), dtype=np.int32)
        masks = {
            name: np.ascontiguousarray(class_map == manifest.class_names.index(name))
            for name in manifest.target_classes
        }
        return SemanticPrediction(
            class_names=manifest.class_names,
            class_map=class_map,
            probabilities=probabilities,
            target_masks=masks,
            provenance=_provenance(self.resolved, str(self.device)),
            latency_ms=latency_ms,
        )


def _validate_checkpoint(checkpoint: Any, resolved: ResolvedModel) -> None:
    if not isinstance(checkpoint, dict) or "model_state_dict" not in checkpoint:
        raise InferenceRuntimeError("checkpoint does not contain model_state_dict")
    manifest = resolved.manifest
    checks = {
        "model": manifest.family,
        "class_names": list(manifest.class_names),
        "img_size": manifest.input_size_hw[0],
        "color_profile": "none",
    }
    for field, expected in checks.items():
        if checkpoint.get(field) != expected:
            raise ModelManifestError(
                f"checkpoint {field} does not match manifest",
                context={"expected": expected, "actual": checkpoint.get(field)},
            )


def _provenance(resolved: ResolvedModel, device: str) -> PredictionProvenance:
    manifest = resolved.manifest
    return PredictionProvenance(
        model_id=manifest.model_id,
        model_version=manifest.version,
        artifact_role=resolved.artifact.role,
        artifact_sha256=resolved.artifact.sha256,
        runtime=manifest.runtime.value,
        device=device,
        preprocessing_fingerprint=manifest.preprocessing.fingerprint(),
    )
