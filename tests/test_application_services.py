from datetime import datetime, timezone

import pytest

from uav_crop_analysis.adapters import InMemoryMissionRepository
from uav_crop_analysis.application import CreateSurveyMission, CreateSurveyMissionCommand
from uav_crop_analysis.domain import MissionId
from uav_crop_analysis.errors import MissionAlreadyExistsError


def _command() -> CreateSurveyMissionCommand:
    return CreateSurveyMissionCommand(
        mission_id="mission-001",
        name="Khao sat ngo D1",
        drone_ids=("drone-01", "drone-02", "drone-03"),
        created_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
    )


def test_create_survey_mission_persists_through_repository_port() -> None:
    repository = InMemoryMissionRepository()
    service = CreateSurveyMission(repository)

    mission = service.execute(_command())

    assert repository.get(MissionId("mission-001")) == mission
    assert repository.list_all() == (mission,)


def test_create_survey_mission_rejects_duplicate_id() -> None:
    repository = InMemoryMissionRepository()
    service = CreateSurveyMission(repository)
    service.execute(_command())

    with pytest.raises(MissionAlreadyExistsError) as error:
        service.execute(_command())

    assert error.value.code == "mission_already_exists"
    assert error.value.context == {"mission_id": "mission-001"}
