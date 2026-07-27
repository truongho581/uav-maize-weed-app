"""Create an artifact-free registry for SDK installs without a model pack."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


def ensure_default_registry(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(_registry_payload(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _registry_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "artifact_root": ".",
        "dataset": {
            "id": "maizemask-v7.2",
            "annotation_contract": {
                "maize": "instance segmentation with maize2/maize4/maize6 stages",
                "weed": "semantic segmentation",
            },
        },
        "models": [
            _model(
                "attention-unet-v72-loso",
                "7.2-loso",
                "attention_unet",
                "semantic_segmentation",
                "evaluation_only_loso_no_artifact",
                "pytorch",
                "semantic_logits",
                ["background", "crop", "weed"],
                ["weed"],
            ),
            _model(
                "deeplabv3plus-r50-v72-loso",
                "7.2-loso",
                "deeplabv3plus_resnet50",
                "semantic_segmentation",
                "evaluation_only_loso_no_artifact",
                "pytorch",
                "semantic_logits",
                ["background", "crop", "weed"],
                ["weed"],
            ),
            _model(
                "segformer-b0-v72-loso",
                "7.2-loso",
                "segformer_b0",
                "semantic_segmentation",
                "evaluation_only_loso_no_artifact",
                "pytorch",
                "semantic_logits",
                ["background", "crop", "weed"],
                ["weed"],
            ),
            _model(
                "yolov8-seg-v72-instance",
                "7.2-pending",
                "yolov8",
                "maize_instance_segmentation",
                "awaiting_checkpoint_path",
                "ultralytics",
                "ultralytics_masks",
                ["maize2", "maize4", "maize6"],
                ["maize2", "maize4", "maize6"],
            ),
            _model(
                "mask-rcnn-r50-fpn-v72-instance",
                "7.2-pending",
                "mask_rcnn_r50_fpn",
                "maize_instance_segmentation",
                "awaiting_checkpoint_path",
                "torchvision",
                "torchvision_masks",
                ["maize2", "maize4", "maize6"],
                ["maize2", "maize4", "maize6"],
            ),
        ],
    }


def _model(
    model_id: str,
    version: str,
    family: str,
    task: str,
    status: str,
    runtime: str,
    output_adapter: str,
    class_names: list[str],
    target_classes: list[str],
) -> dict[str, object]:
    return {
        "id": model_id,
        "version": version,
        "family": family,
        "task": task,
        "status": status,
        "class_names": class_names,
        "target_classes": target_classes,
        "input_size": [640, 640],
        "dataset_version": "maizemask-v7.2",
        "runtime": {"kind": runtime, "output_adapter": output_adapter},
        "preprocessing": {
            "color_space": "rgb",
            "resize_mode": "stretch",
            "interpolation": "bilinear",
            "value_scale": 1.0 / 255.0,
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
        },
        "artifacts": [],
    }
