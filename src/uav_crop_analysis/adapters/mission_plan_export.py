"""Atomic GreenEye bundle and QGroundControl plan export."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4

from uav_crop_analysis.errors import MissionPlanningError
from uav_crop_analysis.planning import DroneRoute, MissionPlanExport, PlannedMission
from uav_crop_analysis.planning.serialization import (
    plan_to_dict,
    route_contract_to_dict,
)


MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_DO_SET_CAM_TRIGG_DIST = 206
MAV_FRAME_MISSION = 2
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3
MAV_AUTOPILOT_ARDUPILOTMEGA = 3
MAV_TYPE_QUADROTOR = 2


class QGroundControlPlanWriter:
    """Write a reviewable stop-and-capture route in QGC Plan v1 format."""

    def to_dict(self, plan: PlannedMission, route: DroneRoute) -> dict[str, Any]:
        # QGC requires this field structurally, but take-off/home is configured
        # by the flight-control application.  Use the first survey point as a
        # neutral placeholder rather than asking the mapping operator for it.
        qgc_home = route.waypoints[0].position
        items: list[dict[str, Any]] = []
        jump_id = 1
        for waypoint in route.waypoints:
            items.append(
                _simple_item(
                    jump_id=jump_id,
                    command=MAV_CMD_NAV_WAYPOINT,
                    frame=MAV_FRAME_GLOBAL_RELATIVE_ALT,
                    altitude=waypoint.altitude_agl_m,
                    altitude_mode=1,
                    params=[
                        waypoint.hold_seconds,
                        0,
                        0,
                        None,
                        waypoint.position.latitude,
                        waypoint.position.longitude,
                        waypoint.altitude_agl_m,
                    ],
                )
            )
            jump_id += 1
            # MAV_CMD_DO_SET_CAM_TRIGG_DIST with param3=1 requests one image.
            items.append(
                _simple_item(
                    jump_id=jump_id,
                    command=MAV_CMD_DO_SET_CAM_TRIGG_DIST,
                    frame=MAV_FRAME_MISSION,
                    altitude=0,
                    altitude_mode=0,
                    params=[0, 0, 1, 0, None, None, None],
                )
            )
            jump_id += 1
        return {
            "fileType": "Plan",
            "geoFence": {"circles": [], "polygons": [], "version": 2},
            "groundStation": "QGroundControl",
            "mission": {
                "cruiseSpeed": 15,
                "firmwareType": MAV_AUTOPILOT_ARDUPILOTMEGA,
                "globalPlanAltitudeMode": 1,
                "hoverSpeed": plan.profile.flight_speed_mps,
                "items": items,
                "plannedHomePosition": [
                    qgc_home.latitude,
                    qgc_home.longitude,
                    0,
                ],
                "vehicleType": MAV_TYPE_QUADROTOR,
                "version": 2,
            },
            "rallyPoints": {"points": [], "version": 2},
            "version": 1,
        }

    def write(self, plan: PlannedMission, route: DroneRoute, destination: Path) -> None:
        destination.write_text(
            json.dumps(
                self.to_dict(plan, route),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


class GreenEyeMissionBundleExporter:
    def __init__(self, qgc_writer: QGroundControlPlanWriter | None = None) -> None:
        self._qgc_writer = qgc_writer or QGroundControlPlanWriter()

    def export(self, plan: PlannedMission, output_root: Path) -> MissionPlanExport:
        root = Path(output_root).expanduser().resolve()
        mission_root = root / "GreenEye mission"
        mission_root.mkdir(parents=True, exist_ok=True)
        name = _available_name(mission_root, _safe_name(plan.mission_id))
        final = mission_root / name
        staging = mission_root / f".{name}.{uuid4().hex}.tmp"
        routes_dir = staging / "routes"
        qgc_dir = staging / "qgroundcontrol"
        media_dir = staging / "media"
        routes_dir.mkdir(parents=True)
        qgc_dir.mkdir(parents=True)
        media_dir.mkdir(parents=True)
        try:
            mission_json = staging / "mission.json"
            _write_json(mission_json, plan_to_dict(plan))
            route_jsons: list[Path] = []
            qgc_plans: list[Path] = []
            for index, route in enumerate(plan.routes, start=1):
                stem = f"drone-{index:02d}"
                drone_media = media_dir / route.drone_id
                drone_media.mkdir()
                (drone_media / ".keep").touch()
                route_json = routes_dir / f"{stem}.plan.json"
                qgc_plan = qgc_dir / f"{stem}.plan"
                _write_json(route_json, route_contract_to_dict(plan, route))
                self._qgc_writer.write(plan, route, qgc_plan)
                route_jsons.append(route_json)
                qgc_plans.append(qgc_plan)

            (media_dir / "README.txt").write_text(
                "Đặt ảnh chụp của từng drone vào media/<drone-id>/.\n"
                "Ví dụ: media/drone-1/DJI_0001.JPG.\n"
                "Có thể đặt telemetry.csv hoặc flight-log.csv cùng thư mục drone.\n"
                "GreenEye sẽ tự nhận dữ liệu khi mở lại ứng dụng.\n",
                encoding="utf-8",
            )

            exported_files = [mission_json, *route_jsons, *qgc_plans]
            checksums = tuple(
                (
                    path.relative_to(staging).as_posix(),
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                for path in exported_files
            )
            checksums_file = staging / "checksums.sha256"
            checksums_file.write_text(
                "".join(f"{digest}  {relative}\n" for relative, digest in checksums),
                encoding="utf-8",
            )
            staging.replace(final)
        except Exception as exc:
            shutil.rmtree(staging, ignore_errors=True)
            if isinstance(exc, MissionPlanningError):
                raise
            raise MissionPlanningError(
                f"cannot export GreenEye mission bundle: {exc}",
                context={"mission_id": plan.mission_id},
            ) from exc

        return MissionPlanExport(
            directory=final,
            mission_json=final / mission_json.relative_to(staging),
            route_jsons=tuple(final / path.relative_to(staging) for path in route_jsons),
            qgroundcontrol_plans=tuple(
                final / path.relative_to(staging) for path in qgc_plans
            ),
            checksums_file=final / checksums_file.relative_to(staging),
            checksums=checksums,
        )


def _simple_item(
    *,
    jump_id: int,
    command: int,
    frame: int,
    altitude: float,
    altitude_mode: int,
    params: list[float | int | None],
) -> dict[str, Any]:
    return {
        "AMSLAltAboveTerrain": None,
        "Altitude": altitude,
        "AltitudeMode": altitude_mode,
        "autoContinue": True,
        "command": command,
        "doJumpId": jump_id,
        "frame": frame,
        "params": params,
        "type": "SimpleItem",
    }


def _write_json(destination: Path, value: dict[str, Any]) -> None:
    destination.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return normalized[:80] or hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _available_name(root: Path, preferred: str) -> str:
    if not (root / preferred).exists():
        return preferred
    index = 2
    while (root / f"{preferred}-{index}").exists():
        index += 1
    return f"{preferred}-{index}"
