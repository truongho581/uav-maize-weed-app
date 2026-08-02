"""Application service coordinating planning, persistence, and export."""

from __future__ import annotations

from pathlib import Path

from uav_crop_analysis.errors import MissionPlanNotFoundError
from uav_crop_analysis.planning.models import (
    MissionPlanExport,
    MissionPlanningRequest,
    PlannedMission,
)
from uav_crop_analysis.planning.ports import (
    MissionPlanExporter,
    MissionPlanner,
    MissionPlanRepository,
)


class MissionPlanningService:
    def __init__(
        self,
        planner: MissionPlanner,
        repository: MissionPlanRepository,
        exporter: MissionPlanExporter,
    ) -> None:
        self._planner = planner
        self._repository = repository
        self._exporter = exporter

    def plan(self, request: MissionPlanningRequest) -> PlannedMission:
        """Compatibility method for API clients that persist on calculation."""
        plan = self._planner.plan(request)
        self._repository.save(plan)
        return plan

    def preview(self, request: MissionPlanningRequest) -> PlannedMission:
        """Calculate a route without persisting it as a mission plan."""
        return self._planner.plan(request)

    def publish(
        self,
        plan: PlannedMission,
        output_root: str | Path,
    ) -> MissionPlanExport:
        """Persist a reviewed plan only when the user exports it."""
        exported = self._exporter.export(plan, Path(output_root))
        self._repository.save(plan)
        return exported

    def discard(self, mission_id: str) -> None:
        """Remove a previously exported plan for a mission."""
        self._repository.delete(mission_id)

    def get(self, mission_id: str) -> PlannedMission:
        plan = self._repository.get(mission_id)
        if plan is None:
            raise MissionPlanNotFoundError(
                f"mission plan does not exist: {mission_id}",
                context={"mission_id": mission_id},
            )
        return plan

    def list(self) -> tuple[PlannedMission, ...]:
        return self._repository.list()

    def export(self, mission_id: str, output_root: str | Path) -> MissionPlanExport:
        return self._exporter.export(self.get(mission_id), Path(output_root))
