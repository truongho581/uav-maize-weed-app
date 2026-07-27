"""Automation CLI over the public SDK and local REST API."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from uav_crop_analysis import UAVCropAnalysisError, __version__
from uav_crop_analysis.api import ApiApplication, LocalApiServer
from uav_crop_analysis.integrations import simulate_three_drone_streams
from uav_crop_analysis.sdk import (
    CreateMissionRequest,
    SubmitAnalysisRequest,
    UavCropAnalysis,
    to_json_value,
)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    parser = _parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "version":
        _write(output, {"application_version": __version__, "api_version": "v1"})
        return 0
    try:
        with UavCropAnalysis.open(args.database, registry_path=args.registry) as sdk:
            return _execute(args, sdk, output)
    except (UAVCropAnalysisError, OSError, ValueError, KeyError) as exc:
        _write(
            errors,
            {
                "error": {
                    "code": getattr(exc, "code", "cli_error"),
                    "message": str(exc),
                }
            },
        )
        return 2


def _execute(args: argparse.Namespace, sdk: UavCropAnalysis, output: TextIO) -> int:
    if args.command == "capabilities":
        _write(output, sdk.capabilities())
    elif args.command == "mission":
        if args.mission_command == "list":
            _write(output, sdk.list_missions())
        elif args.mission_command == "show":
            _write(output, sdk.get_mission(args.mission_id))
        elif args.mission_command == "create":
            drones = tuple(args.drone)
            if len(drones) != 3:
                raise ValueError("mission create requires exactly three --drone values")
            _write(
                output,
                sdk.create_mission(
                    CreateMissionRequest(
                        mission_id=args.mission_id,
                        name=args.name,
                        drone_ids=(drones[0], drones[1], drones[2]),
                        altitude_m=args.altitude,
                        forward_overlap=args.forward_overlap,
                        side_overlap=args.side_overlap,
                    )
                ),
            )
        elif args.mission_command == "import":
            _write(output, sdk.import_manifest(args.manifest))
    elif args.command == "job":
        if args.job_command == "list":
            _write(output, sdk.list_jobs(args.mission_id))
        elif args.job_command == "show":
            _write(output, sdk.get_job(args.job_id))
        elif args.job_command == "submit":
            _write(
                output,
                sdk.submit_analysis(
                    SubmitAnalysisRequest(
                        mission_id=args.mission_id,
                        model_id=args.model,
                        artifact_role=args.artifact,
                        weed_threshold=args.threshold,
                        auto_start=not args.queued,
                    )
                ),
            )
        elif args.job_command == "cancel":
            _write(output, sdk.cancel_job(args.job_id))
    elif args.command == "report":
        _write(output, sdk.export_report(args.mission_id, args.output))
    elif args.command == "qgc-plan":
        _write(output, sdk.inspect_qgc_plan(args.source))
    elif args.command == "qgc-log":
        mapping = {
            int(item.split("=", 1)[0]): item.split("=", 1)[1]
            for item in args.map_system
        }
        _write(
            output,
            sdk.read_qgc_log(
                args.source,
                mission_id=args.mission_id,
                system_to_drone=mapping,
            ),
        )
    elif args.command == "simulate":
        _write(output, simulate_three_drone_streams(samples_per_drone=args.samples))
    elif args.command == "serve":
        server = LocalApiServer(
            ApiApplication(sdk),
            host=args.host,
            port=args.port,
            allow_remote=args.allow_remote,
        )
        host, port = server.address
        _write(output, {"url": f"http://{host}:{port}/api/v1", "read_only_drone": True})
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uav-crop")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--registry", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version")
    subparsers.add_parser("capabilities")

    mission = subparsers.add_parser("mission").add_subparsers(
        dest="mission_command", required=True
    )
    mission.add_parser("list")
    show = mission.add_parser("show")
    show.add_argument("mission_id")
    create = mission.add_parser("create")
    create.add_argument("mission_id")
    create.add_argument("--name", required=True)
    create.add_argument("--drone", action="append", required=True, choices=None)
    create.add_argument("--altitude", type=float, default=10.0)
    create.add_argument("--forward-overlap", type=float, default=0.75)
    create.add_argument("--side-overlap", type=float, default=0.65)
    imported = mission.add_parser("import")
    imported.add_argument("manifest", type=Path)

    job = subparsers.add_parser("job").add_subparsers(dest="job_command", required=True)
    job_list = job.add_parser("list")
    job_list.add_argument("mission_id")
    job_show = job.add_parser("show")
    job_show.add_argument("job_id")
    submit = job.add_parser("submit")
    submit.add_argument("mission_id")
    submit.add_argument("--model", required=True)
    submit.add_argument("--artifact", default="best")
    submit.add_argument("--threshold", type=float, default=0.5)
    submit.add_argument("--queued", action="store_true")
    cancel = job.add_parser("cancel")
    cancel.add_argument("job_id")

    report = subparsers.add_parser("report")
    report.add_argument("mission_id")
    report.add_argument("--output", type=Path, required=True)
    qgc_plan = subparsers.add_parser("qgc-plan")
    qgc_plan.add_argument("source", type=Path)
    qgc_log = subparsers.add_parser("qgc-log")
    qgc_log.add_argument("mission_id")
    qgc_log.add_argument("source", type=Path)
    qgc_log.add_argument("--map-system", action="append", required=True)
    simulate = subparsers.add_parser("simulate")
    simulate.add_argument("--samples", type=int, default=4)
    serve = subparsers.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--allow-remote", action="store_true")
    return parser


def _write(stream: TextIO, value: Any) -> None:
    stream.write(json.dumps(to_json_value(value), ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
