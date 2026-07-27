"""SQLite persistence for analysis jobs and parent-process event history."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from uav_crop_analysis.adapters.sqlite import SQLiteMissionRepository
from uav_crop_analysis.errors import PersistenceError
from uav_crop_analysis.jobs.models import (
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


class SQLiteAnalysisJobRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        SQLiteMissionRepository(self.database_path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def add(self, job: AnalysisJob, event: JobEvent) -> None:
        try:
            with self._connection() as connection, connection:
                connection.execute(
                    """
                    INSERT INTO analysis_jobs VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    _job_values(job),
                )
                _insert_event(connection, event)
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"failed to add analysis job: {job.job_id}",
                context={"job_id": job.job_id},
            ) from exc

    def get(self, job_id: str) -> AnalysisJob | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT * FROM analysis_jobs WHERE job_id = ?",
                    (job_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError(f"failed to read analysis job: {job_id}") from exc
        return _job_from_row(row) if row is not None else None

    def save(self, job: AnalysisJob, event: JobEvent) -> None:
        try:
            with self._connection() as connection, connection:
                cursor = connection.execute(
                    """
                    UPDATE analysis_jobs SET
                        mission_id = ?, config_json = ?, status = ?, stage = ?,
                        progress = ?, attempt = ?, created_at = ?, updated_at = ?,
                        started_at = ?, finished_at = ?, error_json = ?, result_json = ?
                    WHERE job_id = ?
                    """,
                    (*_job_values(job)[1:], job.job_id),
                )
                if cursor.rowcount != 1:
                    raise PersistenceError(f"analysis job does not exist: {job.job_id}")
                _insert_event(connection, event)
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"failed to update analysis job: {job.job_id}",
                context={"job_id": job.job_id},
            ) from exc

    def list_by_status(self, statuses: tuple[JobStatus, ...]) -> tuple[AnalysisJob, ...]:
        if not statuses:
            return ()
        placeholders = ",".join("?" for _ in statuses)
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    f"""
                    SELECT * FROM analysis_jobs
                    WHERE status IN ({placeholders})
                    ORDER BY created_at, job_id
                    """,  # noqa: S608
                    tuple(status.value for status in statuses),
                ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError("failed to list analysis jobs") from exc
        return tuple(_job_from_row(row) for row in rows)

    def list_for_mission(self, mission_id: str) -> tuple[AnalysisJob, ...]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM analysis_jobs
                    WHERE mission_id = ?
                    ORDER BY updated_at DESC, job_id DESC
                    """,
                    (mission_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"failed to list analysis jobs for mission: {mission_id}",
                context={"mission_id": mission_id},
            ) from exc
        return tuple(_job_from_row(row) for row in rows)

    def list_events(self, job_id: str) -> tuple[JobEvent, ...]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM analysis_job_events
                    WHERE job_id = ?
                    ORDER BY sequence_id
                    """,
                    (job_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError(f"failed to list events for job: {job_id}") from exc
        return tuple(
            JobEvent(
                job_id=row["job_id"],
                event_type=JobEventType(row["event_type"]),
                status=JobStatus(row["status"]),
                stage=JobStage(row["stage"]),
                progress=row["progress"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                message=row["message"],
                payload=json.loads(row["payload_json"]) if row["payload_json"] else None,
            )
            for row in rows
        )


def _config_to_dict(config: AnalysisJobConfig) -> dict[str, Any]:
    return {
        "mission_id": config.mission_id,
        "model_id": config.model_id,
        "artifact_role": config.artifact_role,
        "registry_path": str(config.registry_path),
        "inputs": [
            {"image_id": item.image_id, "source_path": str(item.source_path)}
            for item in config.inputs
        ],
        "output_root": str(config.output_root),
        "device": config.device,
        "tile_size": config.tile_size,
        "overlap": config.overlap,
        "weed_threshold": config.weed_threshold,
    }


def _config_from_dict(payload: dict[str, Any]) -> AnalysisJobConfig:
    return AnalysisJobConfig(
        mission_id=payload["mission_id"],
        model_id=payload["model_id"],
        artifact_role=payload["artifact_role"],
        registry_path=Path(payload["registry_path"]),
        inputs=tuple(
            AnalysisInput(item["image_id"], Path(item["source_path"]))
            for item in payload["inputs"]
        ),
        output_root=Path(payload["output_root"]),
        device=payload["device"],
        tile_size=int(payload["tile_size"]),
        overlap=int(payload["overlap"]),
        weed_threshold=float(payload["weed_threshold"]),
    )


def _result_to_dict(result: AnalysisResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "artifact_dir": str(result.artifact_dir),
        "manifest_sha256": result.manifest_sha256,
        "image_summaries": [dict(item) for item in result.image_summaries],
        "provenance": dict(result.provenance),
    }


def _result_from_dict(payload: dict[str, Any] | None) -> AnalysisResult | None:
    if payload is None:
        return None
    return AnalysisResult(
        artifact_dir=Path(payload["artifact_dir"]),
        manifest_sha256=payload["manifest_sha256"],
        image_summaries=tuple(payload["image_summaries"]),
        provenance=payload["provenance"],
    )


def _error_to_dict(error: JobError | None) -> dict[str, Any] | None:
    if error is None:
        return None
    return {
        "code": error.code,
        "message": error.message,
        "retryable": error.retryable,
        "context": dict(error.context),
    }


def _error_from_dict(payload: dict[str, Any] | None) -> JobError | None:
    if payload is None:
        return None
    return JobError(
        code=payload["code"],
        message=payload["message"],
        retryable=bool(payload["retryable"]),
        context=payload["context"],
    )


def _job_values(job: AnalysisJob) -> tuple[Any, ...]:
    error = _error_to_dict(job.error)
    result = _result_to_dict(job.result)
    return (
        job.job_id,
        job.config.mission_id,
        json.dumps(_config_to_dict(job.config), sort_keys=True),
        job.status.value,
        job.stage.value,
        job.progress,
        job.attempt,
        job.created_at.isoformat(),
        job.updated_at.isoformat(),
        job.started_at.isoformat() if job.started_at else None,
        job.finished_at.isoformat() if job.finished_at else None,
        json.dumps(error, sort_keys=True) if error else None,
        json.dumps(result, sort_keys=True) if result else None,
        # Keep tuple width aligned with the 13-column INSERT.
    )


def _job_from_row(row: sqlite3.Row) -> AnalysisJob:
    return AnalysisJob(
        job_id=row["job_id"],
        config=_config_from_dict(json.loads(row["config_json"])),
        status=JobStatus(row["status"]),
        stage=JobStage(row["stage"]),
        progress=row["progress"],
        attempt=row["attempt"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        finished_at=(
            datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None
        ),
        error=_error_from_dict(json.loads(row["error_json"]) if row["error_json"] else None),
        result=_result_from_dict(
            json.loads(row["result_json"]) if row["result_json"] else None
        ),
    )


def _insert_event(connection: sqlite3.Connection, event: JobEvent) -> None:
    connection.execute(
        """
        INSERT INTO analysis_job_events(
            job_id, event_type, status, stage, progress,
            occurred_at, message, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.job_id,
            event.event_type.value,
            event.status.value,
            event.stage.value,
            event.progress,
            event.occurred_at.isoformat(),
            event.message,
            json.dumps(dict(event.payload), sort_keys=True) if event.payload else None,
        ),
    )
