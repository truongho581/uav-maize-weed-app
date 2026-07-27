from __future__ import annotations

from pathlib import Path

import pytest

from uav_crop_analysis.errors import JobStateError
from uav_crop_analysis.jobs import (
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    AnalysisResult,
    JobError,
    JobStage,
    JobStatus,
)


def _config(tmp_path: Path) -> AnalysisJobConfig:
    return AnalysisJobConfig(
        mission_id="mission-1",
        model_id="semantic-1",
        artifact_role="best",
        registry_path=tmp_path / "registry.json",
        inputs=(AnalysisInput("image-1", tmp_path / "image.png"),),
        output_root=tmp_path / "results",
        tile_size=16,
        overlap=4,
    )


def test_job_state_machine_enforces_monotonic_progress_and_retry(tmp_path: Path) -> None:
    queued = AnalysisJob("job-state", _config(tmp_path))
    running = queued.start()
    progressed = running.report_progress(JobStage.TILE_INFERENCE, 0.4)

    assert running.attempt == 1
    assert progressed.status is JobStatus.RUNNING
    with pytest.raises(JobStateError, match="monotonic"):
        progressed.report_progress(JobStage.TILE_INFERENCE, 0.3)
    with pytest.raises(JobStateError, match="stage"):
        progressed.report_progress(JobStage.PREPARE, 0.5)

    failed = progressed.fail(JobError("out_of_memory", "OOM", True, {}))
    retried = failed.retry().start()

    assert retried.attempt == 2
    assert retried.error is None
    assert retried.progress == 0.0


def test_queued_and_running_jobs_have_distinct_cancel_paths(tmp_path: Path) -> None:
    queued = AnalysisJob("job-cancel-queued", _config(tmp_path))
    assert queued.request_cancel().status is JobStatus.CANCELLED

    running = AnalysisJob("job-cancel-running", _config(tmp_path)).start()
    requested = running.request_cancel()
    cancelled = requested.cancel()

    assert requested.status is JobStatus.CANCEL_REQUESTED
    assert cancelled.status is JobStatus.CANCELLED
    assert cancelled.stage is JobStage.TERMINAL


def test_completed_job_requires_atomic_result(tmp_path: Path) -> None:
    running = AnalysisJob("job-complete", _config(tmp_path)).start()
    result = AnalysisResult(tmp_path / "attempt-1", "a" * 64, (), {"model_id": "m"})
    completed = running.complete(result)

    assert completed.status is JobStatus.COMPLETED
    assert completed.progress == 1.0
    with pytest.raises(JobStateError):
        completed.retry()
