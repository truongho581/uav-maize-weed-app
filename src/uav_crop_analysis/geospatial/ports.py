"""Ports for spatial persistence, raster I/O, and orthomosaic engines."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from uav_crop_analysis.domain import ImageAsset, SurveyMission
from uav_crop_analysis.geospatial.models import GeoRasterMetadata, SpatialProduct


ProgressCallback = Callable[[float, str], None]


class SpatialProductRepository(Protocol):
    def add(self, product: SpatialProduct) -> None: ...

    def get(self, product_id: str) -> SpatialProduct | None: ...

    def list_for_mission(self, mission_id: str) -> tuple[SpatialProduct, ...]: ...


class GeoRasterPort(Protocol):
    def inspect(self, path: Path) -> GeoRasterMetadata: ...

    def write_scalar_like(
        self,
        reference_path: Path,
        values: NDArray[np.float32] | NDArray[np.uint8],
        output_path: Path,
        *,
        layer_name: str,
    ) -> GeoRasterMetadata: ...

    def render_rgb_preview(self, path: Path, output_path: Path) -> None: ...

    def render_heatmap_preview(
        self,
        reference_path: Path,
        probability: NDArray[np.float32],
        output_path: Path,
    ) -> None: ...

    def read_valid_mask(self, path: Path) -> NDArray[np.uint8]: ...

    def write_risk_geojson_like(
        self,
        reference_path: Path,
        probability: NDArray[np.float32],
        output_path: Path,
        *,
        threshold: float,
        properties: dict[str, object],
    ) -> None: ...


class OrthomosaicEngine(Protocol):
    def create(
        self,
        mission_id: str,
        image_paths: tuple[Path, ...],
        output_dir: Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> tuple[Path, dict[str, object]]: ...


class PreviewMosaicBuilder(Protocol):
    def build(
        self,
        mission: SurveyMission,
        images: Sequence[ImageAsset],
        output_path: Path,
    ) -> dict[str, object]: ...
