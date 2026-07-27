"""Ordering and identity guard for telemetry from multiple drones."""

from __future__ import annotations

from uav_crop_analysis.domain import DroneId, MissionId, TelemetrySample
from uav_crop_analysis.errors import IntegrationError
from uav_crop_analysis.integrations.models import SystemMapping, TelemetryFrame


class TelemetryStreamGuard:
    def __init__(self, mappings: tuple[SystemMapping, ...]) -> None:
        if not mappings:
            raise IntegrationError("at least one system mapping is required")
        system_ids = [item.system_id for item in mappings]
        drone_ids = [item.drone_id for item in mappings]
        if len(system_ids) != len(set(system_ids)):
            raise IntegrationError("duplicate MAVLink system_id mapping")
        if len(drone_ids) != len(set(drone_ids)):
            raise IntegrationError("a drone_id cannot map to multiple systems")
        self._drone_by_system = {item.system_id: item.drone_id for item in mappings}
        self._last_by_system: dict[int, TelemetryFrame] = {}
        self.dropped_duplicate_count = 0
        self.dropped_out_of_order_count = 0

    def accept(self, mission_id: str, frame: TelemetryFrame) -> TelemetrySample | None:
        expected_drone = self._drone_by_system.get(frame.system_id)
        if expected_drone is None:
            raise IntegrationError(f"unmapped MAVLink system_id: {frame.system_id}")
        if frame.drone_id != expected_drone:
            raise IntegrationError(
                f"system_id {frame.system_id} belongs to {expected_drone}, not {frame.drone_id}"
            )
        previous = self._last_by_system.get(frame.system_id)
        if previous is not None:
            if _same_sample(previous, frame):
                self.dropped_duplicate_count += 1
                return None
            if (
                frame.recorded_at <= previous.recorded_at
                or frame.sequence <= previous.sequence
            ):
                self.dropped_out_of_order_count += 1
                return None
        self._last_by_system[frame.system_id] = frame
        return TelemetrySample(
            mission_id=MissionId(mission_id),
            drone_id=DroneId(frame.drone_id),
            recorded_at=frame.recorded_at,
            position=frame.position,
            relative_altitude_m=frame.relative_altitude_m,
        )


def _same_sample(left: TelemetryFrame, right: TelemetryFrame) -> bool:
    return (
        left.recorded_at == right.recorded_at
        and left.position == right.position
        and left.relative_altitude_m == right.relative_altitude_m
    )
