"""Cross-platform smoke test for the frozen GreenEye executable."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time


def default_executable() -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return Path("dist/UAV_CropAnalysis") / f"UAV_CropAnalysis{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, default=default_executable())
    parser.add_argument("--seconds", type=float, default=10.0)
    args = parser.parse_args()
    executable = args.executable.resolve()
    if not executable.is_file():
        raise FileNotFoundError(executable)
    environment = dict(os.environ)
    if sys.platform != "darwin":
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    environment.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    environment["UAV_CROP_WEBENGINE_SMOKE"] = "1"
    process = subprocess.Popen(
        [str(executable)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    completed = False
    try:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            return_code = process.poll()
            if return_code is not None:
                if return_code == 0:
                    completed = True
                    break
                output = process.stdout.read() if process.stdout is not None else ""
                raise RuntimeError(
                    f"frozen app exited early with {return_code}:\n{output}"
                )
            time.sleep(0.2)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    if not completed:
        raise RuntimeError(f"frozen WebEngine smoke timed out after {args.seconds:g}s")
    print(f"frozen WebEngine smoke passed: {executable} ({args.seconds:g}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
