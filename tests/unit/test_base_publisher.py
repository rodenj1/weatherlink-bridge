"""Tests for BasePublisher ABC."""

from __future__ import annotations

import pytest


class ConcretePublisher:
    """Minimal concrete publisher for testing base class behaviour."""

    name = "concrete"

    async def publish(self, observation: object) -> bool:
        return True

    async def close(self) -> None:
        from weatherlink_bridge.publishers.base import BasePublisher

        # Delegate to the real base-class close() so we cover that line.
        await BasePublisher.close(self)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_base_publisher_close_is_noop() -> None:
    """BasePublisher.close() runs without error and returns None."""
    from weatherlink_bridge.publishers.base import BasePublisher

    class MinimalPublisher(BasePublisher):
        name = "minimal"

        async def publish(self, observation: object) -> bool:
            return True

    pub = MinimalPublisher()
    result = await pub.close()
    assert result is None


@pytest.mark.asyncio
async def test_concrete_publisher_publish_returns_bool() -> None:
    """A concrete publisher can publish and return True."""
    from weatherlink_bridge.publishers.base import BasePublisher

    class TruePublisher(BasePublisher):
        name = "true"

        async def publish(self, observation: object) -> bool:
            return True

    pub = TruePublisher()
    result = await pub.publish(object())
    assert result is True
