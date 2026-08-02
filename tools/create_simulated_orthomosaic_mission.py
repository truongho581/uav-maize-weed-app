"""Create a three-drone mission fixture from one orthomosaic-like JPEG and a DJI DNG."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import timedelta, timezone
import json
from math import atan, cos, degrees, radians, tan
from pathlib import Path
import re
import shutil
from typing import Any, cast

from PIL import Image

from uav_crop_analysis.adapters.image_metadata import PillowExifReader


DRONE_IDS = ("drone-01", "drone-02", "drone-03")
TILE_WIDTH_PX = 2460
TILE_HEIGHT_PX = 1845
LANE_X_ORIGINS_PX = (0, 770, 1540)
CAPTURE_Y_ORIGINS_PX = (0, 461, 922, 1155)
CAPTURE_INTERVAL_SECONDS = 3


@dataclass(frozen=True, slots=True)
class DngMetadata:
    captured_at: str
    latitude: float
    longitude: float
    absolute_altitude_m: float | None
    relative_altitude_m: float
    make: str | None
    model: str | None
    focal_length_mm: float
    focal_length_35mm: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_jpg", type=Path)
    parser.add_argument("source_dng", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--mission-id", default="mission-sim-dji0438-10m")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_jpg = args.source_jpg.expanduser().resolve()
    source_dng = args.source_dng.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    _prepare_output(output_dir, args.overwrite)
    metadata = _read_dng_metadata(source_dng)

    with Image.open(source_jpg) as image:
        source = image.convert("RGB")
    _validate_layout(source.size)
    horizontal_fov_deg, vertical_fov_deg = _full_frame_fov(metadata.focal_length_35mm)
    meters_per_pixel = _meters_per_pixel(
        metadata.relative_altitude_m,
        horizontal_fov_deg,
        source.width,
    )

    tile_records = _write_tiles(source, output_dir, metadata, meters_per_pixel)
    _write_telemetry(output_dir, tile_records)
    _write_manifest(
        output_dir,
        args.mission_id,
        metadata,
        horizontal_fov_deg,
        vertical_fov_deg,
    )
    _write_provenance(
        output_dir,
        source_jpg,
        source_dng,
        metadata,
        horizontal_fov_deg,
        vertical_fov_deg,
        meters_per_pixel,
        tile_records,
    )
    print(output_dir / "mission.json")
    return 0


def _prepare_output(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise SystemExit(f"output directory already exists: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)


def _read_dng_metadata(path: Path) -> DngMetadata:
    probe = PillowExifReader(default_timezone=timezone.utc).read(path)
    if probe.position is None:
        raise SystemExit(f"DNG has no readable GPS position: {path}")
    with Image.open(path) as image:
        exif = image.getexif()
        exif_ifd = dict(exif.get_ifd(34665))
        xmp = _decode_xmp(exif.get(700, b""))
        make = _text(exif.get(271))
        model = _text(exif.get(272))
        focal_length = float(exif_ifd.get(37386, 4.49))
        focal_length_35mm = float(exif_ifd.get(41989, 24.0))
    return DngMetadata(
        captured_at=probe.captured_at.isoformat(),
        latitude=probe.position.latitude,
        longitude=probe.position.longitude,
        absolute_altitude_m=probe.absolute_altitude_m,
        relative_altitude_m=_xmp_float(xmp, "RelativeAltitude", 10.0),
        make=make,
        model=model,
        focal_length_mm=focal_length,
        focal_length_35mm=focal_length_35mm,
    )


def _decode_xmp(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


def _xmp_float(xmp: str, name: str, default: float) -> float:
    match = re.search(rf"drone-dji:{name}=\"([+-]?[0-9.]+)\"", xmp)
    return float(match.group(1)) if match else default


def _text(value: object) -> str | None:
    if value is None:
        return None
    return str(value).rstrip("\x00") or None


def _validate_layout(size: tuple[int, int]) -> None:
    width, height = size
    if width < LANE_X_ORIGINS_PX[-1] + TILE_WIDTH_PX:
        raise SystemExit("source image is narrower than the three-lane simulation layout")
    if height < CAPTURE_Y_ORIGINS_PX[-1] + TILE_HEIGHT_PX:
        raise SystemExit("source image is shorter than the capture simulation layout")


def _full_frame_fov(focal_length_35mm: float) -> tuple[float, float]:
    return (
        degrees(2.0 * atan(36.0 / (2.0 * focal_length_35mm))),
        degrees(2.0 * atan(24.0 / (2.0 * focal_length_35mm))),
    )


def _meters_per_pixel(altitude_m: float, horizontal_fov_deg: float, width_px: int) -> float:
    ground_width_m = 2.0 * altitude_m * tan(radians(horizontal_fov_deg) / 2.0)
    return ground_width_m / width_px


def _write_tiles(
    source: Image.Image,
    output_dir: Path,
    metadata: DngMetadata,
    meters_per_pixel: float,
) -> list[dict[str, object]]:
    captured_at = _parse_time(metadata.captured_at)
    records: list[dict[str, object]] = []
    for lane_index, (drone_id, origin_x) in enumerate(zip(DRONE_IDS, LANE_X_ORIGINS_PX)):
        image_dir = output_dir / "data" / drone_id / "images"
        image_dir.mkdir(parents=True)
        for sequence_index, origin_y in enumerate(CAPTURE_Y_ORIGINS_PX):
            tile = source.crop(
                (origin_x, origin_y, origin_x + TILE_WIDTH_PX, origin_y + TILE_HEIGHT_PX)
            )
            timestamp = captured_at + timedelta(seconds=sequence_index * CAPTURE_INTERVAL_SECONDS)
            image_path = image_dir / f"{sequence_index + 1:03d}.jpg"
            tile.save(image_path, "JPEG", quality=95, subsampling=0, exif=_timestamp_exif(timestamp))
            latitude, longitude = _tile_position(
                metadata.latitude,
                metadata.longitude,
                source.size,
                origin_x,
                origin_y,
                meters_per_pixel,
            )
            records.append(
                {
                    "drone_id": drone_id,
                    "lane_index": lane_index,
                    "sequence_index": sequence_index,
                    "image_path": str(image_path.relative_to(output_dir)),
                    "timestamp": timestamp.isoformat(),
                    "latitude": latitude,
                    "longitude": longitude,
                    "relative_altitude_m": metadata.relative_altitude_m,
                    "crop_box_px": [origin_x, origin_y, TILE_WIDTH_PX, TILE_HEIGHT_PX],
                }
            )
    return records


def _parse_time(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)


def _timestamp_exif(timestamp) -> Image.Exif:
    formatted = timestamp.strftime("%Y:%m:%d %H:%M:%S")
    offset = timestamp.strftime("%z")
    offset = f"{offset[:3]}:{offset[3:]}" if offset else "+00:00"
    exif = Image.Exif()
    exif[306] = formatted
    exif[36867] = formatted
    exif[36881] = offset
    return exif


def _tile_position(
    anchor_latitude: float,
    anchor_longitude: float,
    source_size: tuple[int, int],
    origin_x: int,
    origin_y: int,
    meters_per_pixel: float,
) -> tuple[float, float]:
    center_x = origin_x + TILE_WIDTH_PX / 2.0
    center_y = origin_y + TILE_HEIGHT_PX / 2.0
    east_m = (center_x - source_size[0] / 2.0) * meters_per_pixel
    north_m = (source_size[1] / 2.0 - center_y) * meters_per_pixel
    latitude = anchor_latitude + north_m / 111_320.0
    longitude = anchor_longitude + east_m / (111_320.0 * cos(radians(anchor_latitude)))
    return latitude, longitude


def _write_telemetry(output_dir: Path, records: list[dict[str, object]]) -> None:
    for drone_id in DRONE_IDS:
        telemetry_path = output_dir / "data" / drone_id / "flight.csv"
        drone_records = [record for record in records if record["drone_id"] == drone_id]
        with telemetry_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("timestamp", "latitude", "longitude", "relative_altitude_m"),
            )
            writer.writeheader()
            writer.writerows(
                {
                    "timestamp": record["timestamp"],
                    "latitude": f"{float(cast(Any, record['latitude'])):.8f}",
                    "longitude": f"{float(cast(Any, record['longitude'])):.8f}",
                    "relative_altitude_m": (
                        f"{float(cast(Any, record['relative_altitude_m'])):.2f}"
                    ),
                }
                for record in drone_records
            )


def _write_manifest(
    output_dir: Path,
    mission_id: str,
    metadata: DngMetadata,
    horizontal_fov_deg: float,
    vertical_fov_deg: float,
) -> None:
    camera_profile: dict[str, object] = {
        "profile_id": "dji-fc7703-simulated-crop",
        "name": "DJI FC7703 simulated orthomosaic crop",
        "make": metadata.make,
        "model": metadata.model,
        "image_width_px": TILE_WIDTH_PX,
        "image_height_px": TILE_HEIGHT_PX,
        "focal_length_mm": metadata.focal_length_mm,
        "horizontal_fov_deg": round(horizontal_fov_deg, 4),
        "vertical_fov_deg": round(vertical_fov_deg, 4),
        "distortion_coefficients": [],
    }
    payload = {
        "schema_version": 1,
        "mission": {
            "mission_id": mission_id,
            "name": "Simulated three-drone DJI_0438 10m survey",
            "created_at": metadata.captured_at,
            "flight_profile": {
                "altitude_m": metadata.relative_altitude_m,
                "gimbal_pitch_deg": -90.0,
                "forward_overlap": 0.75,
                "side_overlap": round(1.0 - 770.0 / TILE_WIDTH_PX, 4),
                "capture_mode": "stop_and_capture",
            },
        },
        "max_telemetry_skew_seconds": 0.5,
        "drones": [
            {
                "drone_id": drone_id,
                "lane_index": lane_index,
                "image_dir": f"data/{drone_id}/images",
                "telemetry_file": f"data/{drone_id}/flight.csv",
                "telemetry_mapping": {
                    "timestamp_column": "timestamp",
                    "latitude_column": "latitude",
                    "longitude_column": "longitude",
                    "relative_altitude_column": "relative_altitude_m",
                    "timestamp_format": "iso8601",
                },
                "camera_profile": camera_profile,
            }
            for lane_index, drone_id in enumerate(DRONE_IDS)
        ],
    }
    (output_dir / "mission.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_provenance(
    output_dir: Path,
    source_jpg: Path,
    source_dng: Path,
    metadata: DngMetadata,
    horizontal_fov_deg: float,
    vertical_fov_deg: float,
    meters_per_pixel: float,
    tile_records: list[dict[str, object]],
) -> None:
    payload = {
        "kind": "synthetic_orthomosaic_mission",
        "source_jpg": str(source_jpg),
        "source_dng": str(source_dng),
        "dng_metadata": asdict(metadata),
        "assumptions": {
            "orthomosaic_orientation": "north_up",
            "anchor": "DNG GPS is assumed to be the source JPEG center",
            "gimbal_pitch_deg": -90.0,
            "forward_overlap": 0.75,
            "side_overlap": round(1.0 - 770.0 / TILE_WIDTH_PX, 4),
            "capture_mode": "stop_and_capture",
            "horizontal_fov_deg": horizontal_fov_deg,
            "vertical_fov_deg": vertical_fov_deg,
            "estimated_meters_per_source_pixel": meters_per_pixel,
        },
        "tiles": tile_records,
    }
    (output_dir / "simulation_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
