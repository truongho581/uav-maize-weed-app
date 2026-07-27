import logging
from pathlib import Path

import pytest

from uav_crop_analysis.errors import ConfigurationError
from uav_crop_analysis.infrastructure import AppConfig, configure_logging, resolve_app_paths


def test_linux_paths_honor_xdg_locations(tmp_path: Path) -> None:
    paths = resolve_app_paths(
        system_name="Linux",
        home=tmp_path,
        environ={
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
        },
    )

    assert paths.data_dir == tmp_path / "data/uav-crop-analysis"
    assert paths.config_dir == tmp_path / "config/uav-crop-analysis"
    assert paths.cache_dir == tmp_path / "cache/uav-crop-analysis"
    assert paths.log_dir == tmp_path / "state/uav-crop-analysis/log"


def test_macos_paths_follow_library_conventions(tmp_path: Path) -> None:
    paths = resolve_app_paths(system_name="Darwin", home=tmp_path, environ={})

    assert paths.data_dir == tmp_path / "Library/Application Support/UAV Crop Analysis"
    assert paths.cache_dir == tmp_path / "Library/Caches/UAV Crop Analysis"
    assert paths.log_dir == tmp_path / "Library/Logs/UAV Crop Analysis"


def test_windows_paths_use_local_and_roaming_app_data(tmp_path: Path) -> None:
    paths = resolve_app_paths(
        system_name="Windows",
        home=tmp_path,
        environ={
            "LOCALAPPDATA": str(tmp_path / "AppData/Local"),
            "APPDATA": str(tmp_path / "AppData/Roaming"),
        },
    )

    assert paths.data_dir == tmp_path / "AppData/Local/UAV Crop Analysis"
    assert paths.config_dir == tmp_path / "AppData/Roaming/UAV Crop Analysis"
    assert paths.cache_dir == paths.data_dir / "Cache"
    assert paths.log_dir == paths.data_dir / "Logs"


def test_app_config_rejects_unknown_log_level(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        AppConfig.from_environment(
            system_name="Linux",
            home=tmp_path,
            environ={"UAV_CROP_LOG_LEVEL": "VERBOSE"},
        )


def test_configure_logging_creates_rotating_file_handler(tmp_path: Path) -> None:
    config = AppConfig.from_environment(system_name="Linux", home=tmp_path, environ={})

    logger = configure_logging(config, logger_name="uav_crop_analysis.test")
    logger.info("phase-one-log-check")
    for handler in logger.handlers:
        handler.flush()

    log_path = config.paths.log_dir / "application.log"
    assert log_path.is_file()
    assert "phase-one-log-check" in log_path.read_text()
    assert logger.level == logging.INFO
