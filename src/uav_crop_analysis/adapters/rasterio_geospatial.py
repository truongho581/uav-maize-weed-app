"""Rasterio-backed GeoTIFF validation, export, and preview rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from uav_crop_analysis.errors import GeospatialError
from uav_crop_analysis.geospatial.models import GeoRasterMetadata


class RasterioGeoRaster:
    def inspect(self, path: Path) -> GeoRasterMetadata:
        rasterio = _rasterio()
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise GeospatialError(f"GeoTIFF does not exist: {source}")
        try:
            with rasterio.open(source) as dataset:
                if dataset.crs is None:
                    raise GeospatialError("raster has no coordinate reference system")
                transform = dataset.transform
                if transform.is_identity:
                    raise GeospatialError("raster has an identity transform")
                return GeoRasterMetadata(
                    crs=dataset.crs.to_string(),
                    transform=(
                        float(transform.a),
                        float(transform.b),
                        float(transform.c),
                        float(transform.d),
                        float(transform.e),
                        float(transform.f),
                    ),
                    width=dataset.width,
                    height=dataset.height,
                    bounds=(
                        float(dataset.bounds.left),
                        float(dataset.bounds.bottom),
                        float(dataset.bounds.right),
                        float(dataset.bounds.top),
                    ),
                    resolution=(float(dataset.res[0]), float(dataset.res[1])),
                    nodata=float(dataset.nodata) if dataset.nodata is not None else None,
                )
        except GeospatialError:
            raise
        except Exception as exc:
            raise GeospatialError(f"cannot inspect geospatial raster: {source}") from exc

    def write_scalar_like(
        self,
        reference_path: Path,
        values: NDArray[np.float32] | NDArray[np.uint8],
        output_path: Path,
        *,
        layer_name: str,
    ) -> GeoRasterMetadata:
        rasterio = _rasterio()
        reference = Path(reference_path).expanduser().resolve()
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.tmp{output.suffix}")
        try:
            with rasterio.open(reference) as source:
                if values.shape != (source.height, source.width):
                    raise GeospatialError(
                        "spatial layer shape does not match orthomosaic grid"
                    )
                if source.crs is None or source.transform.is_identity:
                    raise GeospatialError("reference raster is not georeferenced")
                profile: dict[str, Any] = source.profile.copy()
                profile.update(
                    driver="GTiff",
                    count=1,
                    dtype=str(values.dtype),
                    nodata=None,
                    compress="deflate",
                    predictor=3 if values.dtype == np.float32 else 2,
                )
                with rasterio.open(temporary, "w", **profile) as target:
                    target.write(values, 1)
                    target.write_mask(source.dataset_mask())
                    target.update_tags(
                        product="UAV Crop Analysis",
                        layer=layer_name,
                    )
            temporary.replace(output)
        except GeospatialError:
            temporary.unlink(missing_ok=True)
            raise
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise GeospatialError(f"cannot write GeoTIFF: {output}") from exc
        return self.inspect(output)

    def read_valid_mask(self, path: Path) -> NDArray[np.uint8]:
        rasterio = _rasterio()
        source = Path(path).expanduser().resolve()
        try:
            with rasterio.open(source) as dataset:
                return np.ascontiguousarray(dataset.dataset_mask() > 0, dtype=np.uint8)
        except Exception as exc:
            raise GeospatialError(f"cannot read raster valid-data mask: {source}") from exc

    def write_risk_geojson_like(
        self,
        reference_path: Path,
        probability: NDArray[np.float32],
        output_path: Path,
        *,
        threshold: float,
        properties: dict[str, object],
    ) -> None:
        rasterio = _rasterio()
        from rasterio.features import shapes
        from rasterio.warp import transform_geom

        reference = Path(reference_path).expanduser().resolve()
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.tmp{output.suffix}")
        try:
            with rasterio.open(reference) as dataset:
                if probability.shape != (dataset.height, dataset.width):
                    raise GeospatialError(
                        "risk layer shape does not match orthomosaic grid"
                    )
                if dataset.crs is None or dataset.transform.is_identity:
                    raise GeospatialError("reference raster is not georeferenced")
                valid = dataset.dataset_mask() > 0
                risk = np.ascontiguousarray(probability >= threshold, dtype=np.uint8)
                features = []
                for geometry, value in shapes(
                    risk,
                    mask=np.logical_and(valid, risk > 0),
                    transform=dataset.transform,
                ):
                    if int(value) != 1:
                        continue
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": transform_geom(
                                dataset.crs,
                                "EPSG:4326",
                                geometry,
                                precision=7,
                            ),
                            "properties": {
                                **properties,
                                "threshold": threshold,
                            },
                        }
                    )
                payload = {
                    "type": "FeatureCollection",
                    "features": features,
                    "uav_crop_analysis": {
                        "source_crs": dataset.crs.to_string(),
                        "coordinates": "EPSG:4326",
                    },
                }
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            temporary.replace(output)
        except GeospatialError:
            temporary.unlink(missing_ok=True)
            raise
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise GeospatialError(f"cannot write risk GeoJSON: {output}") from exc

    def render_rgb_preview(self, path: Path, output_path: Path) -> None:
        rgb = self._read_preview_rgb(path)
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgb, mode="RGB").save(output)

    def render_heatmap_preview(
        self,
        reference_path: Path,
        probability: NDArray[np.float32],
        output_path: Path,
    ) -> None:
        rgb = self._read_preview_rgb(reference_path)
        resized = np.asarray(
            Image.fromarray(probability, mode="F").resize(
                (rgb.shape[1], rgb.shape[0]),
                Image.Resampling.BILINEAR,
            ),
            dtype=np.float32,
        ).clip(0.0, 1.0)
        colors = _probability_colors(resized)
        alpha = (0.15 + 0.50 * resized)[..., None]
        alpha[resized[..., None] < 0.05] = 0.0
        overlay = np.ascontiguousarray(
            (rgb.astype(np.float32) * (1.0 - alpha) + colors * alpha).clip(0, 255),
            dtype=np.uint8,
        )
        preview = _with_heatmap_legend(Image.fromarray(overlay, mode="RGB"))
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        preview.save(output)

    @staticmethod
    def _read_preview_rgb(path: Path, max_size: int = 1600) -> NDArray[np.uint8]:
        rasterio = _rasterio()
        from rasterio.enums import Resampling

        source = Path(path).expanduser().resolve()
        try:
            with rasterio.open(source) as dataset:
                scale = min(1.0, max_size / max(dataset.width, dataset.height))
                out_height = max(1, round(dataset.height * scale))
                out_width = max(1, round(dataset.width * scale))
                indexes = list(range(1, min(dataset.count, 3) + 1))
                data = dataset.read(
                    indexes,
                    out_shape=(len(indexes), out_height, out_width),
                    resampling=Resampling.bilinear,
                )
        except Exception as exc:
            raise GeospatialError(f"cannot render raster preview: {source}") from exc
        if data.shape[0] == 1:
            data = np.repeat(data, 3, axis=0)
        elif data.shape[0] == 2:
            data = np.concatenate((data, data[:1]), axis=0)
        rgb = np.moveaxis(data[:3], 0, -1)
        if rgb.dtype == np.uint8:
            return np.ascontiguousarray(rgb)
        return _stretch_uint8(rgb)


def _rasterio() -> Any:
    try:
        import rasterio
    except ImportError as exc:
        raise GeospatialError("Rasterio is required for GeoTIFF products") from exc
    return rasterio


def _stretch_uint8(values: NDArray[Any]) -> NDArray[np.uint8]:
    output = np.zeros(values.shape, dtype=np.uint8)
    for channel in range(values.shape[2]):
        band = values[..., channel].astype(np.float32)
        finite = band[np.isfinite(band)]
        if not finite.size:
            continue
        low, high = np.percentile(finite, (2, 98))
        if high <= low:
            continue
        output[..., channel] = np.ascontiguousarray(
            ((band - low) / (high - low) * 255).clip(0, 255),
            dtype=np.uint8,
        )
    return output


def _probability_colors(probability: NDArray[np.float32]) -> NDArray[np.float32]:
    stops = np.array(
        ((35, 75, 142), (35, 150, 171), (238, 196, 67), (190, 50, 43)),
        dtype=np.float32,
    )
    scaled = probability * (len(stops) - 1)
    lower = np.floor(scaled).astype(np.intp)
    upper = np.minimum(lower + 1, len(stops) - 1)
    fraction = (scaled - lower)[..., None]
    return stops[lower] * (1.0 - fraction) + stops[upper] * fraction


def _with_heatmap_legend(image: Image.Image) -> Image.Image:
    legend_height = 54
    canvas = Image.new("RGB", (image.width, image.height + legend_height), "#F4F6F5")
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    bar_left = 16
    bar_top = image.height + 12
    bar_width = max(20, min(360, image.width - 32))
    probability = np.linspace(0.0, 1.0, bar_width, dtype=np.float32)[None, :]
    bar = np.ascontiguousarray(_probability_colors(probability), dtype=np.uint8)
    bar = np.repeat(bar, 14, axis=0)
    canvas.paste(Image.fromarray(bar, mode="RGB"), (bar_left, bar_top))
    draw.rectangle(
        (bar_left, bar_top, bar_left + bar_width, bar_top + 14),
        outline="#34413B",
    )
    draw.text((bar_left, bar_top + 19), "0", fill="#18211D")
    draw.text((bar_left + bar_width // 2 - 8, bar_top + 19), "0.5", fill="#18211D")
    draw.text((bar_left + bar_width - 8, bar_top + 19), "1", fill="#18211D")
    if image.width >= 220:
        draw.text(
            (bar_left + bar_width + 14, bar_top + 1),
            "Weed probability",
            fill="#18211D",
        )
    return canvas
