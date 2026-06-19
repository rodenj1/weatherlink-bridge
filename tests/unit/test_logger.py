"""Tests for the configure_logging function."""

import logging

import structlog


def test_configure_logging_production_mode() -> None:
    """configure_logging runs without error in production (JSON) mode."""
    from weatherlink_bridge.logger import configure_logging

    configure_logging("INFO", development=False)
    root = logging.getLogger()
    assert root.level == logging.INFO


def test_configure_logging_development_mode() -> None:
    """configure_logging runs without error in development (console) mode."""
    from weatherlink_bridge.logger import configure_logging

    configure_logging("DEBUG", development=True)
    root = logging.getLogger()
    assert root.level == logging.DEBUG


def test_configure_logging_sets_structlog_config() -> None:
    """configure_logging sets a structlog configuration."""
    from weatherlink_bridge.logger import configure_logging

    configure_logging("WARNING")
    config = structlog.get_config()
    assert config["logger_factory"] is not None


def test_httpx_loggers_capped_at_warning_to_prevent_url_leak() -> None:
    """httpx/httpcore are forced to WARNING so request URLs (with secrets in the
    query string) are never logged — even when the app runs at DEBUG."""
    from weatherlink_bridge.logger import configure_logging

    configure_logging("DEBUG", development=True)
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    # An INFO record on httpx (where the URL leak lived) must be suppressed.
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
