# -*- mode: python ; coding: utf-8 -*-
# uav_analysis.spec — PyInstaller build config cho phần mềm GreenEye
# Chạy: pyinstaller uav_analysis.spec

from pathlib import Path
import subprocess
import sys
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

BASE = Path(SPECPATH)

# Du lieu di kem, bao gom model pack cuoc bo trong models/checkpoints.
datas = [
    (str(BASE / "models"),           "models"),
    (
        str(BASE / "src" / "uav_crop_analysis" / "resources" / "icons"),
        "uav_crop_analysis/resources/icons",
    ),
    (
        str(BASE / "src" / "uav_crop_analysis" / "resources" / "schemas"),
        "uav_crop_analysis/resources/schemas",
    ),
    (
        str(BASE / "src" / "uav_crop_analysis" / "resources" / "web"),
        "uav_crop_analysis/resources/web",
    ),
]
datas += collect_data_files(
    "rasterio",
    includes=["gdal_data/*", "proj_data/*"],
)

# Cac module an ma PyInstaller co the bo sot.
hidden_imports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "uav_crop_analysis.adapters.sqlite",
    "uav_crop_analysis.adapters.job_sqlite",
    "uav_crop_analysis.adapters.image_metadata",
    "uav_crop_analysis.adapters.manifest",
    "uav_crop_analysis.adapters.model_catalog",
    "uav_crop_analysis.adapters.telemetry_csv",
    "uav_crop_analysis.adapters.spatial_sqlite",
    "uav_crop_analysis.adapters.preview_mosaic",
    "uav_crop_analysis.adapters.rasterio_geospatial",
    "uav_crop_analysis.adapters.nodeodm",
    "uav_crop_analysis.adapters.report_export",
    "uav_crop_analysis.adapters.planning_json",
    "uav_crop_analysis.adapters.mission_plan_export",
    "uav_crop_analysis.planning.application",
    "uav_crop_analysis.planning.models",
    "uav_crop_analysis.planning.ports",
    "uav_crop_analysis.planning.schema",
    "uav_crop_analysis.planning.serialization",
    "uav_crop_analysis.planning.service",
    "uav_crop_analysis.jobs.pipeline",
    "uav_crop_analysis.jobs.service",
    "uav_crop_analysis.jobs.worker",
]
hidden_imports += collect_submodules("uav_crop_analysis.inference.torch_models")
hidden_imports += collect_submodules("ultralytics")
hidden_imports += collect_submodules("rasterio")

a = Analysis(
    ["main.py"],
    pathex=[str(BASE), str(BASE / "src")],
    binaries=collect_dynamic_libs("rasterio"),
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(BASE / "tools" / "pyinstaller_rasterio_runtime.py")],
    # NumPy, Pillow, PyTorch, OpenCV, Transformers, Ultralytics and Qt WebEngine
    # are required by the desktop analysis and geospatial viewers.
    excludes=[
        "matplotlib",
        "tkinter",
        "IPython",
        "jupyter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="UAV_CropAnalysis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # Không hiện cửa sổ CMD đen
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=None,               # Thêm đường dẫn icon .ico ở đây nếu có
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="UAV_CropAnalysis",
)

# PyInstaller thins universal Qt 6.11 frameworks on Apple Silicon. Re-sign the
# resulting framework bundles so QtNetwork and QtWebEngine load in the frozen app.
if sys.platform == "darwin":
    subprocess.run(
        [
            sys.executable,
            str(BASE / "tools" / "codesign_macos_bundle.py"),
            str(Path(DISTPATH) / "UAV_CropAnalysis"),
        ],
        check=True,
    )
