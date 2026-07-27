"""Framework-independent state holder for the mission workspace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from uav_crop_analysis.application.workspace import MissionOverview, MissionSummary


class WorkspaceQuery(Protocol):
    def list_missions(self) -> tuple[MissionSummary, ...]: ...

    def get_overview(self, mission_id: str) -> MissionOverview | None: ...


@dataclass(frozen=True, slots=True)
class WorkspaceState:
    missions: tuple[MissionSummary, ...] = ()
    selected_mission_id: str | None = None
    overview: MissionOverview | None = None
    error_message: str | None = None


class MissionWorkspaceViewModel:
    def __init__(self, query: WorkspaceQuery) -> None:
        self._query = query
        self.state = WorkspaceState()

    def refresh(self) -> WorkspaceState:
        try:
            missions = self._query.list_missions()
        except Exception as exc:
            self.state = WorkspaceState(error_message=str(exc) or type(exc).__name__)
            return self.state
        selected = self.state.selected_mission_id
        if selected and not any(item.mission_id == selected for item in missions):
            selected = None
        self.state = WorkspaceState(missions=missions, selected_mission_id=selected)
        return self.state

    def select_mission(self, mission_id: str) -> WorkspaceState:
        try:
            overview = self._query.get_overview(mission_id)
        except Exception as exc:
            self.state = WorkspaceState(
                missions=self.state.missions,
                error_message=str(exc) or type(exc).__name__,
            )
            return self.state
        if overview is None:
            self.state = WorkspaceState(
                missions=self.state.missions,
                error_message="Không tìm thấy nhiệm vụ đã chọn.",
            )
            return self.state
        self.state = WorkspaceState(
            missions=self.state.missions,
            selected_mission_id=mission_id,
            overview=overview,
        )
        return self.state
