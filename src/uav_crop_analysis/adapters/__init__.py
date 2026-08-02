"""Lazy adapter exports keep optional I/O dependencies outside core imports."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .image_metadata import PillowExifReader
    from .job_sqlite import SQLiteAnalysisJobRepository
    from .memory import InMemoryMissionRepository
    from .mission_plan_export import GreenEyeMissionBundleExporter, QGroundControlPlanWriter
    from .mission_bundle_media import has_greeneye_bundle_media, load_greeneye_bundle_media
    from .model_catalog import RegistryModelCatalog
    from .nodeodm import DockerManagedNodeOdmEngine, DockerNodeOdmRuntime
    from .planning_json import JsonMissionPlanRepository
    from .preview_mosaic import LanePreviewMosaicBuilder
    from .rasterio_geospatial import RasterioGeoRaster
    from .report_export import PortableMissionReportExporter
    from .sqlite import SQLiteMissionRepository
    from .spatial_sqlite import SQLiteSpatialProductRepository
    from .telemetry_csv import CsvTelemetryReader

__all__ = [
    "CsvTelemetryReader",
    "GreenEyeMissionBundleExporter",
    "has_greeneye_bundle_media",
    "InMemoryMissionRepository",
    "JsonMissionPlanRepository",
    "LATEST_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "LanePreviewMosaicBuilder",
    "DockerManagedNodeOdmEngine",
    "DockerNodeOdmRuntime",
    "PillowExifReader",
    "QGroundControlPlanWriter",
    "RegistryModelCatalog",
    "RasterioGeoRaster",
    "PortableMissionReportExporter",
    "SQLiteAnalysisJobRepository",
    "SQLiteMissionRepository",
    "SQLiteSpatialProductRepository",
    "load_mission_manifest",
    "load_greeneye_bundle_media",
    "write_mission_manifest",
]


def __getattr__(name: str) -> Any:
    if name in {"GreenEyeMissionBundleExporter", "QGroundControlPlanWriter"}:
        from .mission_plan_export import (
            GreenEyeMissionBundleExporter,
            QGroundControlPlanWriter,
        )

        return {
            "GreenEyeMissionBundleExporter": GreenEyeMissionBundleExporter,
            "QGroundControlPlanWriter": QGroundControlPlanWriter,
        }[name]
    if name in {"has_greeneye_bundle_media", "load_greeneye_bundle_media"}:
        from .mission_bundle_media import (
            has_greeneye_bundle_media,
            load_greeneye_bundle_media,
        )

        return {
            "has_greeneye_bundle_media": has_greeneye_bundle_media,
            "load_greeneye_bundle_media": load_greeneye_bundle_media,
        }[name]
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
    if name in {"DockerManagedNodeOdmEngine", "DockerNodeOdmRuntime"}:
        from .nodeodm import DockerManagedNodeOdmEngine, DockerNodeOdmRuntime

        return {
            "DockerManagedNodeOdmEngine": DockerManagedNodeOdmEngine,
            "DockerNodeOdmRuntime": DockerNodeOdmRuntime,
        }[name]
    if name == "PillowExifReader":
        from .image_metadata import PillowExifReader

        return PillowExifReader
    if name == "JsonMissionPlanRepository":
        from .planning_json import JsonMissionPlanRepository

        return JsonMissionPlanRepository
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
