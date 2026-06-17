"""Abstract base class for weather data publishers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, ClassVar


class PublishResult(Enum):
    """Result of a single publisher.publish() call.

    Distinguishes between three outcomes so the instrumentation layer can
    record the correct Prometheus status label:

    * ``SUCCESS`` — observation was accepted by the remote service.
    * ``FAILURE`` — observation was rejected or a non-retriable error occurred.
    * ``SKIPPED`` — publisher chose not to attempt the request (e.g. 429 backoff
      window still active per ADR 0007).
    """

    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


class BasePublisher(ABC):
    """Abstract base for all weather data publishers.

    Subclasses must set the class-level ``name`` attribute and implement
    ``publish()``. The ``close()`` method is optional — the default no-op
    is suitable for publishers with no persistent connection.
    """

    name: ClassVar[str]

    @abstractmethod
    async def publish(self, observation: Any) -> PublishResult:
        """Publish a weather observation to the target service.

        Args:
            observation: The canonical weather observation to publish.
                         Type will be ``WeatherObservation`` once Phase 1
                         implements that model.

        Returns:
            A ``PublishResult`` indicating whether the observation was
            accepted, rejected, or skipped (backoff).
        """
        ...  # pragma: no cover

    async def close(self) -> None:
        """Release any resources held by this publisher.

        Default implementation is a no-op. Override for publishers
        that hold persistent HTTP sessions or connections.
        """
        return  # Intentional no-op default; subclasses override as needed.
