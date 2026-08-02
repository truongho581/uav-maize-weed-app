"""Framework-neutral geospatial product contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from uav_crop_analysis.errors import GeospatialError


class SpatialProductKind(str, Enum):
    PREVIEW_MOSAIC = "preview_mosaic"
    ORTHOMOSAIC = "orthomosaic"
    WEED_HEATMAP = "weed_heatmap"


class SpatialAccuracy(str, Enum):
    PREVIEW_ONLY = "preview_only"
    GEOREFERENCED = "georeferenced"


@dataclass(frozen=True, slots=True)
class GeoRasterMetadata:
    crs: str
    transform: tuple[float, float, float, float, float, float]
    width: int
    height: int
    bounds: tuple[float, float, float, float]
    resolution: tuple[float, float]
    nodata: float | None = None

    def __post_init__(self) -> None:
        if not self.crs.strip():
            raise GeospatialError("georeferenced raster requires a CRS")
        if self.width < 1 or self.height < 1:
            raise GeospatialError("georeferenced raster dimensions must be positive")
        a, b, _, d, e, _ = self.transform
        if abs(a * e - b * d) < 1e-15:
            raise GeospatialError("georeferenced raster transform is not invertible")
        if self.transform == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0):
            raise GeospatialError("georeferenced raster transform must not be identity")
        if min(abs(self.resolution[0]), abs(self.resolution[1])) <= 0:
            raise GeospatialError("georeferenced raster resolution must be positive")


@dataclass(frozen=True, slots=True)
class SpatialProduct:
    product_id: str
    mission_id: str
    kind: SpatialProductKind
    accuracy: SpatialAccuracy
    path: Path
    preview_path: Path
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raster: GeoRasterMetadata | None = None
    source_product_id: str | None = None
    source_job_id: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.product_id.strip() or not self.mission_id.strip():
            raise GeospatialError("spatial product and mission IDs are required")
        object.__setattr__(self, "path", Path(self.path).expanduser().resolve())
        object.__setattr__(
            self,
            "preview_path",
            Path(self.preview_path).expanduser().resolve(),
        )
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise GeospatialError("spatial product timestamp must be timezone-aware")
        if self.accuracy is SpatialAccuracy.GEOREFERENCED and self.raster is None:
            raise GeospatialError("georeferenced product requires raster metadata")
        if self.kind is SpatialProductKind.PREVIEW_MOSAIC:
            if self.accuracy is not SpatialAccuracy.PREVIEW_ONLY or self.raster is not None:
                raise GeospatialError("preview mosaic must not claim georeferencing")
        elif self.accuracy is not SpatialAccuracy.GEOREFERENCED or self.raster is None:
            raise GeospatialError("spatial raster products must be georeferenced")
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))


@dataclass(frozen=True, slots=True)
class SpatialWorkspace:
    mission_id: str
    image_count: int
    geotagged_image_count: int
    altitude_image_count: int
    products: tuple[SpatialProduct, ...]
    orthomosaic_engine_configured: bool
    orthomosaic_engine_name: str = "NodeODM (Docker local)"
    orthomosaic_engine_location: str | None = None

    @property
    def geospatial_ready(self) -> bool:
        return self.image_count > 0 and self.geotagged_image_count == self.image_count
