"""Framework-independent state for the geospatial workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from uav_crop_analysis.application import AnalysisModelOption, AnalysisRequest
from uav_crop_analysis.geospatial import (
    ProgressCallback,
    SpatialProduct,
    SpatialProductKind,
    SpatialWorkspace,
    SpatialWorkspaceService,
)
from uav_crop_analysis.jobs import AnalysisJob


@dataclass(frozen=True, slots=True)
class SpatialWorkspaceState:
    mission_id: str | None = None
    workspace: SpatialWorkspace | None = None
    semantic_models: tuple[AnalysisModelOption, ...] = ()
    product_jobs: tuple[tuple[str, tuple[AnalysisJob, ...]], ...] = ()
    error_message: str | None = None

    def jobs_for(self, product_id: str) -> tuple[AnalysisJob, ...]:
        return next((jobs for key, jobs in self.product_jobs if key == product_id), ())


class SpatialWorkspaceViewModel:
    def __init__(self, service: SpatialWorkspaceService) -> None:
        self._service = service
        self.state = SpatialWorkspaceState()

    def load(
        self,
        mission_id: str,
        *,
        poll_jobs: bool = False,
    ) -> SpatialWorkspaceState:
        try:
            if poll_jobs:
                self._service.refresh_analysis_jobs(mission_id)
            workspace = self._service.get_workspace(mission_id)
            if workspace is None:
                raise ValueError("Không tìm thấy nhiệm vụ đã chọn.")
            product_jobs = tuple(
                (product.product_id, self._service.list_orthomosaic_jobs(product.product_id))
                for product in workspace.products
                if product.kind is SpatialProductKind.ORTHOMOSAIC
            )
            self.state = SpatialWorkspaceState(
                mission_id=mission_id,
                workspace=workspace,
                semantic_models=self._service.list_semantic_models(),
                product_jobs=product_jobs,
            )
        except Exception as exc:
            self.state = SpatialWorkspaceState(
                mission_id=mission_id,
                error_message=str(exc) or type(exc).__name__,
            )
        return self.state

    def build_preview(self, mission_id: str) -> SpatialProduct:
        return self._service.build_preview(mission_id)

    def import_orthomosaic(self, mission_id: str, path: Path) -> SpatialProduct:
        return self._service.import_orthomosaic(mission_id, path)

    def create_orthomosaic(
        self,
        mission_id: str,
        progress: ProgressCallback | None = None,
    ) -> SpatialProduct:
        return self._service.create_orthomosaic(mission_id, progress=progress)

    def submit_analysis(
        self,
        product_id: str,
        request: AnalysisRequest,
    ) -> AnalysisJob:
        return self._service.submit_orthomosaic_analysis(product_id, request)

    def export_heatmap(self, product_id: str, job_id: str) -> SpatialProduct:
        return self._service.export_weed_heatmap(product_id, job_id)
