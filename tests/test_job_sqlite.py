from __future__ import annotations

from pathlib import Path
import sqlite3

from uav_crop_analysis.adapters import SQLiteAnalysisJobRepository
from uav_crop_analysis.adapters.sqlite import LATEST_SCHEMA_VERSION, MIGRATION_V1
from uav_crop_analysis.jobs import (
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    AnalysisJobService,
    JobEventType,
    JobStatus,
)


def _job(tmp_path: Path, job_id: str = "job-sqlite") -> AnalysisJob:
    config = AnalysisJobConfig(
        mission_id="mission-sqlite",
        model_id="semantic-model",
        artifact_role="best",
        registry_path=tmp_path / "registry.json",
        inputs=(AnalysisInput("image-1", tmp_path / "image.png"),),
        output_root=tmp_path / "results",
        tile_size=16,
        overlap=4,
    )
    return AnalysisJob(job_id, config)


def test_job_and_event_history_survive_reopen(tmp_path: Path) -> None:
    database = tmp_path / "app.db"
    repository = SQLiteAnalysisJobRepository(database)
    queued = _job(tmp_path)
    repository.add(queued, queued.event(JobEventType.CREATED))
    running = queued.start().report_progress(stage=queued.stage.PREPARE, progress=0.1)
    repository.save(running, running.event(JobEventType.PROGRESS, "prepared"))

    reopened = SQLiteAnalysisJobRepository(database)

    assert reopened.get(queued.job_id) == running
    assert [event.event_type for event in reopened.list_events(queued.job_id)] == [
        JobEventType.CREATED,
        JobEventType.PROGRESS,
    ]
    assert reopened.list_for_mission("mission-sqlite") == (running,)
    assert reopened.list_for_mission("unknown") == ()


def test_restart_marks_interrupted_worker_as_retryable_failure(tmp_path: Path) -> None:
    repository = SQLiteAnalysisJobRepository(tmp_path / "app.db")
    queued = _job(tmp_path, "job-interrupted")
    repository.add(queued, queued.event(JobEventType.CREATED))
    running = queued.start()
    repository.save(running, running.event(JobEventType.STARTED))
    stale_staging = running.config.output_root / running.job_id / ".attempt-0001-crashed"
    stale_staging.mkdir(parents=True)
    (stale_staging / "partial.npy").write_bytes(b"partial")

    recovered = AnalysisJobService(repository).recover_interrupted()

    assert len(recovered) == 1
    assert recovered[0].status is JobStatus.FAILED
    assert recovered[0].error is not None
    assert recovered[0].error.code == "worker_interrupted"
    assert recovered[0].error.retryable
    assert not stale_staging.exists()
    assert repository.list_events(queued.job_id)[-1].event_type is JobEventType.RECOVERED


def test_schema_v1_database_migrates_to_latest_schema(tmp_path: Path) -> None:
    database = tmp_path / "legacy-v1.db"
    connection = sqlite3.connect(database)
    connection.executescript(MIGRATION_V1)
    connection.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (1, '2026-07-27T00:00:00+00:00')"
    )
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    connection.close()

    repository = SQLiteAnalysisJobRepository(database)
    queued = _job(tmp_path, "job-after-migration")
    repository.add(queued, queued.event(JobEventType.CREATED))

    connection = sqlite3.connect(database)
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    connection.close()
    assert version == LATEST_SCHEMA_VERSION
    assert repository.get(queued.job_id) == queued
