"""Check Phase 6 screenshots for dimensions and blank content regions."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parents[1] / "docs/phase6/screenshots"
CASES = ((1366, 768), (1440, 900), (1920, 1080))


def main() -> None:
    for view in ("data", "analysis"):
        for width, height in CASES:
            path = ROOT / f"{view}-{width}x{height}.png"
            with Image.open(path).convert("RGB") as image:
                if image.size != (width, height):
                    raise AssertionError(
                        f"{path.name}: expected {(width, height)}, got {image.size}"
                    )
                variances = cast(list[float], ImageStat.Stat(image).var)
                if max(variances) < 100:
                    raise AssertionError(f"{path.name}: render is blank")
                content = image.crop((230, 40, image.width - 30, image.height - 40))
                pixels = cast(
                    Sequence[tuple[int, int, int]], content.get_flattened_data()
                )
                non_surface = sum(
                    not (235 <= red <= 255 and 235 <= green <= 255 and 235 <= blue <= 255)
                    for red, green, blue in pixels
                )
                if non_surface / (content.width * content.height) < 0.02:
                    raise AssertionError(f"{path.name}: content region is empty")
            print(f"PASS {path.name} {width}x{height}")


if __name__ == "__main__":
    main()
