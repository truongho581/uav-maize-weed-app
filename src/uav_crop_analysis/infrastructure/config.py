"""Environment-backed runtime configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from uav_crop_analysis.errors import ConfigurationError
from uav_crop_analysis.infrastructure.paths import AppPaths, resolve_app_paths


LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True, slots=True)
class AppConfig:
    paths: AppPaths
    log_level: str = "INFO"

    @classmethod
    def from_environment(
        cls,
        *,
        system_name: str | None = None,
        home: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> AppConfig:
        env = environ if environ is not None else os.environ
        log_level = env.get("UAV_CROP_LOG_LEVEL", "INFO").strip().upper()
        if log_level not in LOG_LEVELS:
            raise ConfigurationError(
                f"invalid UAV_CROP_LOG_LEVEL: {log_level}",
                context={"field": "UAV_CROP_LOG_LEVEL", "value": log_level},
            )
        return cls(
            paths=resolve_app_paths(system_name=system_name, home=home, environ=env),
            log_level=log_level,
        )
