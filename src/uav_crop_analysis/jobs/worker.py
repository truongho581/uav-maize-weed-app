"""Spawn-based worker process for semantic and maize instance analysis jobs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import multiprocessing
from pathlib import Path
from queue import Empty
import traceback
from typing import Any

from uav_crop_analysis.errors import (
    PipelineCancelledError,
    UAVCropAnalysisError,
)
from uav_crop_analysis.inference import ModelRegistry, ModelTask, SegmenterFactory
from uav_crop_analysis.jobs.models import AnalysisJob, AnalysisResult, JobStage
from uav_crop_analysis.jobs.pipeline import InstanceTilePipeline, SemanticTilePipeline


class WorkerMessageType(str, Enum):
    PROGRESS = "progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WorkerMessage:
    message_type: WorkerMessageType
    stage: JobStage | None = None
    progress: float | None = None
    detail: str = ""
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class ProcessWorkerHandle:
    def __init__(self, process: Any, message_queue: Any, cancel_event: Any) -> None:
        self.process = process
        self.message_queue = message_queue
        self.cancel_event = cancel_event

    @property
    def is_alive(self) -> bool:
        return bool(self.process.is_alive())

    @property
    def exit_code(self) -> int | None:
        return self.process.exitcode

    def request_cancel(self) -> None:
        self.cancel_event.set()

    def drain_messages(self, wait_timeout: float = 0.0) -> tuple[WorkerMessage, ...]:
        messages: list[WorkerMessage] = []
        if wait_timeout > 0:
            try:
                messages.append(self.message_queue.get(timeout=wait_timeout))
            except Empty:
                return ()
        while True:
            try:
                messages.append(self.message_queue.get_nowait())
            except Empty:
                break
        return tuple(messages)

    def close(self, timeout: float = 1.0) -> None:
        self.process.join(timeout)
        if self.process.is_alive():
            self.cancel_event.set()
            self.process.join(timeout)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout)
        self.message_queue.close()
        self.message_queue.join_thread()


class ProcessAnalysisWorker:
    def __init__(self, start_method: str = "spawn") -> None:
        self._context: Any = multiprocessing.get_context(start_method)

    def start(self, job: AnalysisJob) -> ProcessWorkerHandle:
        if job.attempt < 1:
            raise ValueError("worker requires a started job")
        message_queue = self._context.Queue()
        cancel_event = self._context.Event()
        process = self._context.Process(
            target=_analysis_worker_entry,
            args=(job, message_queue, cancel_event),
            name=f"uav-analysis-{job.job_id}",
            daemon=True,
        )
        process.start()
        return ProcessWorkerHandle(process, message_queue, cancel_event)


def _analysis_worker_entry(job: AnalysisJob, message_queue: Any, cancel_event: Any) -> None:
    try:
        registry = ModelRegistry.from_file(job.config.registry_path)
        manifest = registry.get(job.config.model_id)
        factory = SegmenterFactory(registry)
        pipeline: SemanticTilePipeline | InstanceTilePipeline
        if manifest.task is ModelTask.SEMANTIC:
            pipeline = SemanticTilePipeline(
                factory.load_semantic(
                    job.config.model_id,
                    job.config.artifact_role,
                    device=job.config.device,
                )
            )
        elif manifest.task is ModelTask.MAIZE_INSTANCE:
            pipeline = InstanceTilePipeline(
                factory.load_instance(
                    job.config.model_id,
                    job.config.artifact_role,
                    device=job.config.device,
                )
            )
        else:
            raise ValueError(f"unsupported analysis task: {manifest.task.value}")

        def emit(stage: JobStage, progress: float, detail: str) -> None:
            message_queue.put(
                WorkerMessage(
                    WorkerMessageType.PROGRESS,
                    stage=stage,
                    progress=progress,
                    detail=detail,
                )
            )

        result = pipeline.run(job, emit, cancel_event.is_set)
        message_queue.put(
            WorkerMessage(
                WorkerMessageType.COMPLETED,
                result=result_to_payload(result),
            )
        )
    except PipelineCancelledError:
        message_queue.put(WorkerMessage(WorkerMessageType.CANCELLED))
    except BaseException as exc:
        message_queue.put(
            WorkerMessage(
                WorkerMessageType.FAILED,
                error=classify_worker_error(exc),
            )
        )


def result_to_payload(result: AnalysisResult) -> dict[str, Any]:
    return {
        "artifact_dir": str(result.artifact_dir),
        "manifest_sha256": result.manifest_sha256,
        "image_summaries": [dict(item) for item in result.image_summaries],
        "provenance": dict(result.provenance),
    }


def result_from_payload(payload: dict[str, Any]) -> AnalysisResult:
    return AnalysisResult(
        artifact_dir=Path(payload["artifact_dir"]),
        manifest_sha256=payload["manifest_sha256"],
        image_summaries=tuple(payload["image_summaries"]),
        provenance=payload["provenance"],
    )


def classify_worker_error(exc: BaseException) -> dict[str, Any]:
    message = str(exc) or type(exc).__name__
    lowered = message.lower()
    if isinstance(exc, MemoryError) or "out of memory" in lowered:
        code = "job_out_of_memory"
        retryable = True
    elif isinstance(exc, OSError):
        code = "job_io_error"
        retryable = True
    elif isinstance(exc, UAVCropAnalysisError):
        code = exc.code
        retryable = False
    else:
        code = "worker_unhandled_error"
        retryable = False
    context = {
        "exception_type": type(exc).__name__,
        "traceback": traceback.format_exc(limit=20),
    }
    if isinstance(exc, UAVCropAnalysisError):
        context.update(exc.context)
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "context": context,
    }
