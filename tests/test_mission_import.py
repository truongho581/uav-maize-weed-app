from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil

from PIL import Image

from uav_crop_analysis.adapters import (
    CsvTelemetryReader,
    PillowExifReader,
    SQLiteMissionRepository,
)
from uav_crop_analysis.application import (
    DroneImportSource,
    ImportMissionData,
    MissionImportRequest,
)
from uav_crop_analysis.domain import CameraProfile, DroneId, MissionId, SurveyMission


CAPTURED_AT = datetime(2026, 7, 27, 10, 0, 0, tzinfo=timezone.utc)


def _mission() -> SurveyMission:
    return SurveyMission.create(
        mission_id="mission-import",
        name="Three drone import",
        drone_ids=("drone-01", "drone-02", "drone-03"),
        created_at=datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc),
    )


def _write_image(path: Path, captured_at: datetime, color: tuple[int, int, int]) -> None:
    exif = Image.Exif()
    exif[36867] = captured_at.strftime("%Y:%m:%d %H:%M:%S")
    exif[36881] = "+00:00"
    Image.new("RGB", (64, 64), color).save(path, exif=exif)


def _write_telemetry(
    path: Path,
    captured_at: datetime,
    *,
    latitude: float = 10.75,
    altitude_m: float = 10.0,
) -> None:
    path.write_text(
        "timestamp,latitude,longitude,relative_altitude_m\n"
        f"{captured_at.isoformat()},{latitude},106.67,{altitude_m}\n",
        encoding="utf-8",
    )


def _sources(
    root: Path,
    *,
    telemetry_offset: timedelta = timedelta(0),
    invalid_gps_drone: str | None = None,
) -> tuple[DroneImportSource, DroneImportSource, DroneImportSource]:
    camera = CameraProfile(
        profile_id="generic-rgb",
        name="Generic RGB",
        image_width_px=64,
        image_height_px=64,
    )
    sources = []
    for index, drone_id in enumerate(("drone-01", "drone-02", "drone-03"), start=1):
        image_dir = root / drone_id / "images"
        image_dir.mkdir(parents=True)
        _write_image(
            image_dir / "capture-001.jpg",
            CAPTURED_AT,
            (20 * index, 80 + index, 30),
        )
        telemetry_file = root / drone_id / "flight.csv"
        _write_telemetry(
            telemetry_file,
            CAPTURED_AT + telemetry_offset,
            latitude=999 if drone_id == invalid_gps_drone else 10.75 + index / 1000,
        )
        sources.append(
            DroneImportSource(
                drone_id=DroneId(drone_id),
                image_dir=image_dir,
                telemetry_file=telemetry_file,
                camera_profile=camera,
            )
        )
    return sources[0], sources[1], sources[2]


def _service(tmp_path: Path) -> tuple[ImportMissionData, SQLiteMissionRepository]:
    repository = SQLiteMissionRepository(tmp_path / "missions.db")
    return (
        ImportMissionData(repository, PillowExifReader(), CsvTelemetryReader()),
        repository,
    )


def _codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def test_complete_three_drone_import_persists_and_reopens(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    request = MissionImportRequest(mission=_mission(), sources=_sources(tmp_path / "input"))

    report = service.execute(request)
    reopened = SQLiteMissionRepository(repository.database_path)

    assert report.persisted
    assert not report.has_errors
    assert report.image_counts_by_drone == {
        "drone-01": 1,
        "drone-02": 1,
        "drone-03": 1,
    }
    assert report.metadata_coverage.gps_ratio == 1.0
    assert report.metadata_coverage.altitude_ratio == 1.0
    assert reopened.get(MissionId("mission-import")) == request.mission
    assert len(reopened.list_image_assets(request.mission.mission_id)) == 3
    assert len(reopened.list_telemetry_samples(request.mission.mission_id)) == 3
    assert len(reopened.list_camera_profiles(request.mission.mission_id)) == 1


def test_import_reports_missing_third_drone(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    sources = _sources(tmp_path / "input")

    report = service.execute(MissionImportRequest(mission=_mission(), sources=sources[:2]))

    assert not report.persisted
    assert "missing_drone_source" in _codes(report)
    assert repository.get(MissionId("mission-import")) is None


def test_import_reports_invalid_gps(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    request = MissionImportRequest(
        mission=_mission(),
        sources=_sources(tmp_path / "input", invalid_gps_drone="drone-02"),
    )

    report = service.execute(request)

    assert not report.persisted
    assert "invalid_telemetry_row" in _codes(report)
    assert "missing_gps" in _codes(report)


def test_import_reports_timestamp_skew(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    request = MissionImportRequest(
        mission=_mission(),
        sources=_sources(tmp_path / "input", telemetry_offset=timedelta(seconds=10)),
        max_telemetry_skew_seconds=2.0,
    )

    report = service.execute(request)

    assert not report.persisted
    assert "telemetry_time_skew" in _codes(report)


def test_import_rejects_duplicate_image_content_across_drones(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    sources = _sources(tmp_path / "input")
    first_image = sources[0].image_dir / "capture-001.jpg"
    second_image = sources[1].image_dir / "capture-001.jpg"
    shutil.copyfile(first_image, second_image)

    report = service.execute(MissionImportRequest(mission=_mission(), sources=sources))

    assert not report.persisted
    assert "duplicate_image" in _codes(report)


def test_import_warns_when_filename_order_disagrees_with_capture_time(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    sources = _sources(tmp_path / "input")
    image_dir = sources[0].image_dir
    _write_image(image_dir / "capture-000.jpg", CAPTURED_AT + timedelta(seconds=1), (1, 2, 3))
    telemetry_file = sources[0].telemetry_file
    assert telemetry_file is not None
    telemetry_file.write_text(
        "timestamp,latitude,longitude,relative_altitude_m\n"
        f"{CAPTURED_AT.isoformat()},10.75,106.67,10\n"
        f"{(CAPTURED_AT + timedelta(seconds=1)).isoformat()},10.75,106.67,10\n",
        encoding="utf-8",
    )

    report = service.execute(MissionImportRequest(mission=_mission(), sources=sources))

    assert report.persisted
    assert "non_monotonic_image_sequence" in _codes(report)
