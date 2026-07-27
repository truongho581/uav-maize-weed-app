"""Deterministic three-stream telemetry demo used without SITL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from uav_crop_analysis.domain import GeoPoint
from uav_crop_analysis.integrations.models import TelemetryFrame


def simulate_three_drone_streams(
    *,
    samples_per_drone: int = 4,
    started_at: datetime | None = None,
) -> tuple[TelemetryFrame, ...]:
    if samples_per_drone < 1:
        raise ValueError("samples_per_drone must be positive")
    origin = started_at or datetime.now(timezone.utc)
    frames = []
    for sequence in range(samples_per_drone):
        for lane in range(3):
            frames.append(
                TelemetryFrame(
                    system_id=lane + 1,
                    drone_id=f"drone-{lane + 1}",
                    sequence=sequence,
                    recorded_at=origin + timedelta(seconds=sequence),
                    position=GeoPoint(
                        10.75 + lane * 0.00002 + sequence * 0.00001,
                        106.67 + sequence * 0.00001,
                    ),
                    relative_altitude_m=10.0,
                )
            )
    return tuple(frames)
