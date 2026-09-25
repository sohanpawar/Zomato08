"""Structured Logging Configuration.

Provides unified logging with ISO UTC timestamps, contextual metadata (e.g., request_id),
and consistent formatting across development and production environments.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON lines for structured log ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include contextual fields if present
        if hasattr(record, "request_id"):
            log_payload["request_id"] = record.request_id

        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_payload.update(record.extra_data)

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable formatter with UTC timestamps for local development."""

    def format(self, record: logging.LogRecord) -> str:
        utc_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        req_id = f" [{record.request_id}]" if hasattr(record, "request_id") else ""
        base = f"{utc_time} | {record.levelname:<8} | {record.name}{req_id} - {record.getMessage()}"
        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"
        return base


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Initialize root and application loggers.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: If True, formats logs as JSON lines.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Clear existing handlers to prevent duplicate lines
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level.upper())

    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(TextFormatter())

    root_logger.addHandler(handler)

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger instance for a module."""
    return logging.getLogger(name)
