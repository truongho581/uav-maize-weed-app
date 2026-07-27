from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from uav_crop_analysis.adapters import SQLiteAnalysisJobRepository, SQLiteMissionRepository
from uav_crop_analysis.application import MissionDataStatus, MissionWorkspaceService
from uav_crop_analysis.domain import DroneId, GeoPoint, ImageAsset, SurveyMission
from uav_crop_analysis.jobs import AnalysisInput, AnalysisJob, AnalysisJobConfig, JobEventType


NOW = datetime(2026, 7, 27, 8, 30, tzinfo=timezone.utc)


def _mission(mission_id: str = "mission-workspace") -> SurveyMission:
    return SurveyMission.create(
        mission_id=mission_id,
        name="Khao sat ngo khu A",
        drone_ids=("drone-01", "drone-02", "drone-03"),
        created_at=NOW,
    )


def _image(
    tmp_path: Path,
    mission: SurveyMission,
    drone_id: str,
    sequence: int,
    *,
    complete_metadata: bool = True,
) -> ImageAsset:
    return ImageAsset(
        asset_id=f"{drone_id}-{sequence}",
        mission_id=mission.mission_id,
        drone_id=DroneId(drone_id),
        source_path=tmp_path / drone_id / f"{sequence}.jpg",
        sha256=(drone_id[-1] * 64),
        size_bytes=1024,
        captured_at=NOW,
        width_px=1920,
        height_px=1080,
        sequence_index=sequence,
        position=GeoPoint(10.75, 106.67) if complete_metadata else None,
        relative_altitude_m=10.0 if complete_metadata else None,
    )


def _job(tmp_path: Path, mission_id: str) -> AnalysisJob:
    return AnalysisJob(
        "job-workspace",
        AnalysisJobConfig(
            mission_id=mission_id,
            model_id="segformer-v72",
            artifact_role="best",
            registry_path=tmp_path / "registry.json",
            inputs=(AnalysisInput("drone-01-0", tmp_path / "drone-01/0.jpg"),),
            output_root=tmp_path / "results",
            tile_size=16,
            overlap=4,
        ),
    )


def test_workspace_lists_newest_mission_with_data_and_job_status(tmp_path: Path) -> None:
    database = tmp_path / "app.db"
    missions = SQLiteMissionRepository(database)
    jobs = SQLiteAnalysisJobRepository(database)
    mission = _mission()
    images = tuple(
        _image(tmp_path, mission, drone_id, 0)
        for drone_id in ("drone-01", "drone-02", "drone-03")
    )
    missions.save_bundle(mission, (), images, ())
    job = _job(tmp_path, mission.mission_id.value)
    jobs.add(job, job.event(JobEventType.CREATED))

    workspace = MissionWorkspaceService(missions, jobs)
    summaries = workspace.list_missions()
    overview = workspace.get_overview(mission.mission_id.value)

    assert len(summaries) == 1
    assert summaries[0].image_count == 3
    assert summaries[0].gps_coverage == 1.0
    assert summaries[0].data_status is MissionDataStatus.READY
    assert summaries[0].latest_job_status == job.status
    assert overview is not None
    assert overview.can_analyze
    assert overview.data_status is MissionDataStatus.READY
    assert [drone.image_count for drone in overview.drones] == [1, 1, 1]
    assert overview.recent_jobs[0].model_id == "segformer-v72"


def test_workspace_marks_partial_three_drone_import_incomplete(tmp_path: Path) -> None:
    database = tmp_path / "app.db"
    missions = SQLiteMissionRepository(database)
    jobs = SQLiteAnalysisJobRepository(database)
    mission = _mission()
    missions.save_bundle(
        mission,
        (),
        (_image(tmp_path, mission, "drone-01", 0, complete_metadata=False),),
        (),
    )

    overview = MissionWorkspaceService(missions, jobs).get_overview(
        mission.mission_id.value
    )

    assert overview is not None
    assert overview.data_status is MissionDataStatus.INCOMPLETE
    assert overview.gps_coverage == 0.0
    assert overview.can_analyze


def test_workspace_returns_none_for_unknown_mission(tmp_path: Path) -> None:
    database = tmp_path / "app.db"
    workspace = MissionWorkspaceService(
        SQLiteMissionRepository(database),
        SQLiteAnalysisJobRepository(database),
    )

    assert workspace.get_overview("missing") is None
