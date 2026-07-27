"""Analysis job state, configuration, events, and persisted results."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping

from uav_crop_analysis.errors import JobStateError


SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"


class JobStage(str, Enum):
    QUEUED = "queued"
    PREPARE = "prepare"
    TILE_INFERENCE = "tile_inference"
    MERGE = "merge"
    METRICS = "metrics"
    EXPORT = "export"
    TERMINAL = "terminal"


STAGE_ORDER = {
    JobStage.QUEUED: 0,
    JobStage.PREPARE: 1,
    JobStage.TILE_INFERENCE: 2,
    JobStage.MERGE: 3,
    JobStage.METRICS: 4,
    JobStage.EXPORT: 5,
    JobStage.TERMINAL: 6,
}


class JobEventType(str, Enum):
    CREATED = "created"
    STARTED = "started"
    PROGRESS = "progress"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"
    RETRIED = "retried"
    RECOVERED = "recovered"


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    image_id: str
    source_path: Path

    def __post_init__(self) -> None:
        if not SAFE_ID_PATTERN.fullmatch(self.image_id):
            raise JobStateError(f"unsafe image ID: {self.image_id}")
        object.__setattr__(self, "source_path", Path(self.source_path).expanduser().resolve())


@dataclass(frozen=True, slots=True)
class AnalysisJobConfig:
    mission_id: str
    model_id: str
    artifact_role: str
    registry_path: Path
    inputs: tuple[AnalysisInput, ...]
    output_root: Path
    device: str = "cpu"
    tile_size: int = 640
    overlap: int = 64
    weed_threshold: float = 0.5

    def __post_init__(self) -> None:
        for name, value in (
            ("mission_id", self.mission_id),
            ("model_id", self.model_id),
            ("artifact_role", self.artifact_role),
        ):
            if not value.strip():
                raise JobStateError(f"{name} must not be empty")
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "registry_path", Path(self.registry_path).expanduser().resolve())
        object.__setattr__(self, "output_root", Path(self.output_root).expanduser().resolve())
        if not self.inputs:
            raise JobStateError("analysis job requires at least one image")
        image_ids = [item.image_id for item in self.inputs]
        if len(image_ids) != len(set(image_ids)):
            raise JobStateError("analysis image IDs must be unique")
        if self.tile_size < 8:
            raise JobStateError("tile_size must be at least 8 pixels")
        if not 0 <= self.overlap < self.tile_size:
            raise JobStateError("overlap must be in [0, tile_size)")
        if not 0.0 < self.weed_threshold < 1.0:
            raise JobStateError("weed_threshold must be in (0, 1)")


@dataclass(frozen=True, slots=True)
class JobError:
    code: str
    message: str
    retryable: bool
    context: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.code or not self.message:
            raise JobStateError("job error requires code and message")
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    artifact_dir: Path
    manifest_sha256: str
    image_summaries: tuple[Mapping[str, Any], ...]
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_dir", Path(self.artifact_dir).resolve())
        object.__setattr__(
            self,
            "image_summaries",
            tuple(MappingProxyType(dict(item)) for item in self.image_summaries),
        )
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))


@dataclass(frozen=True, slots=True)
class JobEvent:
    job_id: str
    event_type: JobEventType
    status: JobStatus
    stage: JobStage
    progress: float
    occurred_at: datetime
    message: str = ""
    payload: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True, init=False)
class AnalysisJob:
    job_id: str
    config: AnalysisJobConfig
    status: JobStatus
    stage: JobStage
    progress: float
    attempt: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: JobError | None
    result: AnalysisResult | None

    def __init__(
        self,
        job_id: str,
        config: AnalysisJobConfig,
        status: JobStatus = JobStatus.QUEUED,
        stage: JobStage = JobStage.QUEUED,
        progress: float = 0.0,
        attempt: int = 0,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        error: JobError | None = None,
        result: AnalysisResult | None = None,
    ) -> None:
        now = utc_now()
        object.__setattr__(self, "job_id", job_id)
        object.__setattr__(self, "config", config)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "stage", stage)
        object.__setattr__(self, "progress", progress)
        object.__setattr__(self, "attempt", attempt)
        object.__setattr__(self, "created_at", created_at or now)
        object.__setattr__(self, "updated_at", updated_at or now)
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "finished_at", finished_at)
        object.__setattr__(self, "error", error)
        object.__setattr__(self, "result", result)
        self._validate()

    def _validate(self) -> None:
        if not SAFE_ID_PATTERN.fullmatch(self.job_id):
            raise JobStateError(f"unsafe job ID: {self.job_id}")
        if not 0.0 <= self.progress <= 1.0:
            raise JobStateError("job progress must be in [0, 1]")
        if self.attempt < 0:
            raise JobStateError("job attempt must be non-negative")
        if self.status is JobStatus.COMPLETED and self.result is None:
            raise JobStateError("completed job requires a result")
        if self.status is JobStatus.FAILED and self.error is None:
            raise JobStateError("failed job requires an error")

    def start(self, at: datetime | None = None) -> AnalysisJob:
        self._require_status(JobStatus.QUEUED)
        now = at or utc_now()
        return replace(
            self,
            status=JobStatus.RUNNING,
            stage=JobStage.PREPARE,
            progress=0.0,
            attempt=self.attempt + 1,
            started_at=now,
            finished_at=None,
            updated_at=now,
            error=None,
            result=None,
        )

    def report_progress(
        self,
        stage: JobStage,
        progress: float,
        at: datetime | None = None,
    ) -> AnalysisJob:
        if self.status not in {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
            raise JobStateError(f"cannot report progress while job is {self.status.value}")
        if progress < self.progress or not 0.0 <= progress < 1.0:
            raise JobStateError("running progress must be monotonic and below 1")
        if STAGE_ORDER[stage] < STAGE_ORDER[self.stage]:
            raise JobStateError("job stage must be monotonic")
        return replace(self, stage=stage, progress=progress, updated_at=at or utc_now())

    def request_cancel(self, at: datetime | None = None) -> AnalysisJob:
        now = at or utc_now()
        if self.status is JobStatus.QUEUED:
            return replace(
                self,
                status=JobStatus.CANCELLED,
                stage=JobStage.TERMINAL,
                finished_at=now,
                updated_at=now,
            )
        self._require_status(JobStatus.RUNNING)
        return replace(self, status=JobStatus.CANCEL_REQUESTED, updated_at=now)

    def cancel(self, at: datetime | None = None) -> AnalysisJob:
        if self.status not in {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
            raise JobStateError(f"cannot cancel job while it is {self.status.value}")
        now = at or utc_now()
        return replace(
            self,
            status=JobStatus.CANCELLED,
            stage=JobStage.TERMINAL,
            finished_at=now,
            updated_at=now,
        )

    def fail(self, error: JobError, at: datetime | None = None) -> AnalysisJob:
        if self.status not in {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
            raise JobStateError(f"cannot fail job while it is {self.status.value}")
        now = at or utc_now()
        return replace(
            self,
            status=JobStatus.FAILED,
            stage=JobStage.TERMINAL,
            finished_at=now,
            updated_at=now,
            error=error,
        )

    def complete(self, result: AnalysisResult, at: datetime | None = None) -> AnalysisJob:
        if self.status not in {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
            raise JobStateError(f"cannot complete job while it is {self.status.value}")
        now = at or utc_now()
        return replace(
            self,
            status=JobStatus.COMPLETED,
            stage=JobStage.TERMINAL,
            progress=1.0,
            finished_at=now,
            updated_at=now,
            result=result,
        )

    def retry(self, at: datetime | None = None) -> AnalysisJob:
        if self.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
            raise JobStateError(f"cannot retry job while it is {self.status.value}")
        return replace(
            self,
            status=JobStatus.QUEUED,
            stage=JobStage.QUEUED,
            progress=0.0,
            updated_at=at or utc_now(),
            started_at=None,
            finished_at=None,
            error=None,
            result=None,
        )

    def event(
        self,
        event_type: JobEventType,
        message: str = "",
        payload: Mapping[str, Any] | None = None,
    ) -> JobEvent:
        return JobEvent(
            job_id=self.job_id,
            event_type=event_type,
            status=self.status,
            stage=self.stage,
            progress=self.progress,
            occurred_at=self.updated_at,
            message=message,
            payload=payload,
        )

    def _require_status(self, status: JobStatus) -> None:
        if self.status is not status:
            raise JobStateError(f"expected {status.value}, got {self.status.value}")
