"""SQLite implementation of mission and imported-data repository ports."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from uav_crop_analysis.domain import (
    CameraProfile,
    CaptureMode,
    DroneAssignment,
    DroneId,
    FlightProfile,
    GeoPoint,
    ImageAsset,
    MissionId,
    SurveyMission,
    TelemetrySample,
)
from uav_crop_analysis.errors import (
    MigrationError,
    MissionAlreadyExistsError,
    PersistenceError,
)


LATEST_SCHEMA_VERSION = 4

MIGRATION_V1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE missions (
    mission_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    altitude_m REAL NOT NULL,
    gimbal_pitch_deg REAL NOT NULL,
    forward_overlap REAL NOT NULL,
    side_overlap REAL NOT NULL,
    capture_mode TEXT NOT NULL
);

CREATE TABLE drone_assignments (
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    drone_id TEXT NOT NULL,
    lane_index INTEGER NOT NULL,
    PRIMARY KEY (mission_id, drone_id),
    UNIQUE (mission_id, lane_index)
);

CREATE TABLE camera_profiles (
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL,
    name TEXT NOT NULL,
    make TEXT,
    model TEXT,
    image_width_px INTEGER,
    image_height_px INTEGER,
    focal_length_mm REAL,
    horizontal_fov_deg REAL,
    vertical_fov_deg REAL,
    distortion_coefficients_json TEXT NOT NULL,
    PRIMARY KEY (mission_id, profile_id)
);

CREATE TABLE image_assets (
    asset_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    drone_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    captured_at TEXT NOT NULL,
    width_px INTEGER NOT NULL,
    height_px INTEGER NOT NULL,
    sequence_index INTEGER NOT NULL,
    latitude REAL,
    longitude REAL,
    absolute_altitude_m REAL,
    relative_altitude_m REAL,
    telemetry_offset_ms INTEGER,
    camera_profile_id TEXT,
    FOREIGN KEY (mission_id, drone_id)
        REFERENCES drone_assignments(mission_id, drone_id) ON DELETE CASCADE,
    FOREIGN KEY (mission_id, camera_profile_id)
        REFERENCES camera_profiles(mission_id, profile_id),
    UNIQUE (mission_id, sha256),
    UNIQUE (mission_id, drone_id, sequence_index)
);

CREATE TABLE telemetry_samples (
    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL,
    drone_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    relative_altitude_m REAL NOT NULL,
    FOREIGN KEY (mission_id, drone_id)
        REFERENCES drone_assignments(mission_id, drone_id) ON DELETE CASCADE,
    UNIQUE (mission_id, drone_id, recorded_at)
);

CREATE INDEX idx_image_assets_capture
    ON image_assets(mission_id, drone_id, captured_at);
CREATE INDEX idx_telemetry_capture
    ON telemetry_samples(mission_id, drone_id, recorded_at);
"""

MIGRATION_V2 = """
CREATE TABLE analysis_jobs (
    job_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    config_json TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    progress REAL NOT NULL,
    attempt INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error_json TEXT,
    result_json TEXT
);

CREATE TABLE analysis_job_events (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    progress REAL NOT NULL,
    occurred_at TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT
);

CREATE INDEX idx_analysis_jobs_status
    ON analysis_jobs(status, updated_at);
CREATE INDEX idx_analysis_events_job
    ON analysis_job_events(job_id, sequence_id);
"""

MIGRATION_V3 = """
CREATE TABLE spatial_products (
    product_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    accuracy TEXT NOT NULL,
    path TEXT NOT NULL,
    preview_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    raster_json TEXT,
    source_product_id TEXT,
    source_job_id TEXT,
    provenance_json TEXT NOT NULL
);

CREATE INDEX idx_spatial_products_mission
    ON spatial_products(mission_id, created_at);
"""

