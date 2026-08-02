from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pytest

from uav_crop_analysis.adapters import LATEST_SCHEMA_VERSION, SQLiteMissionRepository
from uav_crop_analysis.domain import (
    CameraProfile,
    DroneId,
    GeoPoint,
    ImageAsset,
    MissionId,
    SurveyMission,
    TelemetrySample,
)
from uav_crop_analysis.errors import MigrationError, PersistenceError


def _mission() -> SurveyMission:
    return SurveyMission.create(
        mission_id="mission-sqlite",
        name="SQLite reopen contract",
        drone_ids=("drone-01", "drone-02", "drone-03"),
        created_at=datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc),
    )


def test_sqlite_migration_creates_and_reopens_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "mission.db"

    first = SQLiteMissionRepository(database_path)
    second = SQLiteMissionRepository(database_path)

    assert first.schema_version == LATEST_SCHEMA_VERSION
    assert second.schema_version == LATEST_SCHEMA_VERSION


def test_sqlite_rejects_database_from_newer_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "future.db"
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA user_version = 99")
    connection.close()

    with pytest.raises(MigrationError):
        SQLiteMissionRepository(database_path)


def test_sqlite_bundle_round_trip_preserves_all_metadata(tmp_path: Path) -> None:
    database_path = tmp_path / "mission.db"
    repository = SQLiteMissionRepository(database_path)
    mission = _mission()
    profile = CameraProfile(
        profile_id="camera-rgb",
        name="Generic RGB",
        image_width_px=640,
        image_height_px=640,
        focal_length_mm=4.5,
        distortion_coefficients=(0.1, -0.05, 0.0, 0.0),
    )
    recorded_at = datetime(2026, 7, 27, 8, 0, 1, tzinfo=timezone.utc)
    telemetry = TelemetrySample(
        mission_id=mission.mission_id,
        drone_id=DroneId("drone-01"),
        recorded_at=recorded_at,
        position=GeoPoint(10.75, 106.67),
        relative_altitude_m=10.5,
    )
    image = ImageAsset(
        asset_id="asset-001",
        mission_id=mission.mission_id,
        drone_id=DroneId("drone-01"),
        source_path=tmp_path / "drone-01/image-001.jpg",
        sha256="a" * 64,
        size_bytes=1024,
        captured_at=recorded_at,
        width_px=640,
        height_px=640,
        sequence_index=0,
        position=telemetry.position,
        absolute_altitude_m=15.2,
        relative_altitude_m=10.5,
        telemetry_offset_ms=0,
        camera_profile_id=profile.profile_id,
    )

    repository.save_bundle(mission, (profile,), (image,), (telemetry,))
    reopened = SQLiteMissionRepository(database_path)

    assert reopened.get(MissionId("mission-sqlite")) == mission
    assert reopened.list_camera_profiles(mission.mission_id) == (profile,)
    assert reopened.list_saved_camera_profiles() == (profile,)
    assert reopened.list_image_assets(mission.mission_id) == (image,)
    assert reopened.list_telemetry_samples(mission.mission_id) == (telemetry,)

    invalid_image = replace(image, camera_profile_id="missing-profile")
    with pytest.raises(PersistenceError):
        reopened.save_bundle(mission, (profile,), (invalid_image,), (telemetry,))

    after_rollback = SQLiteMissionRepository(database_path)
    assert after_rollback.list_image_assets(mission.mission_id) == (image,)
    assert after_rollback.list_telemetry_samples(mission.mission_id) == (telemetry,)


@pytest.mark.parametrize("drone_count", [1, 2, 3])
def test_sqlite_round_trip_supports_one_to_three_drone_assignments(
    tmp_path: Path,
    drone_count: int,
) -> None:
    repository = SQLiteMissionRepository(tmp_path / f"mission-{drone_count}.db")
    mission = SurveyMission.create(
        f"mission-{drone_count}",
        f"Mission {drone_count}",
        tuple(f"drone-{index}" for index in range(drone_count)),
    )

    repository.add(mission)

    assert repository.get(mission.mission_id) == mission


def test_camera_catalog_persists_and_can_be_reused_by_later_missions(tmp_path: Path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "camera-catalog.db")
    first = _mission()
    second = SurveyMission.create(
        "mission-second", "Second mission", ("drone-a", "drone-b", "drone-c")
    )
    repository.add(first)
    repository.add(second)
    profile = CameraProfile(
        profile_id="dji-mini-4k", name="DJI Mini 4K", image_width_px=4000,
        image_height_px=3000, horizontal_fov_deg=82.0,
    )

    repository.save_camera_profile(
        first.mission_id, profile, tuple(item.drone_id for item in first.assignments)
    )
    repository.save_camera_profile(
        second.mission_id, profile, tuple(item.drone_id for item in second.assignments)
    )

    reopened = SQLiteMissionRepository(tmp_path / "camera-catalog.db")
    assert reopened.list_saved_camera_profiles() == (profile,)
    assert reopened.list_camera_profiles(second.mission_id) == (profile,)


def test_sqlite_lists_missions_newest_first(tmp_path: Path) -> None:
    repository = SQLiteMissionRepository(tmp_path / "mission.db")
    older = _mission()
    newer = SurveyMission.create(
        mission_id="mission-newer",
        name="Newer mission",
        drone_ids=("drone-a", "drone-b", "drone-c"),
        created_at=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
    )
    repository.add(older)
    repository.add(newer)

    assert repository.list_missions() == (newer, older)
