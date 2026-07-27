"""Commands and read models for configuring and monitoring analysis jobs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from uav_crop_analysis.application.ports import MissionDataRepository
from uav_crop_analysis.domain import MissionId
from uav_crop_analysis.errors import JobStateError, ModelUnavailableError
from uav_crop_analysis.jobs.models import (
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    JobStatus,
)
from uav_crop_analysis.jobs.repository import AnalysisJobRepository


class AnalysisJobController(Protocol):
    repository: AnalysisJobRepository

    def submit(self, config: AnalysisJobConfig, job_id: str | None = None) -> AnalysisJob: ...

    def dispatch_queued(self) -> tuple[AnalysisJob, ...]: ...

    def poll(self, job_id: str) -> AnalysisJob: ...

    def cancel(self, job_id: str) -> AnalysisJob: ...

    def retry(self, job_id: str, *, force: bool = False, start: bool = True) -> AnalysisJob: ...

    def shutdown(self) -> None: ...


class AnalysisTask(str, Enum):
    SEMANTIC = "semantic_segmentation"
    MAIZE_INSTANCE = "maize_instance_segmentation"


@dataclass(frozen=True, slots=True)
class ModelArtifactOption:
    role: str
    path: Path
    available: bool


@dataclass(frozen=True, slots=True)
class AnalysisModelOption:
    model_id: str
    version: str
    family: str
    task: AnalysisTask
    status: str
    runtime: str
    target_classes: tuple[str, ...]
    artifacts: tuple[ModelArtifactOption, ...]

    @property
    def available(self) -> bool:
        return any(artifact.available for artifact in self.artifacts)


class AnalysisModelCatalog(Protocol):
    def list_models(
        self, task: AnalysisTask | None = None
    ) -> tuple[AnalysisModelOption, ...]: ...

    def get(self, model_id: str) -> AnalysisModelOption: ...

    def ensure_artifact(self, model_id: str, artifact_role: str) -> None: ...


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    mission_id: str
    model_id: str
    artifact_role: str
    device: str = "cpu"
    tile_size: int = 640
    overlap: int = 64
    weed_threshold: float = 0.5
    selected_image_ids: tuple[str, ...] = ()


class AnalysisWorkspaceService:
    def __init__(
        self,
        missions: MissionDataRepository,
        jobs: AnalysisJobController,
        catalog: AnalysisModelCatalog,
        registry_path: str | Path,
        output_root: str | Path,
    ) -> None:
        self._missions = missions
        self._jobs = jobs
        self._catalog = catalog
        self.registry_path = Path(registry_path).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()

    @property
    def repository(self) -> AnalysisJobRepository:
        return self._jobs.repository

    def list_models(
        self, task: AnalysisTask | None = None
    ) -> tuple[AnalysisModelOption, ...]:
        return self._catalog.list_models(task)

    def submit(
        self,
        request: AnalysisRequest,
        *,
        auto_start: bool = True,
        job_id: str | None = None,
    ) -> AnalysisJob:
        mission = self._missions.get(MissionId(request.mission_id))
        if mission is None:
            raise JobStateError(f"mission does not exist: {request.mission_id}")
        assets = self._missions.list_image_assets(mission.mission_id)
        selected = set(request.selected_image_ids)
        if selected:
            known = {asset.asset_id for asset in assets}
            unknown = selected - known
            if unknown:
                raise JobStateError(f"unknown analysis image IDs: {', '.join(sorted(unknown))}")
            assets = tuple(asset for asset in assets if asset.asset_id in selected)
        inputs = tuple(
            AnalysisInput(asset.asset_id, asset.source_path) for asset in assets
        )
        return self.submit_inputs(
            request,
            inputs,
            auto_start=auto_start,
            job_id=job_id,
        )

    def submit_inputs(
        self,
        request: AnalysisRequest,
        inputs: tuple[AnalysisInput, ...],
        *,
        auto_start: bool = True,
        job_id: str | None = None,
    ) -> AnalysisJob:
        mission = self._missions.get(MissionId(request.mission_id))
        if mission is None:
            raise JobStateError(f"mission does not exist: {request.mission_id}")
        model = self._catalog.get(request.model_id)
        if model.task is not AnalysisTask.SEMANTIC:
            raise ModelUnavailableError(
                "instance analysis worker is unavailable until a checkpoint is registered",
                context={"model_id": request.model_id},
            )
        self._catalog.ensure_artifact(request.model_id, request.artifact_role)
        if not inputs:
            raise JobStateError("mission has no images to analyze")
        config = AnalysisJobConfig(
            mission_id=mission.mission_id.value,
            model_id=request.model_id,
            artifact_role=request.artifact_role,
            registry_path=self.registry_path,
            inputs=inputs,
            output_root=self.output_root,
            device=request.device,
            tile_size=request.tile_size,
            overlap=request.overlap,
            weed_threshold=request.weed_threshold,
        )
        job = self._jobs.submit(config, job_id)
        if auto_start:
            self._jobs.dispatch_queued()
            return self._jobs.repository.get(job.job_id) or job
        return job

    def list_jobs(self, mission_id: str) -> tuple[AnalysisJob, ...]:
        return self._jobs.repository.list_for_mission(mission_id)

    def refresh_jobs(self, mission_id: str) -> tuple[AnalysisJob, ...]:
        active = self._jobs.repository.list_for_mission(mission_id)
        for job in active:
            if job.status in {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
                self._jobs.poll(job.job_id)
        self._jobs.dispatch_queued()
        return self._jobs.repository.list_for_mission(mission_id)

    def cancel(self, job_id: str) -> AnalysisJob:
        return self._jobs.cancel(job_id)

    def retry(self, job_id: str) -> AnalysisJob:
        return self._jobs.retry(job_id)

    def shutdown(self) -> None:
        self._jobs.shutdown()
