"""Detected semantic weed regions presented by the map workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt

from uav_crop_analysis.geospatial import SpatialProduct
from uav_crop_analysis.jobs import AnalysisJob, JobStatus

ModelIndex = QModelIndex | QPersistentModelIndex


@dataclass(frozen=True, slots=True)
class WeedRegion:
    region_id: int
    pixel_count: int
    area_m2: float | None
    coverage_percent: float
    centroid_pixel: tuple[float, float]
    centroid_map: tuple[float, float] | None
    bounds_pixel: tuple[float, float, float, float]


class WeedRegionTableModel(QAbstractTableModel):
    HEADERS = ("Vùng", "Diện tích", "Tỷ lệ", "Tâm vùng", "Kích thước")

    def __init__(self) -> None:
        super().__init__()
        self._rows: tuple[WeedRegion, ...] = ()

    @property
    def rows(self) -> tuple[WeedRegion, ...]:
        return self._rows

    def set_rows(self, rows: tuple[WeedRegion, ...]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def region_at(self, row: int) -> WeedRegion | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: ModelIndex, role: int = 0) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        region = self._rows[index.row()]
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        x1, y1, x2, y2 = region.bounds_pixel
        centroid = (
            f"X {region.centroid_map[0]:.3f}, Y {region.centroid_map[1]:.3f}"
            if region.centroid_map is not None
            else f"x {region.centroid_pixel[0]:.0f}, y {region.centroid_pixel[1]:.0f}"
        )
        values = (
            f"Cỏ dại {region.region_id}",
            f"{region.area_m2:.3f} m²"
            if region.area_m2 is not None
            else f"{region.pixel_count:,} px",
            f"{region.coverage_percent:.3f}%",
            centroid,
            f"{x2 - x1:.0f} × {y2 - y1:.0f} px",
        )
        return values[index.column()]


def extract_weed_regions(
    product: SpatialProduct,
    jobs: tuple[AnalysisJob, ...],
    *,
    min_area_m2: float = 0.02,
    limit: int = 500,
) -> tuple[tuple[WeedRegion, ...], int, float | None]:
    """Extract connected semantic areas on a bounded preview-sized mask."""
    completed, summary = _latest_summary(product, jobs)
    if completed is None or completed.result is None or summary is None:
        return (), 0, None
    image_id = str(summary.get("image_id", ""))
    mask_path = completed.result.artifact_dir / f"{image_id}.weed_mask.png"
    if not mask_path.is_file():
        return (), int(summary.get("weed_pixels", 0)), None
    with Image.open(mask_path) as source:
        original_width, original_height = source.size
        mask_image = source.convert("L")
        mask_image.thumbnail((2048, 2048), Image.Resampling.NEAREST)
        mask = np.asarray(mask_image, dtype=np.uint8)
    binary = np.ascontiguousarray(mask > 0, dtype=np.uint8)
    count, _, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    scale_x = original_width / max(mask.shape[1], 1)
    scale_y = original_height / max(mask.shape[0], 1)
    pixel_area = None
    if product.raster is not None:
        pixel_area = abs(product.raster.resolution[0] * product.raster.resolution[1])
    regions: list[WeedRegion] = []
    for label in range(1, count):
        left, top, width, height, sampled_pixels = (int(value) for value in stats[label])
        pixel_count = round(sampled_pixels * scale_x * scale_y)
        area_m2 = pixel_count * pixel_area if pixel_area is not None else None
        if area_m2 is not None and area_m2 < min_area_m2:
            continue
        centroid_x = float(centroids[label][0] * scale_x)
        centroid_y = float(centroids[label][1] * scale_y)
        centroid_map = None
        if product.raster is not None:
            a, b, c, d, e, f = product.raster.transform
            centroid_map = (
                a * centroid_x + b * centroid_y + c,
                d * centroid_x + e * centroid_y + f,
            )
        regions.append(
            WeedRegion(
                region_id=label,
                pixel_count=pixel_count,
                area_m2=area_m2,
                coverage_percent=100.0 * pixel_count / (original_width * original_height),
                centroid_pixel=(centroid_x, centroid_y),
                centroid_map=centroid_map,
                bounds_pixel=(
                    left * scale_x,
                    top * scale_y,
                    (left + width) * scale_x,
                    (top + height) * scale_y,
                ),
            )
        )
    regions.sort(key=lambda item: item.pixel_count, reverse=True)
    weed_pixels = int(summary.get("weed_pixels", sum(item.pixel_count for item in regions)))
    weed_coverage = float(summary.get("weed_coverage_percent", 0.0))
    return tuple(regions[:limit]), weed_pixels, weed_coverage


def extract_class_metrics(
    product: SpatialProduct,
    jobs: tuple[AnalysisJob, ...],
    class_name: str,
) -> tuple[int, float | None]:
    """Return pixel count and coverage for one semantic class on a spatial product."""
    _completed, summary = _latest_summary(product, jobs)
    if summary is None:
        return 0, None
    pixels = summary.get(f"{class_name}_pixels")
    coverage = summary.get(f"{class_name}_coverage_percent")
    class_pixels = summary.get("class_pixels")
    class_coverage = summary.get("class_coverage_percent")
    if not isinstance(pixels, int) and isinstance(class_pixels, dict):
        pixels = class_pixels.get(class_name)
    if not isinstance(coverage, (int, float)) and isinstance(class_coverage, dict):
        coverage = class_coverage.get(class_name)
    return (
        int(pixels) if isinstance(pixels, int) else 0,
        float(coverage) if isinstance(coverage, (int, float)) else None,
    )


def _latest_summary(
    product: SpatialProduct,
    jobs: tuple[AnalysisJob, ...],
) -> tuple[AnalysisJob | None, dict[str, Any] | None]:
    completed = next(
        (job for job in reversed(jobs) if job.status is JobStatus.COMPLETED and job.result),
        None,
    )
    if completed is None or completed.result is None:
        return None, None
    summary = next(
        (
            dict(item)
            for item in completed.result.image_summaries
            if Path(str(item.get("source_path", ""))).resolve() == product.path
        ),
        dict(completed.result.image_summaries[0])
        if completed.result.image_summaries
        else None,
    )
    return completed, summary
