"""Compact presentation names for registered inference models."""

from __future__ import annotations


def display_model_name(model_id: str) -> str:
    """Return a concise UI label while preserving the internal model ID."""
    normalized = model_id.strip().lower().replace("_", "-")
    if normalized.startswith("segformer-b0-v72"):
        return "segformer-b0-v72"
    if normalized.startswith("yolov8-seg-v72"):
        return "yolov8-seg-v72"
    if normalized.startswith("mask-rcnn-r50-fpn-v72"):
        return "mask-rcnn-r50-v72"
    return model_id
