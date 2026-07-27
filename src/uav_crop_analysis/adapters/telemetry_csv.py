"""Mapped CSV telemetry reader with row-level validation reports."""

from __future__ import annotations

import csv
from datetime import datetime, timezone, tzinfo
from pathlib import Path

from uav_crop_analysis.application.import_models import (
    ImportIssue,
    IssueSeverity,
    TelemetryCsvMapping,
    TelemetryReadResult,
    TimestampFormat,
)
from uav_crop_analysis.domain import DroneId, GeoPoint, MissionId, TelemetrySample
from uav_crop_analysis.errors import DomainValidationError


class CsvTelemetryReader:
    def __init__(self, *, default_timezone: tzinfo = timezone.utc) -> None:
        self.default_timezone = default_timezone

    def read(
        self,
        telemetry_path: Path,
        mapping: TelemetryCsvMapping,
        mission_id: MissionId,
        drone_id: DroneId,
    ) -> TelemetryReadResult:
        path = Path(telemetry_path).expanduser().resolve()
        issues: list[ImportIssue] = []
        samples: list[TelemetrySample] = []
        seen_timestamps: set[datetime] = set()
        previous_timestamp: datetime | None = None

        try:
            handle = path.open("r", encoding="utf-8-sig", newline="")
        except OSError as exc:
            return TelemetryReadResult(
                samples=(),
                issues=(
                    ImportIssue(
                        code="telemetry_file_unreadable",
                        message=str(exc),
                        severity=IssueSeverity.ERROR,
                        drone_id=drone_id.value,
                        source=str(path),
                    ),
                ),
            )

        with handle:
            reader = csv.DictReader(handle)
            required = {
                mapping.timestamp_column,
                mapping.latitude_column,
                mapping.longitude_column,
                mapping.relative_altitude_column,
            }
            missing = sorted(required - set(reader.fieldnames or ()))
            if missing:
                return TelemetryReadResult(
                    samples=(),
                    issues=(
                        ImportIssue(
                            code="telemetry_missing_columns",
                            message=f"missing telemetry columns: {', '.join(missing)}",
                            severity=IssueSeverity.ERROR,
                            drone_id=drone_id.value,
                            source=str(path),
                        ),
                    ),
                )

            for row_number, row in enumerate(reader, start=2):
                try:
                    recorded_at = self._timestamp(
                        row[mapping.timestamp_column], mapping.timestamp_format
                    )
                    sample = TelemetrySample(
                        mission_id=mission_id,
                        drone_id=drone_id,
                        recorded_at=recorded_at,
                        position=GeoPoint(
                            float(row[mapping.latitude_column]),
                            float(row[mapping.longitude_column]),
                        ),
                        relative_altitude_m=float(row[mapping.relative_altitude_column]),
                    )
                except (KeyError, TypeError, ValueError, DomainValidationError) as exc:
                    issues.append(
                        ImportIssue(
                            code="invalid_telemetry_row",
                            message=str(exc),
                            severity=IssueSeverity.ERROR,
                            drone_id=drone_id.value,
                            source=str(path),
                            row_number=row_number,
                        )
                    )
                    continue

                if recorded_at in seen_timestamps:
                    issues.append(
                        ImportIssue(
                            code="duplicate_telemetry_timestamp",
                            message=f"duplicate telemetry timestamp: {recorded_at.isoformat()}",
                            severity=IssueSeverity.ERROR,
                            drone_id=drone_id.value,
                            source=str(path),
                            row_number=row_number,
                        )
                    )
                    continue
                if previous_timestamp is not None and recorded_at < previous_timestamp:
                    issues.append(
                        ImportIssue(
                            code="non_monotonic_telemetry",
                            message="telemetry rows are not ordered by timestamp",
                            severity=IssueSeverity.WARNING,
                            drone_id=drone_id.value,
                            source=str(path),
                            row_number=row_number,
                        )
                    )
                previous_timestamp = recorded_at
                seen_timestamps.add(recorded_at)
                samples.append(sample)

        samples.sort(key=lambda item: item.recorded_at)
        return TelemetryReadResult(samples=tuple(samples), issues=tuple(issues))

    def _timestamp(self, raw_value: str, timestamp_format: TimestampFormat) -> datetime:
        value = raw_value.strip()
        if timestamp_format is TimestampFormat.ISO8601:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=self.default_timezone)

        divisor = {
            TimestampFormat.UNIX_SECONDS: 1.0,
            TimestampFormat.UNIX_MILLISECONDS: 1_000.0,
            TimestampFormat.UNIX_MICROSECONDS: 1_000_000.0,
            TimestampFormat.UNIX_NANOSECONDS: 1_000_000_000.0,
        }[timestamp_format]
        return datetime.fromtimestamp(float(value) / divisor, tz=timezone.utc)
