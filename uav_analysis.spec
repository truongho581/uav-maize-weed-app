# -*- mode: python ; coding: utf-8 -*-
# uav_analysis.spec — PyInstaller build config cho phần mềm UAV Crop Analysis
# Chạy: pyinstaller uav_analysis.spec

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

BASE = Path(SPECPATH)

# Du lieu di kem. Checkpoint trien khai duoc cap rieng khi build.
datas = [
    (str(BASE / "models"),           "models"),
]

# Cac module an ma PyInstaller co the bo sot.
hidden_imports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
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
    "uav_crop_analysis.jobs.pipeline",
    "uav_crop_analysis.jobs.service",
    "uav_crop_analysis.jobs.worker",
]
hidden_imports += collect_submodules("uav_crop_analysis.inference.torch_models")

a = Analysis(
    ["main.py"],
    pathex=[str(BASE), str(BASE / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Instance runtimes remain excluded until a maize checkpoint is registered.
    # NumPy, Pillow, PyTorch and Transformers are retained for Phase 6 semantic
    # analysis and result rendering.
    excludes=[
        "cv2",
        "ultralytics",
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
