from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from uav_crop_analysis.domain import GeoPoint
from uav_crop_analysis.errors import DependencyUnavailableError, IntegrationError
import uav_crop_analysis.integrations.mavsdk as mavsdk_module
from uav_crop_analysis.integrations import (
    MavsdkEndpoint,
    MavsdkMissionItem,
    MavsdkReadOnlyAdapter,
    QGroundControlLogReader,
    QGroundControlPlanReader,
    SystemMapping,
    TelemetryFrame,
    TelemetryStreamGuard,
    simulate_three_drone_streams,
)


NOW = datetime(2026, 7, 27, 15, 0, tzinfo=timezone.utc)


def _write_qgc_plan(path: Path) -> None:
    payload = {
        "fileType": "Plan",
        "version": 1,
        "groundStation": "QGroundControl",
        "mission": {
            "version": 2,
            "firmwareType": 12,
            "vehicleType": 2,
            "plannedHomePosition": [10.75, 106.67, 8.0],
            "items": [
                {
                    "type": "SimpleItem",
                    "command": 22,
                    "frame": 3,
                    "autoContinue": True,
                    "params": [0, 0, 0, None, 10.7501, 106.6701, 10],
                },
                {
                    "type": "ComplexItem",
                    "complexItemType": "survey",
                    "Altitude": 10,
                    "polygon": [
                        [10.75, 106.67],
                        [10.75, 106.671],
                        [10.751, 106.671],
                    ],
                    "TransectStyleComplexItem": {
                        "HoverAndCapture": True,
                        "VisualTransectPoints": [
                            [10.7501, 106.6701],
                            [10.7509, 106.6709],
                        ],
                        "CameraCalc": {
                            "FrontalOverlap": 75,
                            "SideOverlap": 65,
                        },
                    },
                },
            ],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_qgroundcontrol_plan_preserves_waypoints_survey_and_hover_capture(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ba drone.plan"
    _write_qgc_plan(source)

    plan = QGroundControlPlanReader().read(source)

    assert plan.plan_version == 1
    assert plan.planned_home == GeoPoint(10.75, 106.67)
    assert len(plan.waypoints) == 3
    assert plan.waypoints[0].command == 22
    assert plan.survey_areas[0].hover_and_capture is True
    assert plan.survey_areas[0].frontal_overlap_percent == 75
    assert len(plan.survey_areas[0].polygon) == 3


def test_qgroundcontrol_csv_maps_three_systems_and_drops_bad_order(
    tmp_path: Path,
) -> None:
    source = tmp_path / "telemetry QGC.csv"
    source.write_text(
        "timestamp,system_id,lat,lon,relative_alt\n"
        "2026-07-27T15:00:00+00:00,1,107500000,1066700000,10000\n"
        "2026-07-27T15:00:00+00:00,1,107500000,1066700000,10000\n"
        "2026-07-27T14:59:59+00:00,1,107500100,1066700100,10000\n"
        "2026-07-27T15:00:00+00:00,2,107500200,1066700000,10000\n"
        "2026-07-27T15:00:00+00:00,3,107500400,1066700000,10000\n",
        encoding="utf-8",
    )

    imported = QGroundControlLogReader().read(
        source,
        mission_id="mission-qgc",
        system_to_drone={1: "drone-01", 2: "drone-02", 3: "drone-03"},
    )

    assert len(imported.samples) == 3
    assert imported.system_ids == (1, 2, 3)
    assert imported.dropped_duplicate_count == 1
    assert imported.dropped_out_of_order_count == 1
    assert imported.samples[0].relative_altitude_m == 10.0
    assert imported.samples[0].position == GeoPoint(10.75, 106.67)


def test_telemetry_guard_rejects_duplicate_identity_and_filters_stream() -> None:
    with pytest.raises(IntegrationError, match="duplicate MAVLink"):
        TelemetryStreamGuard(
            (SystemMapping(1, "drone-01"), SystemMapping(1, "drone-02"))
        )
    guard = TelemetryStreamGuard(
        (
            SystemMapping(1, "drone-01"),
            SystemMapping(2, "drone-02"),
            SystemMapping(3, "drone-03"),
        )
    )
    first = TelemetryFrame(1, "drone-01", 0, NOW, GeoPoint(10.75, 106.67), 10)
    duplicate = TelemetryFrame(1, "drone-01", 1, NOW, GeoPoint(10.75, 106.67), 10)
    older = TelemetryFrame(
        1,
        "drone-01",
        2,
        NOW - timedelta(seconds=1),
        GeoPoint(10.7501, 106.67),
        10,
    )

    assert guard.accept("mission", first) is not None
    assert guard.accept("mission", duplicate) is None
    assert guard.accept("mission", older) is None
    assert guard.dropped_duplicate_count == 1
    assert guard.dropped_out_of_order_count == 1


class _FakeSystem:
    def __init__(self, attempt: int) -> None:
        self.attempt = attempt
        self.core = self
        self.telemetry = self
        self.mission_raw = self

    async def connect(self, *, system_address: str) -> None:
        assert system_address == "udp://:14540"

    async def connection_state(self):
        yield SimpleNamespace(is_connected=True)

    async def position(self):
        if self.attempt == 0:
            raise ConnectionError("simulated link loss")
        yield SimpleNamespace(
            latitude_deg=10.75,
            longitude_deg=106.67,
            relative_altitude_m=10.0,
        )

    async def download_mission(self):
        return [
            SimpleNamespace(
                seq=1,
                command=16,
                frame=3,
                x=107500000,
                y=1066700000,
                z=10.0,
            )
        ]


def test_mavsdk_read_only_adapter_reconnects_and_only_downloads_mission() -> None:
    attempts = 0

    def factory(_endpoint: MavsdkEndpoint) -> _FakeSystem:
        nonlocal attempts
        system = _FakeSystem(attempts)
        attempts += 1
        return system

    adapter = MavsdkReadOnlyAdapter(factory, reconnect_delay_seconds=0)
    endpoint = MavsdkEndpoint(1, "drone-01", "udp://:14540")

    async def collect() -> tuple[
        list[TelemetryFrame], tuple[MavsdkMissionItem, ...]
    ]:
        frames = [
            frame
            async for frame in adapter.stream_positions(endpoint, max_reconnects=1)
        ]
        mission = await adapter.download_mission(endpoint)
        return frames, mission

    frames, mission = asyncio.run(collect())
    assert len(frames) == 1
    assert frames[0].reconnect_count == 1
    assert mission[0].latitude == 10.75
    assert adapter.commands_enabled is False
    assert not hasattr(adapter, "arm")
    assert not hasattr(adapter, "upload_mission")


def test_mavsdk_dependency_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str):
        raise ImportError("not installed")

    monkeypatch.setattr(mavsdk_module.importlib, "import_module", missing)
    endpoint = MavsdkEndpoint(1, "drone-01", "udp://:14540")

    async def read_one() -> None:
        stream = MavsdkReadOnlyAdapter().stream_positions(endpoint, max_reconnects=0)
        await anext(stream)

    with pytest.raises(DependencyUnavailableError):
        asyncio.run(read_one())


def test_simulated_demo_has_three_ordered_streams() -> None:
    frames = simulate_three_drone_streams(samples_per_drone=4, started_at=NOW)
    assert len(frames) == 12
    assert {frame.system_id for frame in frames} == {1, 2, 3}
    assert {frame.drone_id for frame in frames} == {
        "drone-1",
        "drone-2",
        "drone-3",
    }
    assert [frame.sequence for frame in frames[:3]] == [0, 0, 0]
