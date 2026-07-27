"""Image metadata reader backed by Pillow EXIF APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from uav_crop_analysis.application.import_models import ImageProbe
from uav_crop_analysis.domain import GeoPoint
from uav_crop_analysis.errors import ImportDataError


TAG_DATETIME = 306
TAG_DATETIME_ORIGINAL = 36867
TAG_OFFSET_TIME = 36880
TAG_OFFSET_TIME_ORIGINAL = 36881
TAG_GPS_INFO = 34853


class PillowExifReader:
    def __init__(self, *, default_timezone: tzinfo = timezone.utc) -> None:
        self.default_timezone = default_timezone

    def read(self, image_path: Path) -> ImageProbe:
        path = Path(image_path).expanduser().resolve()
        try:
            with Image.open(path) as image:
                width, height = image.size
                exif = image.getexif()
                captured_at = self._capture_time(exif, path)
                position, absolute_altitude = self._gps(exif)
        except (OSError, UnidentifiedImageError) as exc:
            raise ImportDataError(
                f"cannot read image metadata: {path}",
                context={"source": str(path)},
            ) from exc

        return ImageProbe(
            source_path=path,
            captured_at=captured_at,
            width_px=width,
            height_px=height,
            position=position,
            absolute_altitude_m=absolute_altitude,
        )

    def _capture_time(self, exif: Image.Exif, path: Path) -> datetime:
        raw = exif.get(TAG_DATETIME_ORIGINAL) or exif.get(TAG_DATETIME)
        if not raw:
            raise ImportDataError(
                f"image has no EXIF capture timestamp: {path}",
                context={"source": str(path), "field": "captured_at"},
            )
        try:
            parsed = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
            offset = exif.get(TAG_OFFSET_TIME_ORIGINAL) or exif.get(TAG_OFFSET_TIME)
            return parsed.replace(tzinfo=self._parse_offset(str(offset)) if offset else self.default_timezone)
        except ValueError as exc:
            raise ImportDataError(
                f"invalid EXIF capture timestamp: {raw}",
                context={"source": str(path), "field": "captured_at"},
            ) from exc

    @staticmethod
    def _parse_offset(value: str) -> tzinfo:
        sign = -1 if value.startswith("-") else 1
        hours, minutes = value.lstrip("+-").split(":", maxsplit=1)
        return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))

    @classmethod
    def _gps(cls, exif: Image.Exif) -> tuple[GeoPoint | None, float | None]:
        if TAG_GPS_INFO not in exif:
            return None, None
        try:
            gps: dict[int, Any] = dict(exif.get_ifd(TAG_GPS_INFO))
            latitude = cls._coordinate(gps[2], gps[1])
            longitude = cls._coordinate(gps[4], gps[3])
            altitude = float(gps[6]) if 6 in gps else None
            if altitude is not None and gps.get(5) == 1:
                altitude = -altitude
            return GeoPoint(latitude, longitude), altitude
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None, None

    @staticmethod
    def _coordinate(values: Any, reference: Any) -> float:
        degrees, minutes, seconds = (float(item) for item in values)
        result = degrees + minutes / 60.0 + seconds / 3600.0
        if str(reference).upper() in {"S", "W"}:
            result *= -1
        return result
