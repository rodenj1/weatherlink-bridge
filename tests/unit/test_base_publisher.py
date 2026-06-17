"""Tests for BasePublisher ABC and PublishResult enum."""

from __future__ import annotations

import pytest

from weatherlink_bridge.publishers.base import PublishResult


class ConcretePublisher:
    """Minimal concrete publisher for testing base class behaviour."""

    name = "concrete"

    async def publish(self, observation: object) -> PublishResult:
        return PublishResult.SUCCESS

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

        async def publish(self, observation: object) -> PublishResult:
            return PublishResult.SUCCESS

    pub = MinimalPublisher()
    result = await pub.close()
    assert result is None


@pytest.mark.asyncio
async def test_concrete_publisher_publish_returns_success() -> None:
    """A concrete publisher can publish and return PublishResult.SUCCESS."""
    from weatherlink_bridge.publishers.base import BasePublisher

    class TruePublisher(BasePublisher):
        name = "true"

        async def publish(self, observation: object) -> PublishResult:
            return PublishResult.SUCCESS

    pub = TruePublisher()
    result = await pub.publish(object())
    assert result == PublishResult.SUCCESS


def test_publish_result_values() -> None:
    """PublishResult enum has the expected string values."""
    assert PublishResult.SUCCESS.value == "success"
    assert PublishResult.FAILURE.value == "failure"
    assert PublishResult.SKIPPED.value == "skipped"
