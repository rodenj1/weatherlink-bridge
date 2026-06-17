"""Abstract base class for weather data publishers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar


class BasePublisher(ABC):
    """Abstract base for all weather data publishers.

    Subclasses must set the class-level ``name`` attribute and implement
    ``publish()``. The ``close()`` method is optional — the default no-op
    is suitable for publishers with no persistent connection.
    """

    name: ClassVar[str]

    @abstractmethod
    async def publish(self, observation: Any) -> bool:
        """Publish a weather observation to the target service.

        Args:
            observation: The canonical weather observation to publish.
                         Type will be ``WeatherObservation`` once Phase 1
                         implements that model.

        Returns:
            True if published successfully, False otherwise.
        """
        ...  # pragma: no cover

    async def close(self) -> None:
        """Release any resources held by this publisher.

        Default implementation is a no-op. Override for publishers
        that hold persistent HTTP sessions or connections.
        """
        return  # Intentional no-op default; subclasses override as needed.
