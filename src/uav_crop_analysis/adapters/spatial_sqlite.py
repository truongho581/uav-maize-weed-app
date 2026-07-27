"""SQLite persistence for geospatial products and provenance."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from uav_crop_analysis.adapters.sqlite import SQLiteMissionRepository
from uav_crop_analysis.errors import PersistenceError
from uav_crop_analysis.geospatial.models import (
    GeoRasterMetadata,
    SpatialAccuracy,
    SpatialProduct,
    SpatialProductKind,
)


class SQLiteSpatialProductRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        SQLiteMissionRepository(self.database_path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def add(self, product: SpatialProduct) -> None:
        try:
            with self._connection() as connection, connection:
                connection.execute(
                    "INSERT INTO spatial_products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    _values(product),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"failed to add spatial product: {product.product_id}"
            ) from exc

    def get(self, product_id: str) -> SpatialProduct | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM spatial_products WHERE product_id = ?",
                (product_id,),
            ).fetchone()
        return _from_row(row) if row is not None else None

    def list_for_mission(self, mission_id: str) -> tuple[SpatialProduct, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM spatial_products
                WHERE mission_id = ?
                ORDER BY created_at DESC, product_id DESC
                """,
                (mission_id,),
            ).fetchall()
        return tuple(_from_row(row) for row in rows)


def _raster_to_dict(metadata: GeoRasterMetadata | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    return {
        "crs": metadata.crs,
        "transform": metadata.transform,
        "width": metadata.width,
        "height": metadata.height,
        "bounds": metadata.bounds,
        "resolution": metadata.resolution,
        "nodata": metadata.nodata,
    }


def _values(product: SpatialProduct) -> tuple[object, ...]:
    raster = _raster_to_dict(product.raster)
    return (
        product.product_id,
        product.mission_id,
        product.kind.value,
        product.accuracy.value,
        str(product.path),
        str(product.preview_path),
        product.created_at.isoformat(),
        json.dumps(raster, sort_keys=True) if raster else None,
        product.source_product_id,
        product.source_job_id,
        json.dumps(dict(product.provenance), sort_keys=True),
    )


def _from_row(row: sqlite3.Row) -> SpatialProduct:
    payload = json.loads(row["raster_json"]) if row["raster_json"] else None
    raster = (
        GeoRasterMetadata(
            crs=payload["crs"],
            transform=tuple(payload["transform"]),
            width=int(payload["width"]),
            height=int(payload["height"]),
            bounds=tuple(payload["bounds"]),
            resolution=tuple(payload["resolution"]),
            nodata=payload["nodata"],
        )
        if payload
        else None
    )
    return SpatialProduct(
        product_id=row["product_id"],
        mission_id=row["mission_id"],
        kind=SpatialProductKind(row["kind"]),
        accuracy=SpatialAccuracy(row["accuracy"]),
        path=Path(row["path"]),
        preview_path=Path(row["preview_path"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        raster=raster,
        source_product_id=row["source_product_id"],
        source_job_id=row["source_job_id"],
        provenance=json.loads(row["provenance_json"]),
    )
