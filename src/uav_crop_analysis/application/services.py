"""Application services orchestrating domain objects through ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from uav_crop_analysis.application.ports import MissionRepository
from uav_crop_analysis.domain import FlightProfile, MissionId, SurveyMission
from uav_crop_analysis.errors import MissionAlreadyExistsError


@dataclass(frozen=True, slots=True)
class CreateSurveyMissionCommand:
    mission_id: str
    name: str
    drone_ids: tuple[str, str, str]
    flight_profile: FlightProfile | None = None
    created_at: datetime | None = None


class CreateSurveyMission:
    def __init__(self, repository: MissionRepository) -> None:
        self._repository = repository

    def execute(self, command: CreateSurveyMissionCommand) -> SurveyMission:
        mission_id = MissionId(command.mission_id)
        if self._repository.get(mission_id) is not None:
            raise MissionAlreadyExistsError(
                f"mission already exists: {mission_id}",
                context={"mission_id": mission_id.value},
            )

        mission = SurveyMission.create(
            mission_id=mission_id.value,
            name=command.name,
            drone_ids=command.drone_ids,
            flight_profile=command.flight_profile,
            created_at=command.created_at,
        )
        self._repository.add(mission)
        return mission
