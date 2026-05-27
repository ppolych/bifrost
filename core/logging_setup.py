"""Centralized logging setup.

Writes a rolling log to <config_dir>/bifrost.log and mirrors to stderr.
Call configure_logging() once from the entry point.
"""

import logging
import logging.handlers
import os

from core.platform_utils import config_path

_configured = False


def configure_logging(level: int = logging.INFO) -> str:
    global _configured
    if _configured:
        return _log_path()
    _configured = True

    log_path = _log_path()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicating handlers if configure_logging is called more than once
    # (e.g. by tests).
    root.handlers = [file_handler, stderr_handler]

    return log_path


def _log_path() -> str:
    return config_path("bifrost.log")
