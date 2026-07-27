"""Framework-independent state for Phase 6 Data and Analysis workspaces."""

from __future__ import annotations

from dataclasses import dataclass

from uav_crop_analysis.application.analysis_workspace import (
    AnalysisModelOption,
    AnalysisRequest,
    AnalysisTask,
    AnalysisWorkspaceService,
)
from uav_crop_analysis.application.data_workspace import (
    MissionDataWorkspace,
    MissionDataWorkspaceService,
)
from uav_crop_analysis.jobs.models import AnalysisJob


@dataclass(frozen=True, slots=True)
class DataWorkspaceState:
    mission_id: str | None = None
    data: MissionDataWorkspace | None = None
    error_message: str | None = None


class DataWorkspaceViewModel:
    def __init__(self, service: MissionDataWorkspaceService) -> None:
        self._service = service
        self.state = DataWorkspaceState()

    def load(self, mission_id: str) -> DataWorkspaceState:
        try:
            data = self._service.get_data(mission_id)
        except Exception as exc:
            self.state = DataWorkspaceState(
                mission_id=mission_id,
                error_message=str(exc) or type(exc).__name__,
            )
            return self.state
        if data is None:
            self.state = DataWorkspaceState(
                mission_id=mission_id,
                error_message="Không tìm thấy nhiệm vụ đã chọn.",
            )
            return self.state
        self.state = DataWorkspaceState(mission_id=mission_id, data=data)
        return self.state


@dataclass(frozen=True, slots=True)
class AnalysisWorkspaceState:
    mission_id: str | None = None
    semantic_models: tuple[AnalysisModelOption, ...] = ()
    instance_models: tuple[AnalysisModelOption, ...] = ()
    jobs: tuple[AnalysisJob, ...] = ()
    error_message: str | None = None


class AnalysisWorkspaceViewModel:
    def __init__(self, service: AnalysisWorkspaceService) -> None:
        self._service = service
        self.state = AnalysisWorkspaceState()

    def load(self, mission_id: str) -> AnalysisWorkspaceState:
        try:
            self.state = AnalysisWorkspaceState(
                mission_id=mission_id,
                semantic_models=self._service.list_models(AnalysisTask.SEMANTIC),
                instance_models=self._service.list_models(AnalysisTask.MAIZE_INSTANCE),
                jobs=self._service.list_jobs(mission_id),
            )
        except Exception as exc:
            self.state = AnalysisWorkspaceState(
                mission_id=mission_id,
                error_message=str(exc) or type(exc).__name__,
            )
        return self.state

    def submit(self, request: AnalysisRequest) -> AnalysisWorkspaceState:
        try:
            self._service.submit(request)
        except Exception as exc:
            return self._with_error(str(exc) or type(exc).__name__)
        return self.refresh()

    def refresh(self) -> AnalysisWorkspaceState:
        if self.state.mission_id is None:
            return self.state
        try:
            jobs = self._service.refresh_jobs(self.state.mission_id)
        except Exception as exc:
            return self._with_error(str(exc) or type(exc).__name__)
        self.state = AnalysisWorkspaceState(
            mission_id=self.state.mission_id,
            semantic_models=self.state.semantic_models,
            instance_models=self.state.instance_models,
            jobs=jobs,
        )
        return self.state

    def cancel(self, job_id: str) -> AnalysisWorkspaceState:
        try:
            self._service.cancel(job_id)
        except Exception as exc:
            return self._with_error(str(exc) or type(exc).__name__)
        return self.refresh()

    def retry(self, job_id: str) -> AnalysisWorkspaceState:
        try:
            self._service.retry(job_id)
        except Exception as exc:
            return self._with_error(str(exc) or type(exc).__name__)
        return self.refresh()

    def shutdown(self) -> None:
        self._service.shutdown()

    def _with_error(self, message: str) -> AnalysisWorkspaceState:
        self.state = AnalysisWorkspaceState(
            mission_id=self.state.mission_id,
            semantic_models=self.state.semantic_models,
            instance_models=self.state.instance_models,
            jobs=self.state.jobs,
            error_message=message,
        )
        return self.state
