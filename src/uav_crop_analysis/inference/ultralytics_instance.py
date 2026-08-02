"""Ultralytics YOLOv8-seg adapter for maize-only instance segmentation."""

from __future__ import annotations

from time import perf_counter
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from uav_crop_analysis.errors import (
    DependencyUnavailableError,
    InferenceRuntimeError,
    ModelManifestError,
)
from uav_crop_analysis.inference.contracts import (
    ColorSpace,
    ImageInput,
    InstanceBatchPrediction,
    InstancePrediction,
    PredictionProvenance,
)
from uav_crop_analysis.inference.registry import ModelTask, ResolvedModel, RuntimeKind


class UltralyticsInstanceSegmenter:
    """Adapter that normalizes YOLO masks into the project instance contract."""

    def __init__(self, resolved: ResolvedModel, model: Any, device: str) -> None:
        self.resolved = resolved
        self.model = model
        self.device = _resolve_ultralytics_device(device)
        self._validate_model()

    @classmethod
    def load(
        cls,
        resolved: ResolvedModel,
        *,
        device: str = "auto",
    ) -> UltralyticsInstanceSegmenter:
        _validate_resolved_model(resolved)
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise DependencyUnavailableError(
                "Ultralytics is required to run the YOLOv8 maize instance checkpoint"
            ) from exc
        try:
            model = YOLO(str(resolved.artifact_path))
        except Exception as exc:
            raise InferenceRuntimeError(
                f"cannot load YOLOv8 instance checkpoint: {resolved.artifact_path}"
            ) from exc
        return cls(resolved, model, device)

    def predict(self, image: ImageInput) -> InstanceBatchPrediction:
        pixels = image.pixels
        if image.color_space is ColorSpace.RGB:
            pixels = np.ascontiguousarray(pixels[..., ::-1])
        started = perf_counter()
        try:
            result = self.model.predict(
                source=pixels,
                imgsz=self.resolved.manifest.input_size_hw[0],
                conf=0.25,
                iou=0.70,
                max_det=300,
                device=self.device,
                retina_masks=True,
                verbose=False,
            )[0]
        except Exception as exc:
            raise InferenceRuntimeError(
                f"YOLOv8 instance inference failed on {self.device}: {exc}"
            ) from exc

        instances = self._instances_from_result(result, image.size_hw)
        return InstanceBatchPrediction(
            image_size_hw=image.size_hw,
            instances=instances,
            provenance=PredictionProvenance(
                model_id=self.resolved.manifest.model_id,
                model_version=self.resolved.manifest.version,
                artifact_role=self.resolved.artifact.role,
                artifact_sha256=self.resolved.artifact.sha256,
                runtime=RuntimeKind.ULTRALYTICS.value,
                device=self.device,
                preprocessing_fingerprint=self.resolved.manifest.preprocessing.fingerprint(),
            ),
            latency_ms=(perf_counter() - started) * 1000.0,
        )

    def _validate_model(self) -> None:
        raw_names = getattr(self.model, "names", None)
        if not isinstance(raw_names, dict):
            raise ModelManifestError("YOLO checkpoint does not expose a class map")
        names = tuple(str(raw_names.get(index, "")) for index in range(len(raw_names)))
        if names != self.resolved.manifest.class_names:
            raise ModelManifestError(
                "YOLO checkpoint class map does not match the registered maize classes",
                context={
                    "checkpoint_classes": names,
                    "registered_classes": self.resolved.manifest.class_names,
                },
            )

    def _instances_from_result(
        self,
        result: Any,
        image_size_hw: tuple[int, int],
    ) -> tuple[InstancePrediction, ...]:
        boxes = getattr(result, "boxes", None)
        masks = getattr(result, "masks", None)
        if boxes is None or masks is None or getattr(masks, "data", None) is None:
            return ()
        mask_data = _as_numpy(masks.data)
        classes = _as_numpy(boxes.cls).reshape(-1)
        scores = _as_numpy(boxes.conf).reshape(-1)
        coordinates = _as_numpy(boxes.xyxy)
        if not (
            len(mask_data) == len(classes) == len(scores) == len(coordinates)
        ):
            raise InferenceRuntimeError("YOLO result boxes and masks have inconsistent sizes")
        height, width = image_size_hw
        instances: list[InstancePrediction] = []
        for index, (mask, class_value, score, box) in enumerate(
            zip(mask_data, classes, scores, coordinates, strict=True)
        ):
            class_index = int(class_value)
            if not 0 <= class_index < len(self.resolved.manifest.class_names):
                raise InferenceRuntimeError(
                    f"YOLO result contains an unknown class index: {class_index}"
                )
            normalized_mask = _resize_mask(mask, (height, width))
            if len(box) < 4:
                raise InferenceRuntimeError("YOLO result contains an incomplete box")
            box_xyxy = (
                float(box[0]),
                float(box[1]),
                float(box[2]),
                float(box[3]),
            )
            instances.append(
                InstancePrediction(
                    class_index=class_index,
                    class_name=self.resolved.manifest.class_names[class_index],
                    score=float(score),
                    box_xyxy=box_xyxy,
                    mask=normalized_mask,
                )
            )
        return tuple(instances)


def _validate_resolved_model(resolved: ResolvedModel) -> None:
    manifest = resolved.manifest
    if manifest.task is not ModelTask.MAIZE_INSTANCE:
        raise ModelManifestError("Ultralytics adapter requires a maize instance model")
    if manifest.runtime is not RuntimeKind.ULTRALYTICS:
        raise ModelManifestError("Ultralytics adapter requires the ultralytics runtime")
    if manifest.output_adapter != "ultralytics_masks":
        raise ModelManifestError("Ultralytics adapter requires ultralytics_masks output")
    if "weed" in manifest.class_names or "weed" in manifest.target_classes:
        raise ModelManifestError("weed must never be inferred as an instance class")


def _resolve_ultralytics_device(device: str) -> str:
    requested = device.strip().lower()
    if requested != "auto":
        return requested
    import torch

    if torch.cuda.is_available():
        return "0"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


def _as_numpy(value: Any) -> NDArray[Any]:
    candidate = value
    if hasattr(candidate, "detach"):
        candidate = candidate.detach()
    if hasattr(candidate, "cpu"):
        candidate = candidate.cpu()
    if hasattr(candidate, "numpy"):
        candidate = candidate.numpy()
    return np.asarray(candidate)


def _resize_mask(mask: NDArray[Any], size_hw: tuple[int, int]) -> NDArray[np.bool_]:
    height, width = size_hw
    normalized = np.asarray(mask >= 0.5, dtype=np.uint8)
    if normalized.shape != (height, width):
        normalized = np.asarray(
            Image.fromarray(normalized, mode="L").resize(
                (width, height), Image.Resampling.NEAREST
            ),
            dtype=np.uint8,
        )
    return np.ascontiguousarray(normalized.astype(bool), dtype=np.bool_)
