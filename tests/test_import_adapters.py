from datetime import datetime, timezone
import json
from pathlib import Path

from PIL import Image
import pytest

from uav_crop_analysis.adapters import (
    CsvTelemetryReader,
    PillowExifReader,
    load_mission_manifest,
    write_mission_manifest,
)
from uav_crop_analysis.application import (
    DroneImportSource,
    MissionImportRequest,
    TelemetryCsvMapping,
    TimestampFormat,
)
from uav_crop_analysis.domain import CameraProfile, DroneId, MissionId, SurveyMission
from uav_crop_analysis.errors import ImportDataError


def _write_exif_image(path: Path, captured_at: datetime, color: tuple[int, int, int]) -> None:
    exif = Image.Exif()
    exif[36867] = captured_at.strftime("%Y:%m:%d %H:%M:%S")
    exif[36881] = "+00:00"
    Image.new("RGB", (32, 24), color).save(path, exif=exif)


def test_pillow_reader_extracts_dimensions_and_aware_capture_time(tmp_path: Path) -> None:
    image_path = tmp_path / "capture.jpg"
    captured_at = datetime(2026, 7, 27, 9, 30, 0, tzinfo=timezone.utc)
    _write_exif_image(image_path, captured_at, (20, 100, 30))

    probe = PillowExifReader().read(image_path)

    assert probe.captured_at == captured_at
    assert (probe.width_px, probe.height_px) == (32, 24)
    assert probe.position is None
    assert probe.relative_altitude_m is None


def test_pillow_reader_rejects_image_without_capture_time(tmp_path: Path) -> None:
    image_path = tmp_path / "no-exif.jpg"
    Image.new("RGB", (16, 16)).save(image_path)

    with pytest.raises(ImportDataError, match="no EXIF capture timestamp"):
        PillowExifReader().read(image_path)


def test_csv_reader_supports_custom_columns_and_unix_milliseconds(tmp_path: Path) -> None:
    csv_path = tmp_path / "flight.csv"
    csv_path.write_text(
        "time_ms,lat,lon,alt\n"
        "1785142800000,10.75,106.67,10.5\n",
        encoding="utf-8",
    )
    mapping = TelemetryCsvMapping(
        timestamp_column="time_ms",
        latitude_column="lat",
        longitude_column="lon",
        relative_altitude_column="alt",
        timestamp_format=TimestampFormat.UNIX_MILLISECONDS,
    )

    result = CsvTelemetryReader().read(
        csv_path,
        mapping,
        MissionId("mission-001"),
        DroneId("drone-01"),
    )

    assert not result.issues
    assert len(result.samples) == 1
    assert result.samples[0].position.latitude == 10.75
    assert result.samples[0].relative_altitude_m == 10.5


def test_csv_reader_reports_invalid_gps_row(tmp_path: Path) -> None:
    csv_path = tmp_path / "flight.csv"
    csv_path.write_text(
        "timestamp,latitude,longitude,relative_altitude_m\n"
        "2026-07-27T09:30:00+00:00,999,106.67,10\n",
        encoding="utf-8",
    )

    result = CsvTelemetryReader().read(
        csv_path,
        TelemetryCsvMapping(),
        MissionId("mission-001"),
        DroneId("drone-01"),
    )

    assert not result.samples
    assert [issue.code for issue in result.issues] == ["invalid_telemetry_row"]
    assert result.issues[0].row_number == 2


@pytest.mark.parametrize("drone_count", [1, 2, 3])
def test_mission_manifest_round_trip_supports_one_to_three_drones(
    tmp_path: Path,
    drone_count: int,
) -> None:
    drone_ids = tuple(f"drone-0{index}" for index in range(1, drone_count + 1))
    mission = SurveyMission.create(
        mission_id="mission-manifest",
        name="Manifest contract",
        drone_ids=drone_ids,
        created_at=datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc),
    )
    camera = CameraProfile(profile_id="rgb", name="RGB camera")
    sources = tuple(
        DroneImportSource(
            drone_id=DroneId(f"drone-0{index}"),
            image_dir=tmp_path / f"drone-0{index}/images",
            telemetry_file=tmp_path / f"drone-0{index}/flight.csv",
            camera_profile=camera,
        )
        for index in range(1, drone_count + 1)
    )
    request = MissionImportRequest(mission=mission, sources=sources)
    manifest_path = tmp_path / "mission.json"

    write_mission_manifest(request, manifest_path)
    loaded = load_mission_manifest(manifest_path)

    assert loaded.mission == mission
    assert loaded.sources == sources
    text = manifest_path.read_text()
    assert '"image_dir": "drone-01/images"' in text
    assert '"lane_index": 0' in text


@pytest.mark.parametrize("drone_count", [0, 4])
def test_mission_manifest_rejects_drone_count_outside_supported_range(
    tmp_path: Path,
    drone_count: int,
) -> None:
    rows = [
        {"drone_id": f"drone-{index}", "lane_index": index}
        for index in range(drone_count)
    ]
    path = tmp_path / "mission.json"
    path.write_text(
        """
        {
          "schema_version": 1,
          "mission": {
            "mission_id": "mission-invalid-count",
            "name": "Invalid count",
            "created_at": "2026-07-27T09:00:00+00:00",
            "flight_profile": {
              "altitude_m": 10.0,
              "gimbal_pitch_deg": -90.0,
              "forward_overlap": 0.75,
              "side_overlap": 0.65,
              "capture_mode": "stop_and_capture"
            }
          },
          "drones": DRONE_ROWS
        }
        """.replace("DRONE_ROWS", json.dumps(rows)),
        encoding="utf-8",
    )

    with pytest.raises(ImportDataError, match="must define 1 to 3 drones"):
        load_mission_manifest(path)


def test_mission_manifest_rejects_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "mission.json"
    path.write_text('{"schema_version": 99}', encoding="utf-8")

    with pytest.raises(ImportDataError, match="unsupported mission manifest schema"):
        load_mission_manifest(path)
