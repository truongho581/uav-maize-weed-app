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
    WEED_MASK = "weed_mask"
    PROBABILITY = "probability"
    OVERLAY = "overlay"


@dataclass(frozen=True, slots=True)
class ResultImageEntry:
    image_id: str
    source_path: Path
    probability_path: Path
    mask_path: Path
    width: int
    height: int
    weed_coverage_percent: float
    tile_count: int


def result_entries(job: AnalysisJob) -> tuple[ResultImageEntry, ...]:
    if job.status is not JobStatus.COMPLETED or job.result is None:
        return ()
    entries = []
    for summary in job.result.image_summaries:
        payload: dict[str, Any] = dict(summary)
        image_id = str(payload["image_id"])
        entries.append(
            ResultImageEntry(
                image_id=image_id,
                source_path=Path(str(payload["source_path"])),
                probability_path=job.result.artifact_dir
                / f"{image_id}.weed_probability.npy",
                mask_path=job.result.artifact_dir / f"{image_id}.weed_mask.png",
                width=int(payload["width"]),
                height=int(payload["height"]),
                weed_coverage_percent=float(payload["weed_coverage_percent"]),
                tile_count=int(payload["tile_count"]),
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
    elif mode is LayerMode.WEED_MASK:
        mask = _load_mask(entry)
        rgb = np.zeros((entry.height, entry.width, 3), dtype=np.uint8)
        rgb[mask] = (214, 74, 58)
    elif mode is LayerMode.PROBABILITY:
        rgb = _probability_colors(_load_probability(entry))
    else:
        original = _load_original(entry)
        mask = _load_mask(entry)
        rgb = original.astype(np.float32)
        color = np.array((214, 74, 58), dtype=np.float32)
        rgb[mask] = rgb[mask] * (1.0 - opacity) + color * opacity
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


def _qimage(rgb: NDArray[np.uint8]) -> QImage:
    height, width, _ = rgb.shape
    return QImage(
        rgb.data,
        width,
        height,
        int(rgb.strides[0]),
        QImage.Format.Format_RGB888,
    ).copy()
