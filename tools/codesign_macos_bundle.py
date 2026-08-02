"""Repair ad-hoc signatures on thinned Qt frameworks in a macOS one-folder build."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def repair_webengine_framework(bundle: Path) -> bool:
    """Restore Qt's canonical resource paths after PyInstaller collection."""
    framework = (
        bundle
        / "_internal"
        / "PySide6"
        / "Qt"
        / "lib"
        / "QtWebEngineCore.framework"
    )
    deployed_resources = framework / "Versions" / "Resources"
    canonical_version = framework / "Versions" / "A"
    resources = deployed_resources / "Resources"
    helpers = deployed_resources / "Helpers"
    if not resources.is_dir() or not helpers.is_dir() or not canonical_version.is_dir():
        return False

    # QtWebEngine resolves these through Versions/Current -> A.  PyInstaller
    # preserves that link but collects the payload below Versions/Resources.
    shutil.copytree(resources, canonical_version / "Resources", dirs_exist_ok=True)
    shutil.copytree(helpers, canonical_version / "Helpers", dirs_exist_ok=True)
    return True


def native_libraries(bundle: Path) -> list[Path]:
    """Return loose Mach-O libraries that are not covered by a framework seal."""
    internal = bundle / "_internal"
    return sorted(
        path
        for extension in ("*.dylib", "*.so")
        for path in internal.rglob(extension)
        if ".framework/" not in str(path)
    )


def sign(path: Path, *, deep: bool = False) -> None:
    command = ["codesign", "--force", "--sign", "-"]
    if deep:
        command.append("--deep")
    command.append(str(path))
    subprocess.run(command, check=True, capture_output=True, text=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    bundle = args.bundle.expanduser().resolve()
    if sys.platform != "darwin" or not bundle.is_dir():
        return
    repaired_webengine = repair_webengine_framework(bundle)
    libraries = native_libraries(bundle)
    for library in libraries:
        sign(library)
    frameworks = sorted(
        path for path in (bundle / "_internal").rglob("*.framework") if path.is_dir()
    )
    for framework in frameworks:
        sign(framework, deep=True)
    suffix = "; restored QtWebEngine resource paths" if repaired_webengine else ""
    print(
        f"Re-signed {len(libraries)} native libraries and {len(frameworks)} "
        f"macOS frameworks in {bundle}{suffix}"
    )


if __name__ == "__main__":
    main()