MIGRATION_V4 = """
CREATE TABLE camera_catalog (
    profile_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    make TEXT,
    model TEXT,
    image_width_px INTEGER,
    image_height_px INTEGER,
    focal_length_mm REAL,
    horizontal_fov_deg REAL,
    vertical_fov_deg REAL,
    distortion_coefficients_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class SQLiteMissionRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._apply_migrations()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    @property
    def schema_version(self) -> int:
        with self._connection() as connection:
            row = connection.execute("PRAGMA user_version").fetchone()
            return int(row[0])

    def _apply_migrations(self) -> None:
        with self._connection() as connection:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current > LATEST_SCHEMA_VERSION:
                raise MigrationError(
                    f"database schema {current} is newer than supported {LATEST_SCHEMA_VERSION}",
                    context={"current": current, "supported": LATEST_SCHEMA_VERSION},
                )
            if current < 1:
                applied_at = datetime.now().astimezone().isoformat()
                escaped_applied_at = applied_at.replace("'", "''")
                script = (
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_V1
                    + "\nINSERT INTO schema_migrations(version, applied_at) "
                    + f"VALUES (1, '{escaped_applied_at}');\n"
                    + "PRAGMA user_version = 1;\nCOMMIT;"
                )
                try:
                    connection.executescript(script)
                except sqlite3.Error as exc:
                    raise MigrationError("failed to apply SQLite migration v1") from exc
            if current < 2:
                applied_at = datetime.now().astimezone().isoformat()
                escaped_applied_at = applied_at.replace("'", "''")
                script = (
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_V2
                    + "\nINSERT INTO schema_migrations(version, applied_at) "
                    + f"VALUES (2, '{escaped_applied_at}');\n"
                    + "PRAGMA user_version = 2;\nCOMMIT;"
                )
                try:
                    connection.executescript(script)
                except sqlite3.Error as exc:
                    raise MigrationError("failed to apply SQLite migration v2") from exc
            if current < 3:
                applied_at = datetime.now().astimezone().isoformat()
                escaped_applied_at = applied_at.replace("'", "''")
                script = (
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_V3
                    + "\nINSERT INTO schema_migrations(version, applied_at) "
                    + f"VALUES (3, '{escaped_applied_at}');\n"
                    + "PRAGMA user_version = 3;\nCOMMIT;"
                )
                try:
                    connection.executescript(script)
                except sqlite3.Error as exc:
                    raise MigrationError("failed to apply SQLite migration v3") from exc
            if current < 4:
                applied_at = datetime.now().astimezone().isoformat()
                escaped_applied_at = applied_at.replace("'", "''")
                script = (
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_V4
                    + "\nINSERT INTO camera_catalog "
                    "SELECT profile_id, name, make, model, image_width_px, image_height_px, "
                    "focal_length_mm, horizontal_fov_deg, vertical_fov_deg, "
                    "distortion_coefficients_json, '"
                    + escaped_applied_at
                    + "' FROM camera_profiles;\n"
                    + "INSERT INTO schema_migrations(version, applied_at) "
                    + f"VALUES (4, '{escaped_applied_at}');\n"
                    + "PRAGMA user_version = 4;\nCOMMIT;"
                )
                try:
                    connection.executescript(script)
                except sqlite3.Error as exc:
                    raise MigrationError("failed to apply SQLite migration v4") from exc

    def add(self, mission: SurveyMission) -> None:
        try:
            with self._connection() as connection, connection:
                self._insert_mission(connection, mission, replace=False)
                self._insert_assignments(connection, mission)
        except sqlite3.IntegrityError as exc:
            raise MissionAlreadyExistsError(
                f"mission already exists: {mission.mission_id}",
                context={"mission_id": mission.mission_id.value},
            ) from exc
        except sqlite3.Error as exc:
            raise PersistenceError("failed to save mission") from exc

    def get(self, mission_id: MissionId) -> SurveyMission | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT * FROM missions WHERE mission_id = ?",
                    (mission_id.value,),
                ).fetchone()
                if row is None:
                    return None
                assignment_rows = connection.execute(
                    """
                    SELECT drone_id, lane_index
                    FROM drone_assignments
                    WHERE mission_id = ?
                    ORDER BY lane_index
                    """,
                    (mission_id.value,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError("failed to load mission") from exc

        return self._mission_from_rows(row, assignment_rows)

    def list_missions(self) -> tuple[SurveyMission, ...]:
        try:
            with self._connection() as connection:
                mission_rows = connection.execute(
                    "SELECT * FROM missions ORDER BY created_at DESC, mission_id DESC"
                ).fetchall()
                assignment_rows = connection.execute(
                    """
                    SELECT mission_id, drone_id, lane_index
                    FROM drone_assignments
                    ORDER BY mission_id, lane_index
                    """
                ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError("failed to list missions") from exc

        assignments_by_mission: dict[str, list[sqlite3.Row]] = {}
        for assignment in assignment_rows:
            assignments_by_mission.setdefault(assignment["mission_id"], []).append(assignment)
        return tuple(
            self._mission_from_rows(
                row,
                assignments_by_mission.get(row["mission_id"], []),
            )
            for row in mission_rows
        )

    def save_bundle(
        self,
        mission: SurveyMission,
        camera_profiles: tuple[CameraProfile, ...],
        images: tuple[ImageAsset, ...],
        telemetry_samples: tuple[TelemetrySample, ...],
    ) -> None:
        try:
            with self._connection() as connection, connection:
                mission_value = mission.mission_id.value
                for table in (
                    "image_assets",
                    "telemetry_samples",
                    "camera_profiles",
                    "drone_assignments",
                ):
                    connection.execute(
                        f"DELETE FROM {table} WHERE mission_id = ?",  # noqa: S608
                        (mission_value,),
                    )
                self._insert_mission(connection, mission, replace=True)
                self._insert_assignments(connection, mission)
                self._insert_camera_profiles(connection, mission.mission_id, camera_profiles)
                self._upsert_camera_catalog(connection, camera_profiles)
                self._insert_telemetry(connection, telemetry_samples)
                self._insert_images(connection, images)
        except sqlite3.Error as exc:
            raise PersistenceError(
                "failed to save mission import bundle",
                context={"mission_id": mission.mission_id.value},
            ) from exc

    def list_camera_profiles(self, mission_id: MissionId) -> tuple[CameraProfile, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM camera_profiles WHERE mission_id = ? ORDER BY profile_id",
                (mission_id.value,),
            ).fetchall()
        return tuple(
            CameraProfile(
                profile_id=row["profile_id"],
                name=row["name"],
                make=row["make"],
                model=row["model"],
                image_width_px=row["image_width_px"],
                image_height_px=row["image_height_px"],
                focal_length_mm=row["focal_length_mm"],
                horizontal_fov_deg=row["horizontal_fov_deg"],
                vertical_fov_deg=row["vertical_fov_deg"],
                distortion_coefficients=tuple(
                    json.loads(row["distortion_coefficients_json"])
                ),
            )
            for row in rows
        )

    def list_saved_camera_profiles(self) -> tuple[CameraProfile, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM camera_catalog ORDER BY name, profile_id"
            ).fetchall()
        return tuple(self._camera_from_row(row) for row in rows)

    def save_camera_profile(
        self,
        mission_id: MissionId,
        profile: CameraProfile,
        drone_ids: tuple[DroneId, ...],
    ) -> None:
        selected = tuple(drone.value for drone in drone_ids)
        if not selected:
            raise PersistenceError("camera profile must be assigned to at least one drone")
        try:
            with self._connection() as connection, connection:
                known = {
                    row[0]
                    for row in connection.execute(
                        "SELECT drone_id FROM drone_assignments WHERE mission_id = ?",
                        (mission_id.value,),
                    )
                }
                if not set(selected) <= known:
                    raise PersistenceError("camera profile references an unknown mission drone")
                connection.execute(
                    """
                    INSERT INTO camera_profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(mission_id, profile_id) DO UPDATE SET
                        name = excluded.name, make = excluded.make, model = excluded.model,
                        image_width_px = excluded.image_width_px,
                        image_height_px = excluded.image_height_px,
                        focal_length_mm = excluded.focal_length_mm,
                        horizontal_fov_deg = excluded.horizontal_fov_deg,
                        vertical_fov_deg = excluded.vertical_fov_deg,
                        distortion_coefficients_json = excluded.distortion_coefficients_json
                    """,
                    (
                        mission_id.value, profile.profile_id, profile.name, profile.make,
                        profile.model, profile.image_width_px, profile.image_height_px,
                        profile.focal_length_mm, profile.horizontal_fov_deg,
                        profile.vertical_fov_deg, json.dumps(profile.distortion_coefficients),
                    ),
                )
                self._upsert_camera_catalog(connection, (profile,))
                placeholders = ",".join("?" for _ in selected)
                connection.execute(
                    f"UPDATE image_assets SET camera_profile_id = ? "
                    f"WHERE mission_id = ? AND drone_id IN ({placeholders})",  # noqa: S608
                    (profile.profile_id, mission_id.value, *selected),
                )
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceError(
                "failed to save camera profile", context={"mission_id": mission_id.value}
            ) from exc

    def list_image_assets(self, mission_id: MissionId) -> tuple[ImageAsset, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM image_assets
                WHERE mission_id = ?
                ORDER BY drone_id, sequence_index
                """,
                (mission_id.value,),
            ).fetchall()
        return tuple(self._image_from_row(row) for row in rows)

    def list_telemetry_samples(self, mission_id: MissionId) -> tuple[TelemetrySample, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM telemetry_samples
                WHERE mission_id = ?
                ORDER BY drone_id, recorded_at
                """,
                (mission_id.value,),
            ).fetchall()
        return tuple(
            TelemetrySample(
                mission_id=MissionId(row["mission_id"]),
                drone_id=DroneId(row["drone_id"]),
                recorded_at=datetime.fromisoformat(row["recorded_at"]),
                position=GeoPoint(row["latitude"], row["longitude"]),
                relative_altitude_m=row["relative_altitude_m"],
            )
            for row in rows
        )

    @staticmethod
    def _insert_mission(
        connection: sqlite3.Connection,
        mission: SurveyMission,
        *,
        replace: bool,
    ) -> None:
        values = (
            mission.mission_id.value,
            mission.name,
            mission.created_at.isoformat(),
            mission.flight_profile.altitude_m,
            mission.flight_profile.gimbal_pitch_deg,
            mission.flight_profile.forward_overlap,
            mission.flight_profile.side_overlap,
            mission.flight_profile.capture_mode.value,
        )
        if replace:
            connection.execute(
                """
                INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mission_id) DO UPDATE SET
                    name = excluded.name,
                    created_at = excluded.created_at,
                    altitude_m = excluded.altitude_m,
                    gimbal_pitch_deg = excluded.gimbal_pitch_deg,
                    forward_overlap = excluded.forward_overlap,
                    side_overlap = excluded.side_overlap,
                    capture_mode = excluded.capture_mode
                """,
                values,
            )
        else:
            connection.execute("INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", values)

    @staticmethod
    def _insert_assignments(connection: sqlite3.Connection, mission: SurveyMission) -> None:
        connection.executemany(
            "INSERT INTO drone_assignments VALUES (?, ?, ?)",
            (
                (mission.mission_id.value, item.drone_id.value, item.lane_index)
                for item in mission.assignments
            ),
        )

    @staticmethod
    def _insert_camera_profiles(
        connection: sqlite3.Connection,
        mission_id: MissionId,
        profiles: tuple[CameraProfile, ...],
    ) -> None:
        connection.executemany(
            "INSERT INTO camera_profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    mission_id.value,
                    item.profile_id,
                    item.name,
                    item.make,
                    item.model,
                    item.image_width_px,
                    item.image_height_px,
                    item.focal_length_mm,
                    item.horizontal_fov_deg,
                    item.vertical_fov_deg,
                    json.dumps(item.distortion_coefficients),
                )
                for item in profiles
            ),
        )

    @staticmethod
    def _upsert_camera_catalog(
        connection: sqlite3.Connection, profiles: tuple[CameraProfile, ...]
    ) -> None:
        now = datetime.now().astimezone().isoformat()
        connection.executemany(
            """
            INSERT INTO camera_catalog VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                name = excluded.name, make = excluded.make, model = excluded.model,
                image_width_px = excluded.image_width_px, image_height_px = excluded.image_height_px,
                focal_length_mm = excluded.focal_length_mm,
                horizontal_fov_deg = excluded.horizontal_fov_deg,
                vertical_fov_deg = excluded.vertical_fov_deg,
                distortion_coefficients_json = excluded.distortion_coefficients_json,
                updated_at = excluded.updated_at
            """,
            (
                (
                    item.profile_id, item.name, item.make, item.model,
                    item.image_width_px, item.image_height_px, item.focal_length_mm,
                    item.horizontal_fov_deg, item.vertical_fov_deg,
                    json.dumps(item.distortion_coefficients), now,
                )
                for item in profiles
            ),
        )

    @staticmethod
    def _camera_from_row(row: sqlite3.Row) -> CameraProfile:
        return CameraProfile(
            profile_id=row["profile_id"], name=row["name"], make=row["make"],
            model=row["model"], image_width_px=row["image_width_px"],
            image_height_px=row["image_height_px"], focal_length_mm=row["focal_length_mm"],
            horizontal_fov_deg=row["horizontal_fov_deg"],
            vertical_fov_deg=row["vertical_fov_deg"],
            distortion_coefficients=tuple(json.loads(row["distortion_coefficients_json"])),
        )

    @staticmethod
    def _insert_telemetry(
        connection: sqlite3.Connection,
        samples: tuple[TelemetrySample, ...],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO telemetry_samples(
                mission_id, drone_id, recorded_at, latitude, longitude,
                relative_altitude_m
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    item.mission_id.value,
                    item.drone_id.value,
                    item.recorded_at.isoformat(),
                    item.position.latitude,
                    item.position.longitude,
                    item.relative_altitude_m,
                )
                for item in samples
            ),
        )

    @staticmethod
    def _insert_images(
        connection: sqlite3.Connection,
        images: tuple[ImageAsset, ...],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO image_assets VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                (
                    item.asset_id,
                    item.mission_id.value,
                    item.drone_id.value,
                    str(item.source_path),
                    item.sha256,
                    item.size_bytes,
                    item.captured_at.isoformat(),
                    item.width_px,
                    item.height_px,
                    item.sequence_index,
                    item.position.latitude if item.position else None,
                    item.position.longitude if item.position else None,
                    item.absolute_altitude_m,
                    item.relative_altitude_m,
                    item.telemetry_offset_ms,
                    item.camera_profile_id,
                )
                for item in images
            ),
        )

    @staticmethod
    def _image_from_row(row: sqlite3.Row) -> ImageAsset:
        position = None
        if row["latitude"] is not None and row["longitude"] is not None:
            position = GeoPoint(row["latitude"], row["longitude"])
        return ImageAsset(
            asset_id=row["asset_id"],
            mission_id=MissionId(row["mission_id"]),
            drone_id=DroneId(row["drone_id"]),
            source_path=Path(row["source_path"]),
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            captured_at=datetime.fromisoformat(row["captured_at"]),
            width_px=row["width_px"],
            height_px=row["height_px"],
            sequence_index=row["sequence_index"],
            position=position,
            absolute_altitude_m=row["absolute_altitude_m"],
            relative_altitude_m=row["relative_altitude_m"],
            telemetry_offset_ms=row["telemetry_offset_ms"],
            camera_profile_id=row["camera_profile_id"],
        )

    @staticmethod
    def _mission_from_rows(
        row: sqlite3.Row,
        assignment_rows: list[sqlite3.Row] | tuple[sqlite3.Row, ...],
    ) -> SurveyMission:
        assignments = tuple(
            DroneAssignment(DroneId(item["drone_id"]), item["lane_index"])
            for item in assignment_rows
        )
        return SurveyMission(
            mission_id=MissionId(row["mission_id"]),
            name=row["name"],
            assignments=assignments,
            flight_profile=FlightProfile(
                altitude_m=row["altitude_m"],
                gimbal_pitch_deg=row["gimbal_pitch_deg"],
                forward_overlap=row["forward_overlap"],
                side_overlap=row["side_overlap"],
                capture_mode=CaptureMode(row["capture_mode"]),
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
