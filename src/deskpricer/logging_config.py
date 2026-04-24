"""Structured JSON logging setup."""

import json
import logging
import logging.handlers
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def _default_log_dir() -> Path:
    if env_dir := os.environ.get("DESKPRICER_LOG_DIR"):
        return Path(env_dir)
    if sys.platform == "win32":
        return Path(r"C:\ProgramData\DeskPricer\logs")
    return Path.home() / ".local" / "share" / "deskpricer" / "logs"


def get_log_file() -> Path:
    return _default_log_dir() / "pricer.log"


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        try:
            log_dict: dict = {
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "level": record.levelname,
                "logger": record.name,
                "pathname": record.pathname,
                "lineno": record.lineno,
            }
            # Extra fields injected by callers (method, path, query, duration_ms, status)
            for key in ("method", "path", "query", "duration_ms", "status"):
                if hasattr(record, key):
                    val = getattr(record, key)
                    # Defensive: coerce anything that isn't a plain scalar
                    if isinstance(val, str):
                        # Drop lone surrogates that break JSON encoding
                        val = val.encode("utf-8", "surrogatepass").decode("utf-8", "replace")
                    log_dict[key] = val
            # Include message only if it's more than a placeholder
            msg = record.getMessage()
            if msg and msg != "request":
                log_dict["message"] = msg
            if record.exc_info:
                exc_type = record.exc_info[0]
                log_dict["exc_type"] = exc_type.__name__ if exc_type else None
                log_dict["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_dict, default=str)
        except Exception:
            # Absolute fallback — never let a formatter crash leak a Python traceback
            return json.dumps(
                {
                    "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "level": "ERROR",
                    "logger": getattr(record, "name", "unknown"),
                    "message": "LOG_FORMATTER_FAILED",
                }
            )


class _SafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler that swallows Windows PermissionError on rollover.

    On Windows another process (or an antivirus hook) can hold the log file
    open, causing ``os.rename`` to fail with WinError 32.  Rather than crash
    the logging subsystem we skip the rotation and keep appending.
    """

    _rollover_cooldown_until = 0.0

    def shouldRollover(self, record):
        if time.monotonic() < self._rollover_cooldown_until:
            return False
        return super().shouldRollover(record)

    def doRollover(self) -> None:
        try:
            super().doRollover()
            self._rollover_cooldown_until = 0.0
        except OSError:
            # Rotation failed (Windows file lock, disk full, etc.).
            # Suppress retry storms for 60 s and reopen the stream so we
            # keep writing.  The lock is already held by emit().
            self._rollover_cooldown_until = time.monotonic() + 60.0
            if self.stream:
                try:
                    self.stream.close()
                except OSError:
                    pass
            self.stream = self._open()


def setup_logging() -> logging.Logger:
    """Configure the deskpricer logger with a rotating JSON file handler."""
    logger = logging.getLogger("deskpricer")
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

    file_handler = _SafeRotatingFileHandler(
        get_log_file(),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    return logger
