from datetime import datetime, timezone

import pytest

from uav_crop_analysis.domain import (
    CaptureMode,
    DroneAssignment,
    DroneId,
    FlightProfile,
    MissionId,
    SurveyMission,
)
from uav_crop_analysis.errors import DomainValidationError


def test_default_flight_profile_matches_nadir_stop_and_capture_contract() -> None:
    profile = FlightProfile()

    assert profile.altitude_m == 10.0
    assert profile.is_nadir
    assert profile.capture_mode is CaptureMode.STOP_AND_CAPTURE
    assert profile.forward_overlap == 0.75
    assert profile.side_overlap == 0.65


@pytest.mark.parametrize("altitude_m", [9.99, 20.01])
def test_flight_profile_rejects_altitude_outside_project_range(altitude_m: float) -> None:
    with pytest.raises(DomainValidationError) as error:
        FlightProfile(altitude_m=altitude_m)

    assert error.value.context["field"] == "altitude_m"


@pytest.mark.parametrize("overlap", [-0.01, 1.0])
def test_flight_profile_rejects_invalid_overlap(overlap: float) -> None:
    with pytest.raises(DomainValidationError):
        FlightProfile(forward_overlap=overlap)


def test_survey_mission_requires_three_unique_parallel_lanes() -> None:
    mission = SurveyMission.create(
        mission_id="mission-001",
        name="Ruong ngo D1",
        drone_ids=("drone-01", "drone-02", "drone-03"),
        created_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
    )

    assert [assignment.lane_index for assignment in mission.assignments] == [0, 1, 2]
    assert [assignment.drone_id.value for assignment in mission.assignments] == [
        "drone-01",
        "drone-02",
        "drone-03",
    ]


def test_survey_mission_rejects_duplicate_drone_ids() -> None:
    assignments = (
        DroneAssignment(DroneId("drone-01"), 0),
        DroneAssignment(DroneId("drone-01"), 1),
        DroneAssignment(DroneId("drone-03"), 2),
    )

    with pytest.raises(DomainValidationError, match="unique drone IDs"):
        SurveyMission(
            mission_id=MissionId("mission-001"),
            name="D1",
            assignments=assignments,
            flight_profile=FlightProfile(),
            created_at=datetime.now(timezone.utc),
        )


def test_survey_mission_rejects_naive_timestamp() -> None:
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        SurveyMission.create(
            mission_id="mission-001",
            name="D1",
            drone_ids=("drone-01", "drone-02", "drone-03"),
            created_at=datetime(2026, 7, 27),
        )
