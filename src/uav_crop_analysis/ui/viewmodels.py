"""Framework-independent state holder for the mission workspace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from uav_crop_analysis.application.workspace import MissionOverview, MissionSummary
from uav_crop_analysis.domain import CameraProfile, FlightProfile


class WorkspaceQuery(Protocol):
    def list_missions(self) -> tuple[MissionSummary, ...]: ...

    def get_overview(self, mission_id: str) -> MissionOverview | None: ...

    def list_saved_camera_profiles(self) -> tuple[CameraProfile, ...]: ...

    def create_mission(
        self,
        *,
        mission_id: str,
        name: str,
        drone_ids: tuple[str, ...],
        flight_profile: FlightProfile,
        camera_profile: CameraProfile | None = None,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class MissionCreateDraft:
    mission_id: str
    name: str
    drone_ids: tuple[str, ...]
    flight_profile: FlightProfile
    camera_profile: CameraProfile | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceState:
    missions: tuple[MissionSummary, ...] = ()
    selected_mission_id: str | None = None
    overview: MissionOverview | None = None
    camera_profiles: tuple[CameraProfile, ...] = ()
    error_message: str | None = None


class MissionWorkspaceViewModel:
    def __init__(self, query: WorkspaceQuery) -> None:
        self._query = query
        self.state = WorkspaceState()

    def refresh(self) -> WorkspaceState:
        try:
            missions = self._query.list_missions()
            list_cameras = getattr(self._query, "list_saved_camera_profiles", None)
            camera_profiles = tuple(list_cameras()) if callable(list_cameras) else ()
        except Exception as exc:
            self.state = WorkspaceState(error_message=str(exc) or type(exc).__name__)
            return self.state
        selected = self.state.selected_mission_id
        if selected and not any(item.mission_id == selected for item in missions):
            selected = None
        self.state = WorkspaceState(
            missions=missions,
            selected_mission_id=selected,
            camera_profiles=camera_profiles,
        )
        return self.state

    def create_mission(self, draft: MissionCreateDraft) -> WorkspaceState:
        try:
            self._query.create_mission(
                mission_id=draft.mission_id,
                name=draft.name,
                drone_ids=draft.drone_ids,
                flight_profile=draft.flight_profile,
                camera_profile=draft.camera_profile,
            )
        except Exception as exc:
            self.state = WorkspaceState(
                missions=self.state.missions,
                camera_profiles=self.state.camera_profiles,
                error_message=str(exc) or type(exc).__name__,
            )
            return self.state
        state = self.refresh()
        self.state = WorkspaceState(
            missions=state.missions,
            selected_mission_id=draft.mission_id,
            camera_profiles=state.camera_profiles,
        )
        return self.state

    def select_mission(self, mission_id: str) -> WorkspaceState:
        try:
            overview = self._query.get_overview(mission_id)
        except Exception as exc:
            self.state = WorkspaceState(
                missions=self.state.missions,
                camera_profiles=self.state.camera_profiles,
                error_message=str(exc) or type(exc).__name__,
            )
            return self.state
        if overview is None:
            self.state = WorkspaceState(
                missions=self.state.missions,
                camera_profiles=self.state.camera_profiles,
                error_message="Không tìm thấy nhiệm vụ đã chọn.",
            )
            return self.state
        self.state = WorkspaceState(
            missions=self.state.missions,
            selected_mission_id=mission_id,
            overview=overview,
            camera_profiles=self.state.camera_profiles,
        )
        return self.state
