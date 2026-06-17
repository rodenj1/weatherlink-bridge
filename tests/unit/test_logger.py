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
