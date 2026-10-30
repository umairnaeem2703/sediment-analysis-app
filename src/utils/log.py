"""Logging: one logger, a console handler, and a log file in the project folder while a project is open (B5)."""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional

LOGGER_NAME = "sediment"
LOG_DIR, LOG_NAME = "logs", "app.log"
_FORMAT = "%(asctime)s %(levelname)s %(message)s"

MAX_BYTES, BACKUPS = 1_000_000, 3  # the file rolls over to app.log.1 .. app.log.3, so the log stays small to send

_file_handler: Optional[logging.handlers.RotatingFileHandler] = None


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def configure() -> None:
    """Send the log to the console at INFO and above. Safe to call more than once."""
    logger = get_logger()
    logger.setLevel(logging.INFO)
    if not any(type(handler) is logging.StreamHandler for handler in logger.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(console)


def attach_project_log(folder) -> Optional[Path]:
    """Also write the log to `<folder>/logs/app.log`, in place of the log of the project before. Returns the file, or
    None when it can not be opened: a project on a read-only disk still works, without a log file."""
    detach_project_log()
    path = Path(folder) / LOG_DIR / LOG_NAME
    try:
        path.parent.mkdir(exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    except OSError:
        get_logger().warning("The log file %s can not be written.", path)
        return None
    handler.setFormatter(logging.Formatter(_FORMAT))
    get_logger().setLevel(logging.INFO)
    get_logger().addHandler(handler)
    global _file_handler
    _file_handler = handler
    return path


def detach_project_log() -> None:
    global _file_handler
    if _file_handler is not None:
        get_logger().removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None


def log_file() -> Optional[Path]:
    return Path(_file_handler.baseFilename) if _file_handler is not None else None
