"""Load and render published semantic artifacts for the Qt image viewer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from PySide6.QtGui import QImage

from uav_crop_analysis.errors import PipelineExecutionError
from uav_crop_analysis.jobs.models import AnalysisJob, JobStatus


class LayerMode(str, Enum):
    ORIGINAL = "original"
    SEMANTIC_MASK = "semantic_mask"
    WEED_MASK = "weed_mask"
    PROBABILITY = "probability"
    INSTANCE_MASK = "instance_mask"
    OVERLAY = "overlay"


@dataclass(frozen=True, slots=True)
class ResultImageEntry:
    image_id: str
    source_path: Path
    probability_path: Path
    mask_path: Path
    crop_probability_path: Path
    crop_mask_path: Path
    semantic_map_path: Path
    width: int
    height: int
    crop_coverage_percent: float
    weed_coverage_percent: float
    tile_count: int
    analysis_task: str = "semantic_segmentation"
    maize_instance_count: int | None = None
    instance_mask_path: Path | None = None
    instance_overlay_path: Path | None = None


def result_entries(job: AnalysisJob) -> tuple[ResultImageEntry, ...]:
    if job.status is not JobStatus.COMPLETED or job.result is None:
        return ()
    entries = []
    for summary in job.result.image_summaries:
        payload: dict[str, Any] = dict(summary)
        image_id = str(payload["image_id"])
        task = str(payload.get("analysis_task", "semantic_segmentation"))
        entries.append(
            ResultImageEntry(
                image_id=image_id,
                source_path=Path(str(payload["source_path"])),
                probability_path=job.result.artifact_dir
                / f"{image_id}.weed_probability.npy",
                mask_path=job.result.artifact_dir / f"{image_id}.weed_mask.png",
                crop_probability_path=job.result.artifact_dir
                / f"{image_id}.crop_probability.npy",
                crop_mask_path=job.result.artifact_dir / f"{image_id}.crop_mask.png",
                semantic_map_path=job.result.artifact_dir
                / f"{image_id}.semantic_classes.png",
                width=int(payload["width"]),
                height=int(payload["height"]),
                crop_coverage_percent=float(
                    payload.get(
                        "crop_coverage_percent",
                        payload.get("class_coverage_percent", {}).get("crop", 0.0),
                    )
                ),
                weed_coverage_percent=float(payload.get("weed_coverage_percent", 0.0)),
                tile_count=int(payload["tile_count"]),
                analysis_task=task,
                maize_instance_count=(
                    int(payload["maize_instance_count"])
                    if "maize_instance_count" in payload
                    else None
                ),
                instance_mask_path=(
                    job.result.artifact_dir / f"{image_id}.maize_instances.png"
                    if task == "maize_instance_segmentation"
                    else None
                ),
                instance_overlay_path=(
                    job.result.artifact_dir / f"{image_id}.maize_overlay.png"
                    if task == "maize_instance_segmentation"
                    else None
                ),
            )
        )
    return tuple(entries)


def render_layer(
    entry: ResultImageEntry,
    mode: LayerMode,
    *,
    opacity: float = 0.5,
) -> QImage:
    if not 0.0 <= opacity <= 1.0:
        raise ValueError("opacity must be in [0, 1]")
    if mode is LayerMode.ORIGINAL:
        rgb = _load_original(entry)
    elif entry.analysis_task == "maize_instance_segmentation":
        if mode is LayerMode.INSTANCE_MASK:
            rgb = _instance_colors(_load_instance_labels(entry))
        elif mode is LayerMode.OVERLAY:
            rgb = _load_instance_overlay(entry)
        else:
            raise PipelineExecutionError(f"layer is unavailable for maize instance output: {mode.value}")
    elif mode is LayerMode.SEMANTIC_MASK:
        rgb = _semantic_colors(_load_semantic_labels(entry))
    elif mode is LayerMode.WEED_MASK:
        mask = _load_mask(entry)
        rgb = np.zeros((entry.height, entry.width, 3), dtype=np.uint8)
        rgb[mask] = (214, 74, 58)
    elif mode is LayerMode.PROBABILITY:
        rgb = _probability_colors(_load_probability(entry))
    else:
        original = _load_original(entry)
        labels = _load_semantic_labels(entry)
        rgb = original.astype(np.float32)
        crop = labels == 1
        weed = labels == 2
        crop_color = np.array((34, 156, 91), dtype=np.float32)
        weed_color = np.array((214, 74, 58), dtype=np.float32)
        rgb[crop] = rgb[crop] * (1.0 - opacity) + crop_color * opacity
        rgb[weed] = rgb[weed] * (1.0 - opacity) + weed_color * opacity
        rgb = np.ascontiguousarray(rgb.clip(0, 255), dtype=np.uint8)
    return _qimage(rgb)


def _load_original(entry: ResultImageEntry) -> NDArray[np.uint8]:
    try:
        with Image.open(entry.source_path) as image:
            data = np.asarray(image.convert("RGB"), dtype=np.uint8)
    except OSError as exc:
        raise PipelineExecutionError(
            f"cannot open result source image: {entry.source_path}"
        ) from exc
    if data.shape[:2] != (entry.height, entry.width):
        raise PipelineExecutionError("source image shape does not match result metadata")
    return np.ascontiguousarray(data)


def _load_mask(entry: ResultImageEntry) -> NDArray[np.bool_]:
    try:
        with Image.open(entry.mask_path) as image:
            mask = np.asarray(image.convert("L"), dtype=np.uint8) > 0
    except OSError as exc:
        raise PipelineExecutionError(f"cannot open weed mask: {entry.mask_path}") from exc
    if mask.shape != (entry.height, entry.width):
        raise PipelineExecutionError("weed mask shape does not match result metadata")
    return np.ascontiguousarray(mask)


def _load_semantic_labels(entry: ResultImageEntry) -> NDArray[np.uint8]:
    if entry.semantic_map_path.is_file():
        try:
            with Image.open(entry.semantic_map_path) as image:
                labels = np.asarray(image.convert("L"), dtype=np.uint8)
        except OSError as exc:
            raise PipelineExecutionError(
                f"cannot open semantic class map: {entry.semantic_map_path}"
            ) from exc
        if labels.shape != (entry.height, entry.width):
            raise PipelineExecutionError(
                "semantic class map shape does not match result metadata"
            )
        return np.ascontiguousarray(labels)
    labels = np.zeros((entry.height, entry.width), dtype=np.uint8)
    labels[_load_mask(entry)] = 2
    return labels


def _semantic_colors(labels: NDArray[np.uint8]) -> NDArray[np.uint8]:
    rgb = np.zeros((*labels.shape, 3), dtype=np.uint8)
    rgb[labels == 1] = (34, 156, 91)
    rgb[labels == 2] = (214, 74, 58)
    return rgb


def _load_probability(entry: ResultImageEntry) -> NDArray[np.float32]:
    try:
        probability = np.load(entry.probability_path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise PipelineExecutionError(
            f"cannot open weed probability: {entry.probability_path}"
        ) from exc
    if probability.shape != (entry.height, entry.width):
        raise PipelineExecutionError("weed probability shape does not match result metadata")
    return np.ascontiguousarray(probability.clip(0.0, 1.0), dtype=np.float32)


def _load_instance_labels(entry: ResultImageEntry) -> NDArray[np.uint8]:
    if entry.instance_mask_path is None:
        raise PipelineExecutionError("maize instance mask is unavailable")
    try:
        with Image.open(entry.instance_mask_path) as image:
            labels = np.asarray(image.convert("L"), dtype=np.uint8)
    except OSError as exc:
        raise PipelineExecutionError(
            f"cannot open maize instance mask: {entry.instance_mask_path}"
        ) from exc
    if labels.shape != (entry.height, entry.width):
        raise PipelineExecutionError("maize instance mask shape does not match result metadata")
    return np.ascontiguousarray(labels)


def _load_instance_overlay(entry: ResultImageEntry) -> NDArray[np.uint8]:
    if entry.instance_overlay_path is None:
        raise PipelineExecutionError("maize instance overlay is unavailable")
    try:
        with Image.open(entry.instance_overlay_path) as image:
            overlay = np.asarray(image.convert("RGB"), dtype=np.uint8)
    except OSError as exc:
        raise PipelineExecutionError(
            f"cannot open maize instance overlay: {entry.instance_overlay_path}"
        ) from exc
    if overlay.shape[:2] != (entry.height, entry.width):
        raise PipelineExecutionError("maize overlay shape does not match result metadata")
    return np.ascontiguousarray(overlay)


def _probability_colors(probability: NDArray[np.float32]) -> NDArray[np.uint8]:
    # Blue -> cyan -> yellow -> red gives readable low/mid/high probability bands.
    stops = np.array(
        ((35, 75, 142), (35, 150, 171), (238, 196, 67), (190, 50, 43)),
        dtype=np.float32,
    )
    scaled = probability * (len(stops) - 1)
    lower = np.floor(scaled).astype(np.intp)
    upper = np.minimum(lower + 1, len(stops) - 1)
    fraction = (scaled - lower)[..., None]
    colors = stops[lower] * (1.0 - fraction) + stops[upper] * fraction
    return np.ascontiguousarray(colors.clip(0, 255), dtype=np.uint8)


def _instance_colors(labels: NDArray[np.uint8]) -> NDArray[np.uint8]:
    colors = np.array(
        ((18, 28, 22), (62, 163, 94), (60, 128, 207), (222, 154, 49)),
        dtype=np.uint8,
    )
    clipped = np.minimum(labels, len(colors) - 1)
    return np.ascontiguousarray(colors[clipped], dtype=np.uint8)


def _qimage(rgb: NDArray[np.uint8]) -> QImage:
    height, width, _ = rgb.shape
    return QImage(
        rgb.data,
        width,
        height,
        int(rgb.strides[0]),
        QImage.Format.Format_RGB888,
    ).copy()
