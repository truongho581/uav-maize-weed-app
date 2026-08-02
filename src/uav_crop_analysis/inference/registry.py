"""Versioned model registry with strict compatibility and integrity checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any

from uav_crop_analysis.errors import (
    CheckpointIntegrityError,
    ModelManifestError,
    ModelUnavailableError,
)


MODEL_REGISTRY_SCHEMA_VERSION = 2


class ModelTask(str, Enum):
    SEMANTIC = "semantic_segmentation"
    MAIZE_INSTANCE = "maize_instance_segmentation"


class RuntimeKind(str, Enum):
    PYTORCH = "pytorch"
    ONNX = "onnxruntime"
    ULTRALYTICS = "ultralytics"
    TORCHVISION = "torchvision"


@dataclass(frozen=True, slots=True)
class PreprocessingSpec:
    color_space: str
    resize_mode: str
    interpolation: str
    value_scale: float
    mean: tuple[float, float, float]
    std: tuple[float, float, float]

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "color_space": self.color_space,
                "resize_mode": self.resize_mode,
                "interpolation": self.interpolation,
                "value_scale": self.value_scale,
                "mean": self.mean,
                "std": self.std,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    role: str
    path: str
    sha256: str
    format: str


@dataclass(frozen=True, slots=True)
class ModelManifest:
    model_id: str
    version: str
    family: str
    task: ModelTask
    status: str
    class_names: tuple[str, ...]
    target_classes: tuple[str, ...]
    input_size_hw: tuple[int, int]
    dataset_version: str
    runtime: RuntimeKind
    output_adapter: str
    preprocessing: PreprocessingSpec
    artifacts: tuple[ModelArtifact, ...]


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    manifest: ModelManifest
    artifact: ModelArtifact
    artifact_path: Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ModelRegistry:
    def __init__(self, models: tuple[ModelManifest, ...], artifact_root: Path) -> None:
        ids = [model.model_id for model in models]
        if len(ids) != len(set(ids)):
            raise ModelManifestError("model IDs must be unique")
        self._models = {model.model_id: model for model in models}
        self.artifact_root = artifact_root.resolve()

    @classmethod
    def from_file(cls, registry_path: str | Path) -> ModelRegistry:
        path = Path(registry_path).expanduser().resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelManifestError(f"cannot read model registry: {path}") from exc
        if payload.get("schema_version") != MODEL_REGISTRY_SCHEMA_VERSION:
            raise ModelManifestError(
                f"unsupported model registry schema: {payload.get('schema_version')}"
            )
        artifact_root = (path.parent / payload.get("artifact_root", ".")).resolve()
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise ModelManifestError("models must be a list")
        return cls(tuple(_parse_manifest(item) for item in raw_models), artifact_root)

    def list_models(self, task: ModelTask | None = None) -> tuple[ModelManifest, ...]:
        models = tuple(self._models.values())
        if task is not None:
            models = tuple(model for model in models if model.task is task)
        return models

    def get(self, model_id: str) -> ModelManifest:
        try:
            return self._models[model_id]
        except KeyError as exc:
            raise ModelManifestError(f"unknown model ID: {model_id}") from exc

    def resolve(
        self,
        model_id: str,
        artifact_role: str,
        *,
        verify_checksum: bool = True,
    ) -> ResolvedModel:
        manifest = self.get(model_id)
        artifact = next(
            (item for item in manifest.artifacts if item.role == artifact_role),
            None,
        )
        if artifact is None:
            raise ModelUnavailableError(
                f"artifact is not available: {model_id}/{artifact_role}",
                context={"model_id": model_id, "artifact_role": artifact_role},
            )
        artifact_path = (self.artifact_root / artifact.path).resolve()
        if not artifact_path.is_file():
            raise ModelUnavailableError(
                f"model artifact does not exist: {artifact_path}",
                context={"model_id": model_id, "artifact_role": artifact_role},
            )
        if verify_checksum:
            actual = sha256_file(artifact_path)
            if actual != artifact.sha256:
                raise CheckpointIntegrityError(
                    f"checkpoint checksum mismatch: {model_id}/{artifact_role}",
                    context={"expected": artifact.sha256, "actual": actual},
                )
        return ResolvedModel(manifest, artifact, artifact_path)


def _parse_manifest(payload: Any) -> ModelManifest:
    if not isinstance(payload, dict):
        raise ModelManifestError("each model manifest must be an object")
    try:
        class_names = tuple(str(item) for item in payload["class_names"])
        target_classes = tuple(str(item) for item in payload["target_classes"])
        size = tuple(int(item) for item in payload["input_size"])
        pre = payload["preprocessing"]
        preprocessing = PreprocessingSpec(
            color_space=str(pre["color_space"]),
            resize_mode=str(pre["resize_mode"]),
            interpolation=str(pre["interpolation"]),
            value_scale=float(pre["value_scale"]),
            mean=_triple(pre["mean"]),
            std=_triple(pre["std"]),
        )
        artifacts = tuple(
            ModelArtifact(
                role=str(item["role"]),
                path=str(item["path"]),
                sha256=str(item["sha256"]),
                format=str(item["format"]),
            )
            for item in payload.get("artifacts", [])
        )
        manifest = ModelManifest(
            model_id=str(payload["id"]),
            version=str(payload["version"]),
            family=str(payload["family"]),
            task=ModelTask(payload["task"]),
            status=str(payload["status"]),
            class_names=class_names,
            target_classes=target_classes,
            input_size_hw=(size[0], size[1]),
            dataset_version=str(payload["dataset_version"]),
            runtime=RuntimeKind(payload["runtime"]["kind"]),
            output_adapter=str(payload["runtime"]["output_adapter"]),
            preprocessing=preprocessing,
            artifacts=artifacts,
        )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ModelManifestError("model manifest has invalid or missing fields") from exc
    _validate_manifest(manifest)
    return manifest


def _validate_manifest(manifest: ModelManifest) -> None:
    if not manifest.model_id or not manifest.version or not manifest.family:
        raise ModelManifestError("model ID, version and family are required")
    if len(manifest.input_size_hw) != 2 or min(manifest.input_size_hw) < 1:
        raise ModelManifestError(f"invalid input size for {manifest.model_id}")
    if len(manifest.class_names) < 2 or len(set(manifest.class_names)) != len(
        manifest.class_names
    ):
        raise ModelManifestError(f"invalid class map for {manifest.model_id}")
    if not manifest.target_classes or not set(manifest.target_classes) <= set(
        manifest.class_names
    ):
        raise ModelManifestError(f"invalid target classes for {manifest.model_id}")
    if manifest.task is ModelTask.SEMANTIC and not {"crop", "weed"} <= set(
        manifest.target_classes
    ):
        raise ModelManifestError("semantic business output must include crop and weed")
    if manifest.task is ModelTask.SEMANTIC and manifest.output_adapter != "semantic_logits":
        raise ModelManifestError("semantic model output adapter must be semantic_logits")
    if manifest.task is ModelTask.MAIZE_INSTANCE and "weed" in manifest.class_names:
        raise ModelManifestError("weed must not be an instance class")
    if manifest.preprocessing.color_space != "rgb":
        raise ModelManifestError("only RGB model input is currently supported")
    if manifest.preprocessing.resize_mode != "stretch":
        raise ModelManifestError("only stretch resize is currently supported")
    if manifest.preprocessing.interpolation != "bilinear":
        raise ModelManifestError("only bilinear image resize is currently supported")
    if len(manifest.preprocessing.mean) != 3 or len(manifest.preprocessing.std) != 3:
        raise ModelManifestError("preprocessing mean/std must have three values")
    if any(value <= 0 for value in manifest.preprocessing.std):
        raise ModelManifestError("preprocessing std must be positive")
    for artifact in manifest.artifacts:
        if not artifact.role or not artifact.path or len(artifact.sha256) != 64:
            raise ModelManifestError(f"invalid artifact for {manifest.model_id}")
        try:
            int(artifact.sha256, 16)
        except ValueError as exc:
            raise ModelManifestError(f"invalid artifact checksum for {manifest.model_id}") from exc


def _triple(values: Any) -> tuple[float, float, float]:
    if not isinstance(values, list) or len(values) != 3:
        raise ModelManifestError("preprocessing vectors must contain three values")
    return float(values[0]), float(values[1]), float(values[2])
