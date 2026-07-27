"""Check Phase 5 screenshot dimensions and obvious blank-render regressions."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parents[1] / "docs/phase5/screenshots"
CASES = (
    (1366, 768, "10", 1.0),
    (1366, 768, "125", 1.25),
    (1366, 768, "15", 1.5),
    (1440, 900, "10", 1.0),
    (1440, 900, "125", 1.25),
    (1440, 900, "15", 1.5),
    (1920, 1080, "10", 1.0),
    (1920, 1080, "125", 1.25),
    (1920, 1080, "15", 1.5),
)


def main() -> None:
    for width, height, scale_name, scale in CASES:
        path = ROOT / f"overview-{width}x{height}-{scale_name}.png"
        with Image.open(path).convert("RGB") as image:
            expected = (round(width * scale), round(height * scale))
            if image.size != expected:
                raise AssertionError(f"{path.name}: expected {expected}, got {image.size}")
            variances = cast(list[float], ImageStat.Stat(image).var)
            if max(variances) < 100:
                raise AssertionError(f"{path.name}: render is blank or nearly uniform")
            sidebar = image.crop((0, 0, round(200 * scale), image.height - 30))
            pixels = cast(
                Sequence[tuple[int, int, int]], sidebar.get_flattened_data()
            )
            dark_pixels = sum(
                red < 55 and green < 65 and blue < 60
                for red, green, blue in pixels
            )
            if dark_pixels / (sidebar.width * sidebar.height) < 0.75:
                raise AssertionError(f"{path.name}: sidebar did not render")
        print(f"PASS {path.name} {expected[0]}x{expected[1]}")


if __name__ == "__main__":
    main()
