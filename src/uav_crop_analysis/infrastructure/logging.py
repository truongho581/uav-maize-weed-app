"""Application logging configured explicitly by composition roots."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from uav_crop_analysis.infrastructure.config import AppConfig


def configure_logging(
    config: AppConfig,
    *,
    logger_name: str = "uav_crop_analysis",
) -> logging.Logger:
    config.paths.ensure_exists()
    logger = logging.getLogger(logger_name)
    logger.setLevel(config.log_level)
    logger.propagate = False

    for handler in tuple(logger.handlers):
        if getattr(handler, "_uav_crop_handler", False):
            logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        config.paths.log_dir / "application.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    handler._uav_crop_handler = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    return logger
