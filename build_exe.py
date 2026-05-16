"""
build_exe.py -- Build lai EXE UAV_CropAnalysis bang PyInstaller.
Chay: python build_exe.py
"""
import subprocess
import sys
from pathlib import Path

base      = Path(__file__).parent
spec_file = base / "uav_analysis.spec"

if not spec_file.exists():
    print("ERROR: uav_analysis.spec khong tim thay!")
    sys.exit(1)

print("=" * 60)
print("Building EXE: UAV_CropAnalysis")
print("Spec file  :", spec_file)
print("=" * 60)
print("Qua trinh nay mat 2-5 phut, vui long cho...")
print()

result = subprocess.run(
    [sys.executable, "-m", "PyInstaller", str(spec_file), "--noconfirm"],
    cwd=str(base),
)

print()
if result.returncode == 0:
    exe = base / "dist" / "UAV_CropAnalysis" / "UAV_CropAnalysis.exe"
    print("=" * 60)
    print("THANH CONG!")
    print("EXE:", exe)
    if exe.exists():
        mb = exe.stat().st_size / (1024 * 1024)
        print("Kich thuoc: {:.1f} MB".format(mb))
    print("=" * 60)
else:
    print("THAT BAI - Xem loi o tren.")
    sys.exit(1)
