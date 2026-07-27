"""Optional MAVSDK adapter intentionally restricted to read-only operations."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
import importlib
from typing import Any

from uav_crop_analysis.domain import GeoPoint
from uav_crop_analysis.errors import DependencyUnavailableError, IntegrationError
from uav_crop_analysis.integrations.models import (
    MavsdkEndpoint,
    MavsdkMissionItem,
    TelemetryFrame,
)


SystemFactory = Callable[[MavsdkEndpoint], Any]


class MavsdkReadOnlyAdapter:
    """Connect, read position, and download mission; no command surface exists."""

    commands_enabled = False

    def __init__(
        self,
        system_factory: SystemFactory | None = None,
        *,
        reconnect_delay_seconds: float = 0.25,
    ) -> None:
        self._system_factory = system_factory or _default_system_factory
        self._reconnect_delay = reconnect_delay_seconds

    async def stream_positions(
        self,
        endpoint: MavsdkEndpoint,
        *,
        max_reconnects: int = 3,
    ) -> AsyncIterator[TelemetryFrame]:
        if max_reconnects < 0:
            raise IntegrationError("max_reconnects must be non-negative")
        sequence = 0
        reconnect_count = 0
        while True:
            try:
                system = self._system_factory(endpoint)
                await system.connect(system_address=endpoint.system_address)
                await _wait_connected(system)
                received_any = False
                async for position in system.telemetry.position():
                    received_any = True
                    yield TelemetryFrame(
                        system_id=endpoint.system_id,
                        drone_id=endpoint.drone_id,
                        sequence=sequence,
                        recorded_at=datetime.now(timezone.utc),
                        position=GeoPoint(
                            float(position.latitude_deg),
                            float(position.longitude_deg),
                        ),
                        relative_altitude_m=max(
                            0.0,
                            float(position.relative_altitude_m),
                        ),
                        reconnect_count=reconnect_count,
                    )
                    sequence += 1
                if not received_any:
                    raise IntegrationError("MAVSDK position stream ended without data")
            except asyncio.CancelledError:
                raise
            except DependencyUnavailableError:
                raise
            except Exception as exc:
                if reconnect_count >= max_reconnects:
                    raise IntegrationError(
                        f"MAVSDK telemetry disconnected after {reconnect_count} reconnects",
                        context={
                            "system_id": endpoint.system_id,
                            "drone_id": endpoint.drone_id,
                        },
                    ) from exc
            reconnect_count += 1
            if reconnect_count > max_reconnects:
                return
            await asyncio.sleep(self._reconnect_delay)

    async def download_mission(
        self,
        endpoint: MavsdkEndpoint,
    ) -> tuple[MavsdkMissionItem, ...]:
        system = self._system_factory(endpoint)
        await system.connect(system_address=endpoint.system_address)
        await _wait_connected(system)
        try:
            raw_items = await system.mission_raw.download_mission()
        except Exception as exc:
            raise IntegrationError(
                "MAVSDK mission download failed",
                context={"system_id": endpoint.system_id},
            ) from exc
        return tuple(_mission_item(item, index) for index, item in enumerate(raw_items))


async def _wait_connected(system: Any) -> None:
    async for state in system.core.connection_state():
        if bool(state.is_connected):
            return
    raise IntegrationError("MAVSDK connection stream ended before connection")


def _default_system_factory(_endpoint: MavsdkEndpoint) -> Any:
    try:
        module = importlib.import_module("mavsdk")
    except ImportError as exc:
        raise DependencyUnavailableError(
            "MAVSDK is not installed; install the drone optional dependency",
            context={"extra": "drone"},
        ) from exc
    return module.System()


def _mission_item(item: Any, index: int) -> MavsdkMissionItem:
    latitude = _scaled_coordinate(getattr(item, "x", None), 90.0)
    longitude = _scaled_coordinate(getattr(item, "y", None), 180.0)
    altitude = getattr(item, "z", None)
    return MavsdkMissionItem(
        sequence=int(getattr(item, "seq", index)),
        command=int(getattr(item, "command", 0)),
        frame=int(getattr(item, "frame", 0)),
        latitude=latitude,
        longitude=longitude,
        altitude_m=float(altitude) if altitude is not None else None,
    )


def _scaled_coordinate(value: object, limit: float) -> float | None:
    if value is None:
        return None
    number = float(str(value))
    if abs(number) > limit:
        number /= 10_000_000.0
    return number if abs(number) <= limit else None
