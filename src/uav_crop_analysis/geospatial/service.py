"""Mission-level preview, orthomosaic, semantic heatmap, and provenance workflow."""

from __future__ import annotations

from pathlib import Path
import shutil
from uuid import uuid4

import numpy as np
from PIL import Image

from uav_crop_analysis.application.analysis_workspace import (
    AnalysisModelOption,
    AnalysisRequest,
    AnalysisTask,
    AnalysisWorkspaceService,
)
from uav_crop_analysis.application.ports import MissionDataRepository
from uav_crop_analysis.domain import MissionId, SurveyMission
from uav_crop_analysis.errors import GeospatialError
from uav_crop_analysis.geospatial.models import (
    SpatialAccuracy,
    SpatialProduct,
    SpatialProductKind,
    SpatialWorkspace,
)
from uav_crop_analysis.geospatial.ports import (
    GeoRasterPort,
    OrthomosaicEngine,
    PreviewMosaicBuilder,
    ProgressCallback,
    SpatialProductRepository,
)
from uav_crop_analysis.inference.registry import sha256_file
from uav_crop_analysis.jobs.models import AnalysisInput, AnalysisJob, JobStatus


class SpatialWorkspaceService:
    def __init__(
        self,
        missions: MissionDataRepository,
        products: SpatialProductRepository,
        raster: GeoRasterPort,
        preview_builder: PreviewMosaicBuilder,
        output_root: str | Path,
        *,
        analysis: AnalysisWorkspaceService | None = None,
        orthomosaic_engine: OrthomosaicEngine | None = None,
    ) -> None:
        self._missions = missions
        self._products = products
        self._raster = raster
        self._preview_builder = preview_builder
        self._analysis = analysis
        self._engine = orthomosaic_engine
        self.output_root = Path(output_root).expanduser().resolve()

    @property
    def nodeodm_configured(self) -> bool:
        return self._engine is not None

    def get_workspace(self, mission_id: str) -> SpatialWorkspace | None:
        mission = self._missions.get(MissionId(mission_id))
        if mission is None:
            return None
        images = self._missions.list_image_assets(mission.mission_id)
        return SpatialWorkspace(
            mission_id=mission_id,
            image_count=len(images),
            geotagged_image_count=sum(item.position is not None for item in images),
            altitude_image_count=sum(
                item.relative_altitude_m is not None for item in images
            ),
            products=self._products.list_for_mission(mission_id),
            nodeodm_configured=self.nodeodm_configured,
        )

    def list_semantic_models(self) -> tuple[AnalysisModelOption, ...]:
        if self._analysis is None:
            return ()
        return self._analysis.list_models(AnalysisTask.SEMANTIC)

    def build_preview(self, mission_id: str) -> SpatialProduct:
        mission = self._require_mission(mission_id)
        images = self._missions.list_image_assets(mission.mission_id)
        product_id = f"preview-{uuid4().hex}"
        output = self.output_root / mission_id / product_id / "spatial-preview.png"
        provenance = self._preview_builder.build(mission, images, output)
        product = SpatialProduct(
            product_id=product_id,
            mission_id=mission_id,
            kind=SpatialProductKind.PREVIEW_MOSAIC,
            accuracy=SpatialAccuracy.PREVIEW_ONLY,
            path=output,
            preview_path=output,
            provenance=provenance,
        )
        self._products.add(product)
        return product

    def import_orthomosaic(
        self,
        mission_id: str,
        source_path: str | Path,
        *,
        provenance: dict[str, object] | None = None,
    ) -> SpatialProduct:
        self._require_mission(mission_id)
        source = Path(source_path).expanduser().resolve()
        metadata = self._raster.inspect(source)
        product_id = f"orthomosaic-{uuid4().hex}"
        directory = self.output_root / mission_id / product_id
        directory.mkdir(parents=True, exist_ok=True)
        managed = directory / "orthomosaic.tif"
        if source != managed:
            temporary = directory / ".orthomosaic.tmp.tif"
            shutil.copy2(source, temporary)
            temporary.replace(managed)
        preview = directory / "orthomosaic-preview.png"
        self._raster.render_rgb_preview(managed, preview)
        product = SpatialProduct(
            product_id=product_id,
            mission_id=mission_id,
            kind=SpatialProductKind.ORTHOMOSAIC,
            accuracy=SpatialAccuracy.GEOREFERENCED,
            path=managed,
            preview_path=preview,
            raster=metadata,
            provenance={
                "source_sha256": sha256_file(managed),
                **(provenance or {"engine": "external_import"}),
            },
        )
        self._products.add(product)
        return product

    def create_orthomosaic(
        self,
        mission_id: str,
        *,
        progress: ProgressCallback | None = None,
    ) -> SpatialProduct:
        workspace = self.get_workspace(mission_id)
        if workspace is None:
            raise GeospatialError(f"mission does not exist: {mission_id}")
        if not workspace.geospatial_ready:
            raise GeospatialError(
                "all mission images require GPS before NodeODM processing"
            )
        if self._engine is None:
            raise GeospatialError("NodeODM engine is not configured")
        mission = self._require_mission(mission_id)
        images = self._missions.list_image_assets(mission.mission_id)
        task_dir = self.output_root / mission_id / f"nodeodm-{uuid4().hex}"
        source, provenance = self._engine.create(
            mission_id,
            tuple(item.source_path for item in images),
            task_dir,
            progress=progress,
        )
        return self.import_orthomosaic(
            mission_id,
            source,
            provenance=provenance,
        )

    def submit_orthomosaic_analysis(
        self,
        product_id: str,
        request: AnalysisRequest,
    ) -> AnalysisJob:
        if self._analysis is None:
            raise GeospatialError("semantic analysis service is not configured")
        product = self._require_product(product_id, SpatialProductKind.ORTHOMOSAIC)
        if request.mission_id != product.mission_id:
            raise GeospatialError("analysis mission does not match orthomosaic")
        return self._analysis.submit_inputs(
            request,
            (AnalysisInput(f"orthomosaic-{product_id}", product.path),),
        )

    def list_orthomosaic_jobs(self, product_id: str) -> tuple[AnalysisJob, ...]:
        if self._analysis is None:
            return ()
        product = self._require_product(product_id, SpatialProductKind.ORTHOMOSAIC)
        return tuple(
            job
            for job in self._analysis.list_jobs(product.mission_id)
            if len(job.config.inputs) == 1
            and job.config.inputs[0].source_path == product.path
        )

    def refresh_analysis_jobs(self, mission_id: str) -> tuple[AnalysisJob, ...]:
        if self._analysis is None:
            return ()
        return self._analysis.refresh_jobs(mission_id)

    def export_weed_heatmap(self, product_id: str, job_id: str) -> SpatialProduct:
        product = self._require_product(product_id, SpatialProductKind.ORTHOMOSAIC)
        jobs = {job.job_id: job for job in self.list_orthomosaic_jobs(product_id)}
        job = jobs.get(job_id)
        if job is None:
            raise GeospatialError("analysis job does not belong to this orthomosaic")
        if job.status is not JobStatus.COMPLETED or job.result is None:
            raise GeospatialError("analysis job must be completed before heatmap export")
        summary = job.result.image_summaries[0]
        image_id = str(summary["image_id"])
        probability_path = job.result.artifact_dir / f"{image_id}.weed_probability.npy"
        mask_path = job.result.artifact_dir / f"{image_id}.weed_mask.png"
        try:
            probability = np.ascontiguousarray(
                np.load(probability_path, allow_pickle=False),
                dtype=np.float32,
            )
            with Image.open(mask_path) as image:
                mask = np.ascontiguousarray(
                    np.asarray(image.convert("L"), dtype=np.uint8) > 0,
                    dtype=np.uint8,
                )
        except (OSError, ValueError) as exc:
            raise GeospatialError("cannot load semantic artifacts for heatmap") from exc

        heatmap_id = f"heatmap-{uuid4().hex}"
        directory = self.output_root / product.mission_id / heatmap_id
        probability_tif = directory / "weed-probability.tif"
        mask_tif = directory / "weed-mask.tif"
        quality_tif = directory / "valid-data-mask.tif"
        risk_geojson = directory / "weed-risk.geojson"
        preview = directory / "weed-heatmap-preview.png"
        metadata = self._raster.write_scalar_like(
            product.path,
            probability,
            probability_tif,
            layer_name="weed_probability",
        )
        self._raster.write_scalar_like(
            product.path,
            mask,
            mask_tif,
            layer_name="weed_mask",
        )
        valid_mask = self._raster.read_valid_mask(product.path)
        self._raster.write_scalar_like(
            product.path,
            valid_mask,
            quality_tif,
            layer_name="orthomosaic_valid_data_mask",
        )
        self._raster.write_risk_geojson_like(
            product.path,
            probability,
            risk_geojson,
            threshold=job.config.weed_threshold,
            properties={
                "class": "weed",
                "source_job_id": job.job_id,
                "source_product_id": product.product_id,
            },
        )
        self._raster.render_heatmap_preview(product.path, probability, preview)
        result = SpatialProduct(
            product_id=heatmap_id,
            mission_id=product.mission_id,
            kind=SpatialProductKind.WEED_HEATMAP,
            accuracy=SpatialAccuracy.GEOREFERENCED,
            path=probability_tif,
            preview_path=preview,
            raster=metadata,
            source_product_id=product.product_id,
            source_job_id=job.job_id,
            provenance={
                "mask_geotiff": str(mask_tif),
                "quality_geotiff": str(quality_tif),
                "quality_definition": "orthomosaic_valid_data_mask",
                "risk_geojson": str(risk_geojson),
                "model_id": job.config.model_id,
                "artifact_role": job.config.artifact_role,
                "weed_threshold": job.config.weed_threshold,
                "weed_coverage_percent": float(summary["weed_coverage_percent"]),
                "analysis_manifest_sha256": job.result.manifest_sha256,
            },
        )
        self._products.add(result)
        return result

    def _require_mission(self, mission_id: str) -> SurveyMission:
        mission = self._missions.get(MissionId(mission_id))
        if mission is None:
            raise GeospatialError(f"mission does not exist: {mission_id}")
        return mission

    def _require_product(
        self,
        product_id: str,
        kind: SpatialProductKind,
    ) -> SpatialProduct:
        product = self._products.get(product_id)
        if product is None:
            raise GeospatialError(f"spatial product does not exist: {product_id}")
        if product.kind is not kind:
            raise GeospatialError(f"spatial product must be {kind.value}")
        return product
