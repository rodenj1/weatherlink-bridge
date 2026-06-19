"""Logging configuration using structlog.

ADR 0004: structlog — JSON lines in production, colored console in development.
stdlib logging is routed through structlog so all log output (including from
third-party libraries) is structured.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(log_level: str, *, development: bool = False) -> None:
    """Configure structlog for the application.

    In development mode: colored console output with tracebacks.
    In production mode: JSON lines output.

    Args:
        log_level: Log level string (e.g. "INFO", "DEBUG").
        development: If True, use human-friendly console renderer.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if development:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # SECURITY: httpx/httpcore log the full request URL at INFO. Those URLs
    # carry credentials in their query strings (WeatherLink ``api-key``, the WU
    # ``PASSWORD``), so emitting them would leak secrets into stdout/pod logs.
    # Cap these loggers at WARNING unconditionally — even in development — so
    # request URLs are never logged regardless of the app log level.
    for noisy_logger in ("httpx", "httpcore"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
