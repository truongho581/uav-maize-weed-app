"""Cross-platform application data locations without import-time I/O."""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from uav_crop_analysis.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_dir: Path
    config_dir: Path
    cache_dir: Path
    log_dir: Path

    def ensure_exists(self) -> AppPaths:
        for path in (self.data_dir, self.config_dir, self.cache_dir, self.log_dir):
            path.mkdir(parents=True, exist_ok=True)
        return self


def resolve_app_paths(
    *,
    system_name: str | None = None,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> AppPaths:
    system = system_name or platform.system()
    user_home = (home or Path.home()).expanduser()
    env = environ if environ is not None else os.environ

    if system == "Windows":
        local = Path(env.get("LOCALAPPDATA", user_home / "AppData/Local"))
        roaming = Path(env.get("APPDATA", user_home / "AppData/Roaming"))
        data_dir = local / "UAV Crop Analysis"
        return AppPaths(
            data_dir=data_dir,
            config_dir=roaming / "UAV Crop Analysis",
            cache_dir=data_dir / "Cache",
            log_dir=data_dir / "Logs",
        )

    if system == "Darwin":
        return AppPaths(
            data_dir=user_home / "Library/Application Support/UAV Crop Analysis",
            config_dir=user_home / "Library/Application Support/UAV Crop Analysis",
            cache_dir=user_home / "Library/Caches/UAV Crop Analysis",
            log_dir=user_home / "Library/Logs/UAV Crop Analysis",
        )

    if system == "Linux":
        data_home = Path(env.get("XDG_DATA_HOME", user_home / ".local/share"))
        config_home = Path(env.get("XDG_CONFIG_HOME", user_home / ".config"))
        cache_home = Path(env.get("XDG_CACHE_HOME", user_home / ".cache"))
        state_home = Path(env.get("XDG_STATE_HOME", user_home / ".local/state"))
        return AppPaths(
            data_dir=data_home / "uav-crop-analysis",
            config_dir=config_home / "uav-crop-analysis",
            cache_dir=cache_home / "uav-crop-analysis",
            log_dir=state_home / "uav-crop-analysis/log",
        )

    raise ConfigurationError(
        f"unsupported operating system: {system}",
        context={"system_name": system},
    )
