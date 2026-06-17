"""Factory registry for weather data publishers.

ADR 0003: PublisherFactory mirrors the DestinationFactory registry pattern.
Builders are registered by publisher type name (e.g. "wunderground", "windy").
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

import structlog

from weatherlink_bridge.exceptions import ConfigurationError
from weatherlink_bridge.publishers.base import BasePublisher
from weatherlink_bridge.settings import AppSettings

PublisherBuilder = Callable[[AppSettings], BasePublisher]

_log = structlog.get_logger(__name__)


class PublisherFactory:
    """Registry that maps publisher type names to builder callables.

    All methods are class-level; the class is never instantiated.

    Usage::

        PublisherFactory.register("wunderground", WundergroundPublisher)
        publisher = PublisherFactory.create("wunderground", settings)
    """

    _builders: ClassVar[dict[str, PublisherBuilder]] = {}

    @classmethod
    def register(cls, publisher_type: str, builder: PublisherBuilder) -> None:
        """Register a builder for a publisher type.

        Args:
            publisher_type: Non-empty string identifier for the publisher.
            builder: Callable that accepts AppSettings and returns a BasePublisher.

        Raises:
            ValueError: If publisher_type is empty.
        """
        if not publisher_type:
            raise ValueError("publisher_type must be a non-empty string")
        cls._builders[publisher_type] = builder
        _log.debug("publisher_registered", publisher_type=publisher_type)

    @classmethod
    def unregister(cls, publisher_type: str) -> bool:
        """Remove a publisher type from the registry.

        Args:
            publisher_type: The type identifier to remove.

        Returns:
            True if it was registered and has been removed, False if not found.
        """
        if publisher_type in cls._builders:
            del cls._builders[publisher_type]
            _log.debug("publisher_unregistered", publisher_type=publisher_type)
            return True
        return False

    @classmethod
    def get_available_types(cls) -> list[str]:
        """Return all currently registered publisher type names."""
        return list(cls._builders.keys())

    @classmethod
    def is_registered(cls, publisher_type: str) -> bool:
        """Return True if publisher_type has a registered builder."""
        return publisher_type in cls._builders

    @classmethod
    def create(cls, publisher_type: str, settings: AppSettings) -> BasePublisher:
        """Instantiate a publisher by type.

        Args:
            publisher_type: The registered type identifier.
            settings: Application settings forwarded to the builder.

        Returns:
            A new BasePublisher instance.

        Raises:
            ConfigurationError: If publisher_type is not registered.
        """
        if publisher_type not in cls._builders:
            available = ", ".join(cls._builders) or "<none>"
            raise ConfigurationError(
                f"Unknown publisher type: {publisher_type!r}",
                details=f"Available types: {available}",
            )
        return cls._builders[publisher_type](settings)

    @classmethod
    def create_all(cls, settings: AppSettings) -> list[BasePublisher]:
        """Create all publishers whose enabled flag is True in settings.

        Checks ``settings.wunderground.enabled`` and ``settings.windy.enabled``.
        A publisher is only created if it is both enabled *and* registered.

        Args:
            settings: Application settings used to determine enabled publishers
                      and forwarded to each builder.

        Returns:
            List of instantiated publishers (may be empty).
        """
        publisher_map: dict[str, bool] = {
            "wunderground": settings.wunderground.enabled,
            "windy": settings.windy.enabled,
        }
        publishers: list[BasePublisher] = []
        for pub_type, enabled in publisher_map.items():
            if enabled and cls.is_registered(pub_type):
                publishers.append(cls.create(pub_type, settings))
                _log.info("publisher_created", publisher_type=pub_type)
        return publishers
