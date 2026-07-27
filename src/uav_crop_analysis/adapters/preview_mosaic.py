"""Explicitly non-georeferenced contact-sheet preview for three drone lanes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from uav_crop_analysis.domain import ImageAsset, SurveyMission
from uav_crop_analysis.errors import GeospatialError


class LanePreviewMosaicBuilder:
    def __init__(self, thumbnail_size: tuple[int, int] = (180, 120), max_per_lane: int = 10):
        self.thumbnail_size = thumbnail_size
        self.max_per_lane = max_per_lane

    def build(
        self,
        mission: SurveyMission,
        images: Sequence[ImageAsset],
        output_path: Path,
    ) -> dict[str, object]:
        rows = []
        sampled_count = 0
        for assignment in sorted(mission.assignments, key=lambda item: item.lane_index):
            lane_images = sorted(
                (item for item in images if item.drone_id == assignment.drone_id),
                key=lambda item: item.sequence_index,
            )
            sampled = _sample(lane_images, self.max_per_lane)
            rows.append((assignment, sampled, len(lane_images)))
            sampled_count += len(sampled)
        if not sampled_count:
            raise GeospatialError("mission has no images for a spatial preview")

        thumb_width, thumb_height = self.thumbnail_size
        label_width = 180
        gap = 8
        header_height = 46
        row_height = thumb_height + 34
        columns = max(len(row[1]) for row in rows)
        canvas = Image.new(
            "RGB",
            (
                label_width + columns * (thumb_width + gap) + gap,
                header_height + len(rows) * row_height + gap,
            ),
            "#F4F6F5",
        )
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, canvas.width, header_height), fill="#B13A32")
        draw.text(
            (14, 15),
            "SPATIAL PREVIEW - NOT GEOREFERENCED",
            fill="white",
        )
        for row_index, (assignment, sampled, total) in enumerate(rows):
            y = header_height + row_index * row_height
            draw.text(
                (14, y + 18),
                f"Lane {assignment.lane_index + 1}\n{assignment.drone_id.value}\n{len(sampled)}/{total}",
                fill="#18211D",
                spacing=3,
            )
            for column, asset in enumerate(sampled):
                try:
                    with Image.open(asset.source_path) as source:
                        thumbnail = ImageOps.fit(
                            source.convert("RGB"),
                            self.thumbnail_size,
                            method=Image.Resampling.LANCZOS,
                        )
                except OSError as exc:
                    raise GeospatialError(
                        f"cannot open preview image: {asset.source_path}"
                    ) from exc
                x = label_width + column * (thumb_width + gap)
                canvas.paste(thumbnail, (x, y + 4))
                draw.text(
                    (x, y + thumb_height + 8),
                    f"#{asset.sequence_index + 1}  {asset.source_path.name[:18]}",
                    fill="#34413B",
                )
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output)
        return {
            "layout": "lane_sequence_contact_sheet",
            "source_image_count": len(images),
            "sampled_image_count": sampled_count,
            "max_per_lane": self.max_per_lane,
        }


def _sample(images: Sequence[ImageAsset], limit: int) -> tuple[ImageAsset, ...]:
    if len(images) <= limit:
        return tuple(images)
    indices = [round(index * (len(images) - 1) / (limit - 1)) for index in range(limit)]
    return tuple(images[index] for index in indices)
