"""Business metrics derived from normalized segmentation contracts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from uav_crop_analysis.errors import InferenceInputError
from uav_crop_analysis.inference.contracts import InstanceBatchPrediction


@dataclass(frozen=True, slots=True)
class MaizeMetrics:
    instance_count: int
    canopy_pixels: int
    canopy_coverage_percent: float
    footprint_area_m2: float | None
    canopy_area_m2: float | None
    density_per_m2: float | None
    mean_canopy_area_m2: float | None
    stage_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class WeedGridCell:
    row: int
    column: int
    density: float
    high_risk: bool


@dataclass(frozen=True, slots=True)
class WeedMetrics:
    weed_pixels: int
    coverage_percent: float
    area_m2: float | None
    grid_rows: int
    grid_columns: int
    cells: tuple[WeedGridCell, ...]


def summarize_maize_instances(
    prediction: InstanceBatchPrediction,
    *,
    gsd_cm_per_px: float | None = None,
) -> MaizeMetrics:
    height, width = prediction.image_size_hw
    if any("weed" in item.class_name.casefold() for item in prediction.instances):
        raise InferenceInputError("weed must not be included in maize instance metrics")
    canopy = np.zeros((height, width), dtype=np.bool_)
    for instance in prediction.instances:
        canopy |= instance.mask
    canopy_pixels = int(canopy.sum())
    total_pixels = height * width
    pixel_area_m2 = _pixel_area_m2(gsd_cm_per_px)
    footprint_area = total_pixels * pixel_area_m2 if pixel_area_m2 is not None else None
    canopy_area = canopy_pixels * pixel_area_m2 if pixel_area_m2 is not None else None
    count = len(prediction.instances)
    density = count / footprint_area if footprint_area else None
    mean_area = canopy_area / count if canopy_area is not None and count else None
    return MaizeMetrics(
        instance_count=count,
        canopy_pixels=canopy_pixels,
        canopy_coverage_percent=round(100.0 * canopy_pixels / total_pixels, 6),
        footprint_area_m2=_rounded(footprint_area),
        canopy_area_m2=_rounded(canopy_area),
        density_per_m2=_rounded(density),
        mean_canopy_area_m2=_rounded(mean_area),
        stage_counts=dict(sorted(Counter(item.class_name for item in prediction.instances).items())),
    )


def summarize_weed_mask(
    weed_mask: NDArray[np.bool_],
    *,
    gsd_cm_per_px: float | None = None,
    grid_shape: tuple[int, int] = (10, 10),
    high_risk_threshold: float = 0.3,
) -> WeedMetrics:
    if weed_mask.dtype != np.bool_ or weed_mask.ndim != 2:
        raise InferenceInputError("weed mask must be a bool HxW array")
    rows, columns = grid_shape
    if rows < 1 or columns < 1:
        raise ValueError("grid dimensions must be positive")
    if not 0.0 <= high_risk_threshold <= 1.0:
        raise ValueError("high risk threshold must be in [0, 1]")
    weed_pixels = int(weed_mask.sum())
    pixel_area_m2 = _pixel_area_m2(gsd_cm_per_px)
    y_edges = np.linspace(0, weed_mask.shape[0], rows + 1, dtype=np.intp)
    x_edges = np.linspace(0, weed_mask.shape[1], columns + 1, dtype=np.intp)
    cells = []
    for row in range(rows):
        for column in range(columns):
            cell = weed_mask[
                y_edges[row] : y_edges[row + 1],
                x_edges[column] : x_edges[column + 1],
            ]
            density = float(cell.mean()) if cell.size else 0.0
            cells.append(
                WeedGridCell(
                    row=row,
                    column=column,
                    density=round(density, 6),
                    high_risk=density >= high_risk_threshold,
                )
            )
    return WeedMetrics(
        weed_pixels=weed_pixels,
        coverage_percent=round(100.0 * weed_pixels / weed_mask.size, 6),
        area_m2=_rounded(weed_pixels * pixel_area_m2 if pixel_area_m2 is not None else None),
        grid_rows=rows,
        grid_columns=columns,
        cells=tuple(cells),
    )


def _pixel_area_m2(gsd_cm_per_px: float | None) -> float | None:
    if gsd_cm_per_px is None:
        return None
    if gsd_cm_per_px <= 0:
        raise ValueError("GSD must be positive")
    return (gsd_cm_per_px / 100.0) ** 2


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
