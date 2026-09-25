"""Smoke test to verify imports, package structure, and logging setup."""

import json
import logging
import pytest

from app import __version__
from app.logging import JSONFormatter, TextFormatter, get_logger, setup_logging


def test_package_version() -> None:
    """Verify application version is defined."""
    assert __version__ == "0.1.0"


def test_logging_setup_text(caplog: pytest.LogCaptureFixture) -> None:
    """Verify text logging initialization."""
    setup_logging(level="DEBUG", json_format=False)
    logger = get_logger("test.smoke")
    with caplog.at_level(logging.INFO):
        logger.info("Test message for smoke verification")
    assert "Test message for smoke verification" in caplog.text


def test_json_formatter_outputs_valid_json() -> None:
    """Verify JSON log formatter includes timestamp and message."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Structured event",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Structured event"
    assert "timestamp" in parsed
