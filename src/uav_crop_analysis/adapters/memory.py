"""In-memory adapters used by tests and early integration prototypes."""

from __future__ import annotations

from threading import RLock

from uav_crop_analysis.domain import MissionId, SurveyMission


class InMemoryMissionRepository:
    def __init__(self) -> None:
        self._missions: dict[str, SurveyMission] = {}
        self._lock = RLock()

    def add(self, mission: SurveyMission) -> None:
        with self._lock:
            self._missions[mission.mission_id.value] = mission

    def get(self, mission_id: MissionId) -> SurveyMission | None:
        with self._lock:
            return self._missions.get(mission_id.value)

    def list_missions(self) -> tuple[SurveyMission, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._missions.values(),
                    key=lambda mission: (mission.created_at, mission.mission_id.value),
                    reverse=True,
                )
            )

    def list_all(self) -> tuple[SurveyMission, ...]:
        """Compatibility alias for Phase 1 callers."""
        return self.list_missions()
