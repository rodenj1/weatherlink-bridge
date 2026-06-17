"""Exception hierarchy for WeatherLink Bridge.

All custom exceptions inherit from WeatherLinkBridgeError, which stores
a human-readable message and an optional details string.
"""

from __future__ import annotations


class WeatherLinkBridgeError(Exception):
    """Base exception for all WeatherLink Bridge errors.

    Attributes:
        message: Short description of the error.
        details: Optional additional context.
        full_message: Combined message and details string.
    """

    def __init__(self, message: str, *, details: str | None = None) -> None:
        self.message = message
        self.details = details
        self.full_message = f"{message}: {details}" if details else message
        super().__init__(self.full_message)


class ConfigurationError(WeatherLinkBridgeError):
    """Raised when application configuration is invalid or incomplete."""


class CollectorError(WeatherLinkBridgeError):
    """Raised when a weather data collector encounters an unrecoverable error."""


class PublisherError(WeatherLinkBridgeError):
    """Raised when a publisher fails to deliver an observation."""


class MappingError(WeatherLinkBridgeError):
    """Raised when a sensor-field mapping cannot be applied."""
