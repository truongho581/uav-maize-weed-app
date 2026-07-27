"""ONNX Runtime semantic adapter using the same preprocessing contract as PyTorch."""

from __future__ import annotations

from time import perf_counter
from typing import Any

import numpy as np
from PIL import Image

from uav_crop_analysis.errors import DependencyUnavailableError, InferenceRuntimeError
from uav_crop_analysis.inference.contracts import (
    ImageInput,
    PredictionProvenance,
    SemanticPrediction,
)
from uav_crop_analysis.inference.preprocessing import prepare_semantic_input
from uav_crop_analysis.inference.registry import ModelTask, ResolvedModel, RuntimeKind


class OnnxSemanticSegmenter:
    def __init__(self, resolved: ResolvedModel, session: Any) -> None:
        self.resolved = resolved
        self.session = session
        self.input_name = session.get_inputs()[0].name

    @classmethod
    def load(cls, resolved: ResolvedModel) -> OnnxSemanticSegmenter:
        manifest = resolved.manifest
        if manifest.task is not ModelTask.SEMANTIC:
            raise InferenceRuntimeError(f"model is not semantic: {manifest.model_id}")
        if manifest.runtime is not RuntimeKind.ONNX or resolved.artifact.format != "onnx":
            raise InferenceRuntimeError(f"artifact is not an ONNX semantic model: {manifest.model_id}")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise DependencyUnavailableError(
                "ONNX inference requires the optional 'onnx' dependencies"
            ) from exc
        session = ort.InferenceSession(
            str(resolved.artifact_path),
            providers=["CPUExecutionProvider"],
        )
        return cls(resolved, session)

    def predict(self, image: ImageInput) -> SemanticPrediction:
        manifest = self.resolved.manifest
        batch = prepare_semantic_input(image, manifest.input_size_hw, manifest.preprocessing)
        started = perf_counter()
        outputs = self.session.run(None, {self.input_name: batch})
        latency_ms = (perf_counter() - started) * 1000.0
        if not outputs:
            raise InferenceRuntimeError("ONNX model returned no output")
        logits = np.asarray(outputs[0], dtype=np.float32)
        if logits.ndim != 4 or logits.shape[0] != 1 or logits.shape[1] != len(
            manifest.class_names
        ):
            raise InferenceRuntimeError(
                "ONNX logits must use 1xCxHxW shape",
                context={"shape": logits.shape},
            )
        logits = _resize_logits(logits[0], image.size_hw)
        probabilities = _softmax(logits)
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
            provenance=PredictionProvenance(
                model_id=manifest.model_id,
                model_version=manifest.version,
                artifact_role=self.resolved.artifact.role,
                artifact_sha256=self.resolved.artifact.sha256,
                runtime=manifest.runtime.value,
                device="cpu",
                preprocessing_fingerprint=manifest.preprocessing.fingerprint(),
            ),
            latency_ms=latency_ms,
        )


def _resize_logits(logits: np.ndarray, size_hw: tuple[int, int]) -> np.ndarray:
    if logits.shape[-2:] == size_hw:
        return np.ascontiguousarray(logits, dtype=np.float32)
    height, width = size_hw
    resized = [
        np.asarray(
            Image.fromarray(channel, mode="F").resize(
                (width, height), Image.Resampling.BILINEAR
            ),
            dtype=np.float32,
        )
        for channel in logits
    ]
    return np.ascontiguousarray(np.stack(resized), dtype=np.float32)


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=0, keepdims=True)
    exp = np.exp(shifted)
    return np.ascontiguousarray(exp / exp.sum(axis=0, keepdims=True), dtype=np.float32)
