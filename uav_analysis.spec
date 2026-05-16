# -*- mode: python ; coding: utf-8 -*-
# uav_analysis.spec — PyInstaller build config cho phần mềm UAV Crop Analysis
# Chạy: pyinstaller uav_analysis.spec

import os
from pathlib import Path

BASE = Path(SPECPATH)

# ── Dữ liệu đi kèm (file .ui, thư mục models, …) ──
datas = [
    # File Qt Designer UI
    (str(BASE / "phan_tich_ui.ui"),  "."),
    # Thư mục models (best.pt và bất kỳ file .pt nào trong đó)
    (str(BASE / "models"),           "models"),
]

# ── Các module ẩn mà PyInstaller hay bỏ sót ──
hidden_imports = [
    "PyQt5.uic",
    "PyQt5.QtXml",
    "cv2",
    "numpy",
    "ultralytics",
    "ultralytics.nn.tasks",
    "ultralytics.models.yolo.segment",
]

a = Analysis(
    ["main.py"],
    pathex=[str(BASE)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter", "IPython", "jupyter"],
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
