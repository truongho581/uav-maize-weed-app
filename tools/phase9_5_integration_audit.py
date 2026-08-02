"""Generate and verify deterministic GreenEye plans for one to three drones."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pyproj import Transformer

from uav_crop_analysis.adapters import GreenEyeMissionBundleExporter
from uav_crop_analysis.domain import CameraProfile, GeoPoint
from uav_crop_analysis.integrations import QGroundControlPlanReader
from uav_crop_analysis.planning import (
    GridMissionPlanner,
    MissionPlanningProfile,
    MissionPlanningRequest,
    SurveyArea,
)
from uav_crop_analysis.planning.serialization import plan_to_dict
from uav_crop_analysis.sdk import UavCropAnalysis


PROJECTED_CRS = "EPSG:32648"
RECTANGLE = (
    (500_000.0, 1_200_000.0),
    (500_080.0, 1_200_000.0),
    (500_080.0, 1_200_050.0),
    (500_000.0, 1_200_050.0),
)


def build_request(drone_count: int) -> MissionPlanningRequest:
    transformer = Transformer.from_crs(PROJECTED_CRS, "EPSG:4326", always_xy=True)
    points = tuple(
        GeoPoint(latitude, longitude)
        for longitude, latitude in (
            transformer.transform(x_value, y_value) for x_value, y_value in RECTANGLE
        )
    )
    return MissionPlanningRequest(
        mission_id=f"phase9-5-golden-{drone_count}",
        survey_area=SurveyArea(points),
        profile=MissionPlanningProfile(
            drone_count=drone_count,
            sweep_heading_deg=90.0,
        ),
        camera=CameraProfile(
            profile_id="camera-phase9-5-golden",
            name="Camera RGB golden",
            image_width_px=4000,
            image_height_px=3000,
            horizontal_fov_deg=82.0,
            vertical_fov_deg=62.0,
        ),
        drone_ids=tuple(f"drone-{index + 1}" for index in range(drone_count)),
        homes=(points[0],) * drone_count,
    )


def run_audit(output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=False)
    planner = GridMissionPlanner()
    exporter = GreenEyeMissionBundleExporter()
    scenarios: list[dict[str, Any]] = []
    for drone_count in (1, 2, 3):
        request = build_request(drone_count)
        plan = planner.plan(request)
        repeated = planner.plan(request)
        if plan != repeated:
            raise RuntimeError(f"planner is not deterministic for {drone_count} drone")
        if len(plan.routes) != drone_count or not plan.export_ready:
            raise RuntimeError(f"plan is not export-ready for {drone_count} drone")
        if plan.coverage_ratio < 0.999:
            raise RuntimeError(f"coverage is below contract for {drone_count} drone")
        lanes = tuple(lane for route in plan.routes for lane in route.lane_indices)
        if lanes != tuple(range(len(lanes))):
            raise RuntimeError(f"routes are not contiguous for {drone_count} drone")

        exported = exporter.export(plan, output_root)
        for relative, expected in exported.checksums:
            source = exported.directory / relative
            actual = hashlib.sha256(source.read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError(f"checksum mismatch: {relative}")

        qgc_summaries = []
        for route, source in zip(
            plan.routes, exported.qgroundcontrol_plans, strict=True
        ):
            inspected = QGroundControlPlanReader().read(source)
            raw = json.loads(source.read_text(encoding="utf-8"))
            commands = sorted({int(item["command"]) for item in raw["mission"]["items"]})
            if len(inspected.waypoints) != len(route.waypoints) or commands != [16, 206]:
                raise RuntimeError(f"QGC route contract mismatch: {source.name}")
            qgc_summaries.append(
                {
                    "file": source.name,
                    "waypoint_count": len(inspected.waypoints),
                    "commands": commands,
                }
            )

        payload = json.dumps(
            plan_to_dict(plan),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        scenarios.append(
            {
                "drone_count": drone_count,
                "area_m2": round(plan.area_m2, 3),
                "coverage_ratio": round(plan.coverage_ratio, 6),
                "heading_deg": round(plan.effective_sweep_heading_deg, 3),
                "capture_count": plan.capture_count,
                "lane_spacing_m": round(plan.camera_footprint.lane_spacing_m, 6),
                "capture_spacing_m": round(
                    plan.camera_footprint.capture_spacing_m, 6
                ),
                "plan_sha256": hashlib.sha256(payload).hexdigest(),
                "routes": [
                    {
                        "drone_id": route.drone_id,
                        "lanes": list(route.lane_indices),
                        "capture_count": len(route.waypoints),
                        "distance_m": round(route.estimated_distance_m, 3),
                        "duration_s": round(route.estimated_duration_seconds, 3),
                    }
                    for route in plan.routes
                ],
                "qgroundcontrol": qgc_summaries,
                "checksum_count": len(exported.checksums),
            }
        )

    forbidden = ("arm", "takeoff", "upload_mission", "start_mission")
    exposed = [name for name in forbidden if hasattr(UavCropAnalysis, name)]
    if exposed:
        raise RuntimeError(f"forbidden drone commands are exposed: {', '.join(exposed)}")
    summary: dict[str, Any] = {
        "audit_version": 1,
        "scenarios": scenarios,
        "safety": {
            "drone_commands_enabled": False,
            "forbidden_sdk_methods": list(forbidden),
            "exposed_forbidden_methods": exposed,
        },
    }
    (output_root / "audit-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def golden_projection(summary: dict[str, Any]) -> dict[str, Any]:
    scenarios = []
    for source in summary["scenarios"]:
        scenario = dict(source)
        scenario.pop("plan_sha256", None)
        scenarios.append(scenario)
    return {
        "audit_version": summary["audit_version"],
        "scenarios": scenarios,
        "safety": summary["safety"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run_audit(args.output.resolve())
    print(json.dumps(golden_projection(summary), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
