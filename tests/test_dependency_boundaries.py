import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
HEAVY_MODULES = ("PyQt5", "PySide6", "cv2", "numpy", "torch", "ultralytics")


def _run_isolated_import(module: str) -> set[str]:
    script = (
        "import json, sys; "
        f"import {module}; "
        f"blocked={HEAVY_MODULES!r}; "
        "print(json.dumps(sorted(name for name in blocked if name in sys.modules)))"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    import json

    return set(json.loads(completed.stdout))


def test_domain_import_does_not_load_ui_or_ai_dependencies() -> None:
    assert _run_isolated_import("uav_crop_analysis.domain") == set()


def test_application_import_does_not_load_ui_or_ai_runtimes() -> None:
    assert _run_isolated_import("uav_crop_analysis.application") == {"numpy"}


def test_inference_contract_import_does_not_initialize_torch() -> None:
    assert _run_isolated_import("uav_crop_analysis.inference") == {"numpy"}


def test_job_models_import_does_not_initialize_inference_dependencies() -> None:
    assert _run_isolated_import("uav_crop_analysis.jobs") == set()
