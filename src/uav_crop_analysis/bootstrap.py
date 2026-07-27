"""Framework-neutral composition root shared by desktop, SDK, CLI, and API."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys

from uav_crop_analysis.adapters import (
    CsvTelemetryReader,
    LanePreviewMosaicBuilder,
    NodeOdmOrthomosaicEngine,
    PillowExifReader,
    PortableMissionReportExporter,
    RasterioGeoRaster,
    RegistryModelCatalog,
    SQLiteAnalysisJobRepository,
    SQLiteMissionRepository,
    SQLiteSpatialProductRepository,
)
from uav_crop_analysis.application import (
    AnalysisWorkspaceService,
    ImportMissionData,
    MissionDataWorkspaceService,
    MissionWorkspaceService,
)
from uav_crop_analysis.geospatial import SpatialWorkspaceService
from uav_crop_analysis.infrastructure import AppConfig, configure_logging
from uav_crop_analysis.inference.default_registry import ensure_default_registry
from uav_crop_analysis.jobs import AnalysisJobService
from uav_crop_analysis.reporting import MissionReportService


@dataclass(slots=True)
class ApplicationRuntime:
    """Application services with no dependency on a presentation framework."""

    config: AppConfig
    database_path: Path
    registry_path: Path
    missions: SQLiteMissionRepository
    jobs: SQLiteAnalysisJobRepository
    spatial_products: SQLiteSpatialProductRepository
    catalog: RegistryModelCatalog
    job_service: AnalysisJobService
    mission_workspace: MissionWorkspaceService
    data_workspace: MissionDataWorkspaceService
    analysis_workspace: AnalysisWorkspaceService
    spatial_workspace: SpatialWorkspaceService
    report_workspace: MissionReportService
    mission_import: ImportMissionData

    def shutdown(self) -> None:
        self.job_service.shutdown()


def build_runtime(
    database_path: str | Path | None = None,
    *,
    config: AppConfig | None = None,
    registry_path: str | Path | None = None,
    nodeodm_url: str | None = None,
) -> ApplicationRuntime:
    runtime_config = config or AppConfig.from_environment()
    runtime_config.paths.ensure_exists()
    configure_logging(runtime_config)
    database = Path(
        database_path
        or os.environ.get("UAV_CROP_DATABASE")
        or runtime_config.paths.data_dir / "app.db"
    ).expanduser().resolve()
    missions = SQLiteMissionRepository(database)
    jobs = SQLiteAnalysisJobRepository(database)
    job_service = AnalysisJobService(jobs)
    job_service.recover_interrupted()
    try:
        registry = resolve_registry_path(registry_path)
    except FileNotFoundError:
        if registry_path is not None or os.environ.get("UAV_CROP_MODEL_REGISTRY"):
            raise
        registry = ensure_default_registry(
            runtime_config.paths.config_dir / "model_inventory.json"
        )
    catalog = RegistryModelCatalog(registry)
    products = SQLiteSpatialProductRepository(database)
    analysis = AnalysisWorkspaceService(
        missions,
        job_service,
        catalog,
        registry,
        runtime_config.paths.data_dir / "results",
    )
    odm_url = (
        nodeodm_url
        if nodeodm_url is not None
        else os.environ.get("UAV_CROP_NODEODM_URL", "").strip()
    )
    return ApplicationRuntime(
        config=runtime_config,
        database_path=database,
        registry_path=registry,
        missions=missions,
        jobs=jobs,
        spatial_products=products,
        catalog=catalog,
        job_service=job_service,
        mission_workspace=MissionWorkspaceService(missions, jobs),
        data_workspace=MissionDataWorkspaceService(missions),
        analysis_workspace=analysis,
        spatial_workspace=SpatialWorkspaceService(
            missions,
            products,
            RasterioGeoRaster(),
            LanePreviewMosaicBuilder(),
            runtime_config.paths.data_dir / "spatial",
            analysis=analysis,
            orthomosaic_engine=(NodeOdmOrthomosaicEngine(odm_url) if odm_url else None),
        ),
        report_workspace=MissionReportService(
            missions,
            jobs,
            products,
            catalog,
            PortableMissionReportExporter(),
        ),
        mission_import=ImportMissionData(
            missions,
            PillowExifReader(),
            CsvTelemetryReader(),
        ),
    )


def resolve_registry_path(override: str | Path | None = None) -> Path:
    configured = override or os.environ.get("UAV_CROP_MODEL_REGISTRY")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "models/model_inventory.json")
    candidates.extend(
        (
            Path.cwd() / "models/model_inventory.json",
            Path(__file__).resolve().parents[2] / "models/model_inventory.json",
        )
    )
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.is_file():
            return resolved
    checked = ", ".join(str(path.expanduser()) for path in candidates)
    raise FileNotFoundError(f"model registry was not found; checked: {checked}")
