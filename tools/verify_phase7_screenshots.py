"""Check Phase 7 screenshots for dimensions and blank rendering."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parents[1] / "docs/phase7/screenshots"
CASES = ((1366, 768), (1440, 900), (1920, 1080))


def main() -> None:
    for width, height in CASES:
        path = ROOT / f"spatial-{width}x{height}.png"
        with Image.open(path).convert("RGB") as image:
            if image.size != (width, height):
                raise AssertionError(
                    f"{path.name}: expected {(width, height)}, got {image.size}"
                )
            variances = cast(list[float], ImageStat.Stat(image).var)
            if max(variances) < 100:
                raise AssertionError(f"{path.name}: render is blank")
            viewer = image.crop((230, 330, image.width - 360, image.height - 150))
            viewer_variances = cast(list[float], ImageStat.Stat(viewer).var)
            if max(viewer_variances) < 80:
                raise AssertionError(f"{path.name}: spatial preview is blank")
        print(f"PASS {path.name} {width}x{height}")


if __name__ == "__main__":
    main()
