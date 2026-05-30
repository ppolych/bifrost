"""Centralized logging setup.

Writes a rolling log to <config_dir>/bifrost.log and mirrors to stderr.
Call configure_logging() once from the entry point.
"""

import logging
import logging.handlers
import os

from core.platform_utils import config_path
from core.security import redact_text

_configured = False


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original_msg = record.msg
        original_args = record.args
        try:
            record.msg = redact_text(record.getMessage())
            record.args = ()
            return super().format(record)
        finally:
            record.msg = original_msg
            record.args = original_args


def configure_logging(level: int = logging.INFO) -> str:
    global _configured
    if _configured:
        return _log_path()
    _configured = True

    log_path = _log_path()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    formatter = RedactingFormatter(
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
