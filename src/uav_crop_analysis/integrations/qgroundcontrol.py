"""QGroundControl plan and exported telemetry-log readers."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
from typing import Any, Mapping

from uav_crop_analysis.domain import DroneId, GeoPoint, MissionId, TelemetrySample
from uav_crop_analysis.errors import DependencyUnavailableError, ImportDataError
from uav_crop_analysis.integrations.models import (
    QgcPlan,
    QgcSurveyArea,
    QgcWaypoint,
    TelemetryLogImport,
)


_COLUMN_ALIASES = {
    "timestamp": ("timestamp", "time", "_timestamp"),
    "system_id": ("system_id", "sysid", "systemid"),
    "latitude": (
        "latitude",
        "lat",
        "vehicle_gps_position.lat",
        "global_position_int.lat",
    ),
    "longitude": (
        "longitude",
        "lon",
        "lng",
        "vehicle_gps_position.lon",
        "global_position_int.lon",
    ),
    "relative_altitude_m": (
        "relative_altitude_m",
        "relative_altitude",
        "relative_alt",
        "global_position_int.relative_alt",
    ),
}


class QGroundControlPlanReader:
    def read(self, source_path: str | Path) -> QgcPlan:
        path = Path(source_path).expanduser().resolve()
        try:
            payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("fileType") != "Plan":
                raise ImportDataError("QGroundControl fileType must be Plan")
            mission = _mapping(payload.get("mission"), "mission")
            home_values = _number_list(
                mission.get("plannedHomePosition"), 3, "plannedHomePosition"
            )
            home_latitude, home_longitude, home_altitude = home_values[:3]
            if (
                home_latitude is None
                or home_longitude is None
                or home_altitude is None
            ):
                raise ImportDataError("QGroundControl plannedHomePosition contains null")
            home = (
                home_latitude,
                home_longitude,
                home_altitude,
            )
            items = mission.get("items")
            if not isinstance(items, list) or not items:
                raise ImportDataError("QGroundControl mission requires at least one item")
            waypoints: list[QgcWaypoint] = []
            surveys: list[QgcSurveyArea] = []
            for sequence, raw_item in enumerate(items):
                item = _mapping(raw_item, f"mission.items[{sequence}]")
                item_type = str(item.get("type", ""))
                if item_type == "SimpleItem":
                    waypoint = _simple_item(sequence, item)
                    if waypoint is not None:
                        waypoints.append(waypoint)
                elif item_type == "ComplexItem" and str(
                    item.get("complexItemType", "")
                ).casefold() == "survey":
                    survey = _survey_item(sequence, item)
                    surveys.append(survey)
                    waypoints.extend(
                        QgcWaypoint(
                            sequence=sequence,
                            command=16,
                            frame=3,
                            latitude=point.latitude,
                            longitude=point.longitude,
                            altitude_m=_optional_float(
                                item.get("Altitude", item.get("altitude"))
                            )
                            or home[2],
                            auto_continue=True,
                            source_type="survey_visual_transect",
                        )
                        for point in survey.visual_transect_points
                    )
            return QgcPlan(
                source_path=path,
                plan_version=int(payload.get("version", 0)),
                mission_version=int(mission.get("version", 0)),
                ground_station=str(payload.get("groundStation", "")),
                firmware_type=int(mission.get("firmwareType", 0)),
                vehicle_type=int(mission.get("vehicleType", 0)),
                planned_home=GeoPoint(home[0], home[1]),
                planned_home_altitude_m=home[2],
                waypoints=tuple(waypoints),
                survey_areas=tuple(surveys),
            )
        except ImportDataError:
            raise
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ImportDataError(
                f"invalid QGroundControl plan: {path}",
                context={"source": str(path)},
            ) from exc


class QGroundControlLogReader:
    """Read QGC CSV exports directly and binary tlog through optional pymavlink."""

    def read(
        self,
        source_path: str | Path,
        *,
        mission_id: str,
        system_to_drone: Mapping[int, str],
    ) -> TelemetryLogImport:
        path = Path(source_path).expanduser().resolve()
        if path.suffix.casefold() == ".csv":
            rows = self._csv_rows(path)
        elif path.suffix.casefold() == ".tlog":
            rows = self._tlog_rows(path)
        else:
            raise ImportDataError("QGroundControl log must be .csv or .tlog")
        return _rows_to_telemetry(path, mission_id, system_to_drone, rows)

    @staticmethod
    def _csv_rows(path: Path) -> tuple[dict[str, object], ...]:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    raise ImportDataError("QGroundControl CSV has no header")
                names = {name.casefold(): name for name in reader.fieldnames}
                columns = {
                    key: next(
                        (names[alias] for alias in aliases if alias in names),
                        None,
                    )
                    for key, aliases in _COLUMN_ALIASES.items()
                }
                missing = [key for key, value in columns.items() if value is None]
                if missing:
                    raise ImportDataError(
                        f"QGroundControl CSV missing columns: {', '.join(missing)}"
                    )
                return tuple(
                    {
                        key: row[str(column)]
                        for key, column in columns.items()
                    }
                    for row in reader
                )
        except ImportDataError:
            raise
        except OSError as exc:
            raise ImportDataError(f"cannot read QGroundControl CSV: {path}") from exc

    @staticmethod
    def _tlog_rows(path: Path) -> tuple[dict[str, object], ...]:
        try:
            mavutil = importlib.import_module("pymavlink.mavutil")
        except ImportError as exc:
            raise DependencyUnavailableError(
                "pymavlink is required to read QGroundControl .tlog files",
                context={"extra": "drone"},
            ) from exc
        connection = mavutil.mavlink_connection(str(path))
        rows: list[dict[str, object]] = []
        while True:
            message = connection.recv_match(
                type=["GLOBAL_POSITION_INT", "GPS_RAW_INT"],
                blocking=False,
            )
            if message is None:
                break
            message_type = str(message.get_type())
            relative_alt = getattr(message, "relative_alt", None)
            if message_type != "GLOBAL_POSITION_INT" or relative_alt is None:
                continue
            rows.append(
                {
                    "timestamp": getattr(message, "_timestamp"),
                    "system_id": message.get_srcSystem(),
                    "latitude": getattr(message, "lat"),
                    "longitude": getattr(message, "lon"),
                    "relative_altitude_m": relative_alt,
                }
            )
        return tuple(rows)


def _simple_item(sequence: int, item: dict[str, Any]) -> QgcWaypoint | None:
    params = _number_list(item.get("params"), 7, f"item {sequence} params", allow_none=True)
    if params[4] is None or params[5] is None or params[6] is None:
        return None
    point = GeoPoint(float(params[4]), float(params[5]))
    return QgcWaypoint(
        sequence=sequence,
        command=int(item.get("command", 0)),
        frame=int(item.get("frame", 0)),
        latitude=point.latitude,
        longitude=point.longitude,
        altitude_m=float(params[6]),
        auto_continue=bool(item.get("autoContinue", True)),
        source_type="simple_item",
    )


def _survey_item(sequence: int, item: dict[str, Any]) -> QgcSurveyArea:
    style = _mapping(item.get("TransectStyleComplexItem"), "TransectStyleComplexItem")
    camera = style.get("CameraCalc")
    camera_map = camera if isinstance(camera, dict) else {}
    return QgcSurveyArea(
        sequence=sequence,
        polygon=_points(item.get("polygon"), "survey polygon"),
        visual_transect_points=_points(
            style.get("VisualTransectPoints", []),
            "survey visual transect points",
            allow_empty=True,
        ),
        hover_and_capture=bool(style.get("HoverAndCapture", False)),
        frontal_overlap_percent=_optional_float(camera_map.get("FrontalOverlap")),
        side_overlap_percent=_optional_float(camera_map.get("SideOverlap")),
    )


def _rows_to_telemetry(
    path: Path,
    mission_id: str,
    mapping: Mapping[int, str],
    rows: tuple[dict[str, object], ...],
) -> TelemetryLogImport:
    if not mapping:
        raise ImportDataError("system_to_drone mapping must not be empty")
    samples: list[TelemetrySample] = []
    last_by_system: dict[int, tuple[datetime, float, float, float]] = {}
    duplicate_count = 0
    out_of_order_count = 0
    observed: set[int] = set()
    for row_number, row in enumerate(rows, start=2):
        try:
            system_id = int(str(row["system_id"]))
            drone_id = mapping.get(system_id)
            if drone_id is None:
                raise ImportDataError(
                    f"unmapped MAVLink system_id {system_id} at row {row_number}"
                )
            recorded_at = _timestamp(row["timestamp"])
            latitude = _coordinate(row["latitude"], limit=90.0)
            longitude = _coordinate(row["longitude"], limit=180.0)
            altitude = _altitude(row["relative_altitude_m"])
            signature = (recorded_at, latitude, longitude, altitude)
            previous = last_by_system.get(system_id)
            if previous == signature:
                duplicate_count += 1
                continue
            if previous is not None and recorded_at <= previous[0]:
                out_of_order_count += 1
                continue
            last_by_system[system_id] = signature
            observed.add(system_id)
            samples.append(
                TelemetrySample(
                    mission_id=MissionId(mission_id),
                    drone_id=DroneId(drone_id),
                    recorded_at=recorded_at,
                    position=GeoPoint(latitude, longitude),
                    relative_altitude_m=altitude,
                )
            )
        except ImportDataError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ImportDataError(
                f"invalid QGroundControl telemetry row {row_number}",
                context={"source": str(path), "row_number": row_number},
            ) from exc
    return TelemetryLogImport(
        source_path=path,
        samples=tuple(samples),
        dropped_duplicate_count=duplicate_count,
        dropped_out_of_order_count=out_of_order_count,
        system_ids=tuple(sorted(observed)),
    )


def _timestamp(value: object) -> datetime:
    text = str(value).strip()
    try:
        numeric = float(text)
    except ValueError:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timestamp must include timezone")
        return parsed
    return datetime.fromtimestamp(numeric, tz=timezone.utc)


def _coordinate(value: object, *, limit: float) -> float:
    number = float(str(value))
    if abs(number) > limit:
        number /= 10_000_000.0
    if abs(number) > limit:
        raise ValueError("coordinate outside range")
    return number


def _altitude(value: object) -> float:
    number = float(str(value))
    if number > 1000:
        number /= 1000.0
    if number < 0:
        raise ValueError("relative altitude must be non-negative")
    return number


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ImportDataError(f"QGroundControl {field} must be an object")
    return value


def _number_list(
    value: object,
    minimum: int,
    field: str,
    *,
    allow_none: bool = False,
) -> list[float | None]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ImportDataError(f"QGroundControl {field} is invalid")
    result: list[float | None] = []
    for item in value:
        if item is None and allow_none:
            result.append(None)
        else:
            result.append(float(item))
    return result


def _points(value: object, field: str, *, allow_empty: bool = False) -> tuple[GeoPoint, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ImportDataError(f"QGroundControl {field} is invalid")
    return tuple(
        GeoPoint(*_point_pair(point, field))
        for point in value
    )


def _point_pair(value: object, field: str) -> tuple[float, float]:
    numbers = _number_list(value, 2, field)
    if numbers[0] is None or numbers[1] is None:
        raise ImportDataError(f"QGroundControl {field} contains null coordinate")
    return float(numbers[0]), float(numbers[1])


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
