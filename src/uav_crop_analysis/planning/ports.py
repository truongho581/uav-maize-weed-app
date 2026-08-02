"""Ports for mission planners and future persistence/export adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from uav_crop_analysis.planning.models import (
    MissionPlanExport,
    MissionPlanningRequest,
    PlannedMission,
)


class MissionPlanner(Protocol):
    def plan(self, request: MissionPlanningRequest) -> PlannedMission: ...


class MissionPlanRepository(Protocol):
    def save(self, plan: PlannedMission) -> None: ...

    def delete(self, mission_id: str) -> None: ...

    def get(self, mission_id: str) -> PlannedMission | None: ...

    def list(self) -> tuple[PlannedMission, ...]: ...


class MissionPlanExporter(Protocol):
    def export(self, plan: PlannedMission, output_root: Path) -> MissionPlanExport: ...
