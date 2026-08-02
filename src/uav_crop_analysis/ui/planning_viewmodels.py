"""Framework-neutral state for the desktop mission-planning workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from uav_crop_analysis.application import MissionDataWorkspace, MissionDataWorkspaceService
from uav_crop_analysis.domain import GeoPoint
from uav_crop_analysis.errors import MissionPlanNotFoundError, MissionPlanningError
from uav_crop_analysis.planning import (
    MissionPlanExport,
    MissionPlanningProfile,
    MissionPlanningRequest,
    MissionPlanningService,
    PlannedMission,
    SurveyArea,
)


@dataclass(frozen=True, slots=True)
class PlanningDraft:
    mission_id: str
    camera_profile_id: str
    polygon_wgs84: tuple[tuple[float, float], ...]
    altitude_agl_m: float
    gimbal_pitch_deg: float = -90.0
    forward_overlap: float = 0.75
    side_overlap: float = 0.65
    flight_speed_mps: float = 3.0
    capture_pause_seconds: float = 1.0
    sweep_heading_deg: float | None = None
    minimum_route_separation_m: float = 2.0


@dataclass(frozen=True, slots=True)
class PlanningWorkspaceState:
    mission_id: str | None = None
    workspace: MissionDataWorkspace | None = None
    plan: PlannedMission | None = None
    exported: MissionPlanExport | None = None
    error_message: str | None = None


class PlanningWorkspaceViewModel:
    def __init__(
        self,
        data_service: MissionDataWorkspaceService,
        planning_service: MissionPlanningService,
    ) -> None:
        self._data_service = data_service
        self._planning_service = planning_service
        self.state = PlanningWorkspaceState()

    def load(self, mission_id: str) -> PlanningWorkspaceState:
        try:
            workspace = self._data_service.get_data(mission_id)
            if workspace is None:
                raise MissionPlanningError(f"mission does not exist: {mission_id}")
            try:
                plan = self._planning_service.get(mission_id)
            except MissionPlanNotFoundError:
                plan = None
            self.state = PlanningWorkspaceState(
                mission_id=mission_id,
                workspace=workspace,
                plan=plan,
            )
        except Exception as exc:
            self.state = PlanningWorkspaceState(
                mission_id=mission_id,
                error_message=str(exc) or type(exc).__name__,
            )
        return self.state

    def calculate(self, draft: PlanningDraft) -> PlanningWorkspaceState:
        workspace = self.state.workspace
        if workspace is None or self.state.mission_id != draft.mission_id:
            return self._with_error("Nhiệm vụ lập đường bay chưa được tải.")
        cameras = {profile.profile_id: profile for profile in workspace.camera_catalog}
        cameras.update({profile.profile_id: profile for profile in workspace.cameras})
        camera = cameras.get(draft.camera_profile_id)
        if camera is None:
            return self._with_error("Không tìm thấy hồ sơ máy ảnh đã chọn.")
        assignments = tuple(
            sorted(workspace.mission.assignments, key=lambda item: item.lane_index)
        )
        try:
            plan = self._planning_service.preview(
                MissionPlanningRequest(
                    mission_id=draft.mission_id,
                    survey_area=SurveyArea(
                        tuple(
                            GeoPoint(latitude, longitude)
                            for latitude, longitude in draft.polygon_wgs84
                        )
                    ),
                    profile=MissionPlanningProfile(
                        drone_count=len(assignments),
                        altitude_agl_m=draft.altitude_agl_m,
                        gimbal_pitch_deg=draft.gimbal_pitch_deg,
                        forward_overlap=draft.forward_overlap,
                        side_overlap=draft.side_overlap,
                        flight_speed_mps=draft.flight_speed_mps,
                        capture_pause_seconds=draft.capture_pause_seconds,
                        sweep_heading_deg=draft.sweep_heading_deg,
                        minimum_route_separation_m=draft.minimum_route_separation_m,
                    ),
                    camera=camera,
                    drone_ids=tuple(item.drone_id.value for item in assignments),
                )
            )
        except Exception as exc:
            return self._with_error(str(exc) or type(exc).__name__)
        self.state = PlanningWorkspaceState(
            mission_id=draft.mission_id,
            workspace=workspace,
            plan=plan,
        )
        return self.state

    def export(self, output_root: Path) -> PlanningWorkspaceState:
        workspace = self.state.workspace
        plan = self.state.plan
        if workspace is None or plan is None:
            return self._with_error("Nhiệm vụ lập đường bay chưa được tải.")
        try:
            exported = self._planning_service.publish(plan, output_root)
        except Exception as exc:
            return self._with_error(str(exc) or type(exc).__name__)
        self.state = PlanningWorkspaceState(
            mission_id=plan.mission_id,
            workspace=workspace,
            plan=self.state.plan,
            exported=exported,
        )
        return self.state

    def discard(self, mission_id: str) -> PlanningWorkspaceState:
        try:
            self._planning_service.discard(mission_id)
        except Exception as exc:
            return self._with_error(str(exc) or type(exc).__name__)
        self.state = PlanningWorkspaceState(
            mission_id=mission_id,
            workspace=self.state.workspace,
        )
        return self.state

    def _with_error(self, message: str) -> PlanningWorkspaceState:
        self.state = PlanningWorkspaceState(
            mission_id=self.state.mission_id,
            workspace=self.state.workspace,
            plan=self.state.plan,
            exported=self.state.exported,
            error_message=message,
        )
        return self.state
