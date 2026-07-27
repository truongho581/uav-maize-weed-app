"""Versioned REST dispatcher over the public SDK."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import unquote, urlsplit

from uav_crop_analysis import __version__
from uav_crop_analysis.adapters.report_export import mission_report_to_dict
from uav_crop_analysis.errors import (
    ApiRequestError,
    JobNotFoundError,
    MissionNotFoundError,
    UAVCropAnalysisError,
)
from uav_crop_analysis.integrations import simulate_three_drone_streams
from uav_crop_analysis.sdk import (
    API_VERSION,
    CreateMissionRequest,
    SubmitAnalysisRequest,
    UavCropAnalysis,
    to_json_value,
)


MAX_REQUEST_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status: int
    payload: dict[str, Any]


class ApiApplication:
    def __init__(self, sdk: UavCropAnalysis) -> None:
        self.sdk = sdk

    def handle(
        self,
        method: str,
        raw_path: str,
        body: bytes = b"",
    ) -> ApiResponse:
        try:
            return self._dispatch(method.upper(), raw_path, body)
        except MissionNotFoundError as exc:
            return _error(404, exc)
        except JobNotFoundError as exc:
            return _error(404, exc)
        except (ApiRequestError, ValueError, TypeError, KeyError) as exc:
            error = (
                exc
                if isinstance(exc, UAVCropAnalysisError)
                else ApiRequestError(str(exc) or "invalid API request")
            )
            return _error(400, error)
        except UAVCropAnalysisError as exc:
            return _error(409, exc)
        except Exception:
            return _error(500, ApiRequestError("internal API error"))

    def _dispatch(self, method: str, raw_path: str, body: bytes) -> ApiResponse:
        split = urlsplit(raw_path)
        parts = tuple(unquote(part) for part in split.path.strip("/").split("/") if part)
        if parts[:2] != ("api", API_VERSION):
            return _error(404, ApiRequestError("API route does not exist"))
        route = parts[2:]
        if method == "GET" and route == ("health",):
            return _ok(
                {
                    "status": "ok",
                    "database_schema_version": self.sdk.runtime.missions.schema_version,
                }
            )
        if method == "GET" and route == ("version",):
            return _ok(
                {
                    "application_version": __version__,
                    "sdk_schema_version": self.sdk.schema_version,
                    "api_version": API_VERSION,
                }
            )
        if method == "GET" and route == ("capabilities",):
            return _ok(to_json_value(self.sdk.capabilities()))
        if route == ("missions",):
            if method == "GET":
                return _ok(to_json_value(self.sdk.list_missions()))
            if method == "POST":
                payload = _json_object(body)
                drone_ids = _three_strings(payload.get("drone_ids"), "drone_ids")
                mission_result = self.sdk.create_mission(
                    CreateMissionRequest(
                        mission_id=str(payload["mission_id"]),
                        name=str(payload["name"]),
                        drone_ids=drone_ids,
                        altitude_m=float(payload.get("altitude_m", 10.0)),
                        gimbal_pitch_deg=float(payload.get("gimbal_pitch_deg", -90.0)),
                        forward_overlap=float(payload.get("forward_overlap", 0.75)),
                        side_overlap=float(payload.get("side_overlap", 0.65)),
                    )
                )
                return _ok(to_json_value(mission_result), status=201)
        if route == ("missions", "import") and method == "POST":
            payload = _json_object(body)
            return _ok(
                to_json_value(self.sdk.import_manifest(str(payload["manifest_path"]))),
                status=201,
            )
        if len(route) == 2 and route[0] == "missions" and method == "GET":
            return _ok(to_json_value(self.sdk.get_mission(route[1])))
        if len(route) == 3 and route[0] == "missions" and route[2] == "jobs":
            mission_id = route[1]
            if method == "GET":
                return _ok(to_json_value(self.sdk.list_jobs(mission_id)))
            if method == "POST":
                payload = _json_object(body)
                job_result = self.sdk.submit_analysis(
                    SubmitAnalysisRequest(
                        mission_id=mission_id,
                        model_id=str(payload["model_id"]),
                        artifact_role=str(payload.get("artifact_role", "best")),
                        device=str(payload.get("device", "cpu")),
                        tile_size=int(payload.get("tile_size", 640)),
                        overlap=int(payload.get("overlap", 64)),
                        weed_threshold=float(payload.get("weed_threshold", 0.5)),
                        selected_image_ids=tuple(
                            str(item) for item in payload.get("selected_image_ids", [])
                        ),
                        auto_start=bool(payload.get("auto_start", True)),
                    )
                )
                return _ok(to_json_value(job_result), status=202)
        if len(route) == 3 and route[0] == "missions" and route[2] == "results":
            if method == "GET":
                return _ok(to_json_value(self.sdk.list_results(route[1])))
        if len(route) == 3 and route[0] == "missions" and route[2] == "report":
            if method == "GET":
                return _ok(mission_report_to_dict(self.sdk.build_report(route[1])))
        if (
            len(route) == 4
            and route[0] == "missions"
            and route[2:] == ("report", "export")
            and method == "POST"
        ):
            payload = _json_object(body)
            return _ok(
                to_json_value(
                    self.sdk.export_report(route[1], str(payload["output_root"]))
                ),
                status=201,
            )
        if len(route) == 2 and route[0] == "jobs" and method == "GET":
            return _ok(to_json_value(self.sdk.get_job(route[1])))
        if (
            len(route) == 3
            and route[0] == "jobs"
            and route[2] == "cancel"
            and method == "POST"
        ):
            return _ok(to_json_value(self.sdk.cancel_job(route[1])))
        if route == ("integrations", "qgc", "plan") and method == "POST":
            payload = _json_object(body)
            plan = self.sdk.inspect_qgc_plan(str(payload["source_path"]))
            return _ok(to_json_value(plan))
        if route == ("integrations", "qgc", "log") and method == "POST":
            payload = _json_object(body)
            raw_mapping = payload.get("system_to_drone")
            if not isinstance(raw_mapping, dict):
                raise ApiRequestError("system_to_drone must be an object")
            imported = self.sdk.read_qgc_log(
                str(payload["source_path"]),
                mission_id=str(payload["mission_id"]),
                system_to_drone={int(key): str(value) for key, value in raw_mapping.items()},
            )
            return _ok(to_json_value(imported))
        if route == ("integrations", "simulation") and method == "GET":
            return _ok(to_json_value(simulate_three_drone_streams()))
        return _error(404, ApiRequestError("API route does not exist"))


def _json_object(body: bytes) -> dict[str, Any]:
    if len(body) > MAX_REQUEST_BYTES:
        raise ApiRequestError("request body exceeds 1 MiB")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiRequestError("request body must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ApiRequestError("request JSON must be an object")
    return value


def _three_strings(value: object, field: str) -> tuple[str, str, str]:
    if not isinstance(value, list) or len(value) != 3:
        raise ApiRequestError(f"{field} must contain exactly three values")
    values = tuple(str(item) for item in value)
    return values[0], values[1], values[2]


def _ok(data: Any, *, status: int = 200) -> ApiResponse:
    return ApiResponse(status, {"api_version": API_VERSION, "data": data})


def _error(status: int, error: UAVCropAnalysisError) -> ApiResponse:
    return ApiResponse(
        status,
        {
            "api_version": API_VERSION,
            "error": {
                "code": error.code,
                "message": error.message,
                "context": to_json_value(error.context),
            },
        },
    )
