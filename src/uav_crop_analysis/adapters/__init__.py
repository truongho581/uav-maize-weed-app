"""Lazy adapter exports keep optional I/O dependencies outside core imports."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .image_metadata import PillowExifReader
    from .job_sqlite import SQLiteAnalysisJobRepository
    from .memory import InMemoryMissionRepository
    from .model_catalog import RegistryModelCatalog
    from .nodeodm import NodeOdmOrthomosaicEngine
    from .preview_mosaic import LanePreviewMosaicBuilder
    from .rasterio_geospatial import RasterioGeoRaster
    from .report_export import PortableMissionReportExporter
    from .sqlite import SQLiteMissionRepository
    from .spatial_sqlite import SQLiteSpatialProductRepository
    from .telemetry_csv import CsvTelemetryReader

__all__ = [
    "CsvTelemetryReader",
    "InMemoryMissionRepository",
    "LATEST_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "LanePreviewMosaicBuilder",
    "NodeOdmOrthomosaicEngine",
    "PillowExifReader",
    "RegistryModelCatalog",
    "RasterioGeoRaster",
    "PortableMissionReportExporter",
    "SQLiteAnalysisJobRepository",
    "SQLiteMissionRepository",
    "SQLiteSpatialProductRepository",
    "load_mission_manifest",
    "write_mission_manifest",
]


def __getattr__(name: str) -> Any:
    if name == "CsvTelemetryReader":
        from .telemetry_csv import CsvTelemetryReader

        return CsvTelemetryReader
    if name == "InMemoryMissionRepository":
        from .memory import InMemoryMissionRepository

        return InMemoryMissionRepository
    if name == "LATEST_SCHEMA_VERSION":
        from .sqlite import LATEST_SCHEMA_VERSION

        return LATEST_SCHEMA_VERSION
    if name == "MANIFEST_SCHEMA_VERSION":
        from .manifest import MANIFEST_SCHEMA_VERSION

        return MANIFEST_SCHEMA_VERSION
    if name == "LanePreviewMosaicBuilder":
        from .preview_mosaic import LanePreviewMosaicBuilder

        return LanePreviewMosaicBuilder
    if name == "NodeOdmOrthomosaicEngine":
        from .nodeodm import NodeOdmOrthomosaicEngine

        return NodeOdmOrthomosaicEngine
    if name == "PillowExifReader":
        from .image_metadata import PillowExifReader

        return PillowExifReader
    if name == "RegistryModelCatalog":
        from .model_catalog import RegistryModelCatalog

        return RegistryModelCatalog
    if name == "RasterioGeoRaster":
        from .rasterio_geospatial import RasterioGeoRaster

        return RasterioGeoRaster
    if name == "PortableMissionReportExporter":
        from .report_export import PortableMissionReportExporter

        return PortableMissionReportExporter
    if name == "SQLiteAnalysisJobRepository":
        from .job_sqlite import SQLiteAnalysisJobRepository

        return SQLiteAnalysisJobRepository
    if name == "SQLiteMissionRepository":
        from .sqlite import SQLiteMissionRepository

        return SQLiteMissionRepository
    if name == "SQLiteSpatialProductRepository":
        from .spatial_sqlite import SQLiteSpatialProductRepository

        return SQLiteSpatialProductRepository
    if name in {"load_mission_manifest", "write_mission_manifest"}:
        from .manifest import load_mission_manifest, write_mission_manifest

        return {
            "load_mission_manifest": load_mission_manifest,
            "write_mission_manifest": write_mission_manifest,
        }[name]
    raise AttributeError(name)
