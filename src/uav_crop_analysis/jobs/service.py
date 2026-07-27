"""Parent-process orchestration of persisted jobs and worker messages."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from uav_crop_analysis.errors import JobNotFoundError, JobStateError
from uav_crop_analysis.jobs.models import (
    AnalysisJob,
    AnalysisJobConfig,
    JobError,
    JobEventType,
    JobStatus,
)
from uav_crop_analysis.jobs.repository import AnalysisJobRepository
from uav_crop_analysis.jobs.pipeline import cleanup_staging_artifacts
from uav_crop_analysis.jobs.worker import (
    ProcessAnalysisWorker,
    ProcessWorkerHandle,
    WorkerMessage,
    WorkerMessageType,
    result_from_payload,
)


class AnalysisJobService:
    def __init__(
        self,
        repository: AnalysisJobRepository,
        worker: ProcessAnalysisWorker | None = None,
        max_workers: int = 1,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        self.repository = repository
        self.worker = worker or ProcessAnalysisWorker()
        self.max_workers = max_workers
        self._handles: dict[str, ProcessWorkerHandle] = {}

    def submit(self, config: AnalysisJobConfig, job_id: str | None = None) -> AnalysisJob:
        job = AnalysisJob(job_id or f"job-{uuid4().hex}", config)
        self.repository.add(job, job.event(JobEventType.CREATED, "analysis job queued"))
        return job

    def start(self, job_id: str) -> AnalysisJob:
        if job_id in self._handles:
            raise JobStateError(f"job already has an active worker: {job_id}")
        if len(self._handles) >= self.max_workers:
            raise JobStateError("analysis worker capacity is full")
        job = self._require_job(job_id).start()
        self.repository.save(job, job.event(JobEventType.STARTED, "worker starting"))
        try:
            self._handles[job_id] = self.worker.start(job)
        except BaseException as exc:
            error = JobError(
                code="worker_start_failed",
                message=str(exc) or type(exc).__name__,
                retryable=True,
                context={"exception_type": type(exc).__name__},
            )
            job = job.fail(error)
            self.repository.save(job, job.event(JobEventType.FAILED, error.message))
        return job

    def cancel(self, job_id: str) -> AnalysisJob:
        job = self._require_job(job_id).request_cancel()
        event_type = (
            JobEventType.CANCELLED
            if job.status is JobStatus.CANCELLED
            else JobEventType.CANCEL_REQUESTED
        )
        self.repository.save(job, job.event(event_type, "cancellation requested"))
        handle = self._handles.get(job_id)
        if handle is not None:
            handle.request_cancel()
        return job

    def retry(self, job_id: str, *, force: bool = False, start: bool = True) -> AnalysisJob:
        self._retire_handle(job_id)
        current = self._require_job(job_id)
        if current.status is JobStatus.FAILED and current.error is not None:
            if not current.error.retryable and not force:
                raise JobStateError(f"job error is not retryable: {current.error.code}")
        job = current.retry()
        self.repository.save(job, job.event(JobEventType.RETRIED, "job queued for retry"))
        return self.start(job_id) if start else job

    def poll(self, job_id: str) -> AnalysisJob:
        job = self._require_job(job_id)
        handle = self._handles.get(job_id)
        if handle is None:
            return job
        job = self._apply_messages(job, handle.drain_messages())
        if not handle.is_alive:
            job = self._apply_messages(job, handle.drain_messages(wait_timeout=0.2))
            if job.status in {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}:
                error = JobError(
                    code="worker_exited",
                    message=f"worker exited without terminal event (code={handle.exit_code})",
                    retryable=True,
                    context={"exit_code": handle.exit_code},
                )
                job = job.fail(error)
                self.repository.save(job, job.event(JobEventType.FAILED, error.message))
                cleanup_staging_artifacts(job.config.output_root / job.job_id)
            handle.close(timeout=0.1)
            self._handles.pop(job_id, None)
        return job

    def wait(self, job_id: str, timeout: float = 60.0, interval: float = 0.02) -> AnalysisJob:
        deadline = time.monotonic() + timeout
        while True:
            job = self.poll(job_id)
            if job.status in {JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED}:
                self._retire_handle(job_id)
                return job
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for analysis job: {job_id}")
            time.sleep(interval)

    def recover_interrupted(self) -> tuple[AnalysisJob, ...]:
        interrupted = self.repository.list_by_status(
            (JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED)
        )
        recovered = []
        for job in interrupted:
            error = JobError(
                code="worker_interrupted",
                message="application restarted while worker was active",
                retryable=True,
                context={},
            )
            failed = job.fail(error)
            cleanup_staging_artifacts(job.config.output_root / job.job_id)
            self.repository.save(
                failed,
                failed.event(JobEventType.RECOVERED, error.message),
            )
            recovered.append(failed)
        return tuple(recovered)

    def resume_queued(self) -> tuple[AnalysisJob, ...]:
        return self.dispatch_queued()

    def dispatch_queued(self) -> tuple[AnalysisJob, ...]:
        available = max(0, self.max_workers - len(self._handles))
        queued = self.repository.list_by_status((JobStatus.QUEUED,))[:available]
        return tuple(self.start(job.job_id) for job in queued)

    def shutdown(self) -> None:
        for job_id, handle in tuple(self._handles.items()):
            handle.request_cancel()
            handle.close()
            self._handles.pop(job_id, None)

    def _apply_messages(
        self,
        job: AnalysisJob,
        messages: tuple[WorkerMessage, ...],
    ) -> AnalysisJob:
        for message in _coalesce_progress(messages):
            if message.message_type is WorkerMessageType.PROGRESS:
                if message.stage is None or message.progress is None:
                    continue
                job = job.report_progress(message.stage, message.progress)
                self.repository.save(
                    job,
                    job.event(
                        JobEventType.PROGRESS,
                        message.detail,
                        {"worker_progress": message.progress},
                    ),
                )
            elif message.message_type is WorkerMessageType.COMPLETED:
                if message.result is None:
                    raise JobStateError("worker completed without a result")
                job = job.complete(result_from_payload(message.result))
                self.repository.save(job, job.event(JobEventType.COMPLETED, "analysis completed"))
            elif message.message_type is WorkerMessageType.CANCELLED:
                job = job.cancel()
                self.repository.save(job, job.event(JobEventType.CANCELLED, "analysis cancelled"))
            elif message.message_type is WorkerMessageType.FAILED:
                payload: dict[str, Any] = message.error or {}
                error = JobError(
                    code=str(payload.get("code", "worker_failed")),
                    message=str(payload.get("message", "worker failed")),
                    retryable=bool(payload.get("retryable", False)),
                    context=payload.get("context", {}),
                )
                job = job.fail(error)
                self.repository.save(job, job.event(JobEventType.FAILED, error.message))
        return job

    def _require_job(self, job_id: str) -> AnalysisJob:
        job = self.repository.get(job_id)
        if job is None:
            raise JobNotFoundError(f"analysis job does not exist: {job_id}")
        return job

    def _retire_handle(self, job_id: str) -> None:
        handle = self._handles.pop(job_id, None)
        if handle is not None:
            handle.close()


def _coalesce_progress(messages: tuple[WorkerMessage, ...]) -> tuple[WorkerMessage, ...]:
    coalesced: list[WorkerMessage] = []
    pending_progress: WorkerMessage | None = None
    for message in messages:
        if message.message_type is WorkerMessageType.PROGRESS:
            pending_progress = message
            continue
        if pending_progress is not None:
            coalesced.append(pending_progress)
            pending_progress = None
        coalesced.append(message)
    if pending_progress is not None:
        coalesced.append(pending_progress)
    return tuple(coalesced)
