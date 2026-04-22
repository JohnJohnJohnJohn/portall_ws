"""Structured JSON logging setup."""

import json
import logging
import logging.handlers
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def _default_log_dir() -> Path:
    env_dir = os.environ.get("DESK_PRICER_LOG_DIR")
    if env_dir:
        return Path(env_dir)
    if sys.platform == "win32":
        return Path(r"C:\ProgramData\DeskPricer\logs")
    return Path.home() / ".local" / "share" / "deskpricer" / "logs"


def get_log_file() -> Path:
    return _default_log_dir() / "pricer.log"


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_dict: dict = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
        }
        # Extra fields injected by callers (method, path, query, duration_ms, status)
        for key in ("method", "path", "query", "duration_ms", "status"):
            if hasattr(record, key):
                log_dict[key] = getattr(record, key)
        # Include message only if it's more than a placeholder
        msg = record.getMessage()
        if msg and msg != "request":
            log_dict["message"] = msg
        return json.dumps(log_dict)


def setup_logging() -> logging.Logger:
    """Configure the desk_pricer logger with a rotating JSON file handler."""
    logger = logging.getLogger("desk_pricer")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    log_dir = _default_log_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # If we can't create the directory, fall back to stderr-only
        sys.stderr.write(f"[DeskPricer] failed to create log dir {log_dir}: {exc}\n")
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        return logger

    log_file = log_dir / "pricer.log"
    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    return logger
