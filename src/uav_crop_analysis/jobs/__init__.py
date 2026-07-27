"""Persisted analysis jobs, semantic pipeline, and worker process services."""

from typing import TYPE_CHECKING, Any

from .models import (
    AnalysisInput,
    AnalysisJob,
    AnalysisJobConfig,
    AnalysisResult,
    JobError,
    JobEvent,
    JobEventType,
    JobStage,
    JobStatus,
)
from .repository import AnalysisJobRepository

if TYPE_CHECKING:
    from .pipeline import SemanticTilePipeline
    from .service import AnalysisJobService
    from .worker import ProcessAnalysisWorker

__all__ = [
    "AnalysisInput",
    "AnalysisJob",
    "AnalysisJobConfig",
    "AnalysisJobRepository",
    "AnalysisJobService",
    "AnalysisResult",
    "JobError",
    "JobEvent",
    "JobEventType",
    "JobStage",
    "JobStatus",
    "ProcessAnalysisWorker",
    "SemanticTilePipeline",
]


def __getattr__(name: str) -> Any:
    if name == "AnalysisJobService":
        from .service import AnalysisJobService

        return AnalysisJobService
    if name == "ProcessAnalysisWorker":
        from .worker import ProcessAnalysisWorker

        return ProcessAnalysisWorker
    if name == "SemanticTilePipeline":
        from .pipeline import SemanticTilePipeline

        return SemanticTilePipeline
    raise AttributeError(name)
