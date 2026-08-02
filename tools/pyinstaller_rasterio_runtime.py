"""Configure GDAL and PROJ data paths inside the frozen desktop bundle."""

from __future__ import annotations

import os
from pathlib import Path
import sys


# The frozen macOS application launches QtWebEngine helper processes for the
# interactive planning and field maps. The helper runs inside the signed app
# bundle, so Chromium's Linux sandbox is neither needed nor reliably available.
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")


bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
rasterio_root = bundle_root / "rasterio"
gdal_data = rasterio_root / "gdal_data"
proj_data = rasterio_root / "proj_data"

if gdal_data.is_dir():
    os.environ.setdefault("GDAL_DATA", str(gdal_data))
if proj_data.is_dir():
    os.environ.setdefault("PROJ_DATA", str(proj_data))
    os.environ.setdefault("PROJ_LIB", str(proj_data))

# PyInstaller can preserve the macOS framework symlinks but place WebEngine
# resources below ``Versions/Resources/Resources``. Qt itself only searches the
# canonical framework location, so point it at the deployed files explicitly.
webengine_framework = (
    bundle_root / "PySide6" / "Qt" / "lib" / "QtWebEngineCore.framework"
)
resource_candidates = (
    webengine_framework / "Versions" / "Resources" / "Resources",
    webengine_framework / "Versions" / "A" / "Resources",
    webengine_framework / "Resources",
)
for resource_path in resource_candidates:
    if (resource_path / "qtwebengine_resources.pak").is_file():
        os.environ["QTWEBENGINE_RESOURCES_PATH"] = str(resource_path)
        locales_path = resource_path / "qtwebengine_locales"
        if locales_path.is_dir():
            os.environ["QTWEBENGINE_LOCALES_PATH"] = str(locales_path)
        break

helper_candidates = (
    webengine_framework
    / "Versions"
    / "Resources"
    / "Helpers"
    / "QtWebEngineProcess.app"
    / "Contents"
    / "MacOS"
    / "QtWebEngineProcess",
    webengine_framework
    / "Versions"
    / "A"
    / "Helpers"
    / "QtWebEngineProcess.app"
    / "Contents"
    / "MacOS"
    / "QtWebEngineProcess",
    webengine_framework
    / "Helpers"
    / "QtWebEngineProcess.app"
    / "Contents"
    / "MacOS"
    / "QtWebEngineProcess",
)
for helper_path in helper_candidates:
    if helper_path.is_file():
        os.environ["QTWEBENGINEPROCESS_PATH"] = str(helper_path)
        break
