"""Tests for PublisherFactory registry pattern."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from weatherlink_bridge.exceptions import ConfigurationError
from weatherlink_bridge.publishers.base import BasePublisher
from weatherlink_bridge.publishers.factory import PublisherBuilder, PublisherFactory
from weatherlink_bridge.settings import AppSettings

if TYPE_CHECKING:
    from weatherlink_bridge.models.observation import WeatherObservation


class FakePublisher(BasePublisher):
    name = "fake"

    async def publish(self, observation: WeatherObservation) -> bool:
        return True


def make_fake_builder() -> PublisherBuilder:
    def builder(settings: AppSettings) -> BasePublisher:
        return FakePublisher()

    return builder


def _make_settings_mock(
    *, wunderground_enabled: bool, windy_enabled: bool
) -> AppSettings:
    """Create a MagicMock that quacks like AppSettings for create_all tests."""
    mock = MagicMock()
    mock.wunderground.enabled = wunderground_enabled
    mock.windy.enabled = windy_enabled
    return mock  # type: ignore[return-value]


@pytest.fixture(autouse=True)
def clean_registry() -> Generator[None, None, None]:
    """Ensure each test starts with a clean factory registry."""
    original = dict(PublisherFactory._builders)
    yield
    PublisherFactory._builders.clear()
    PublisherFactory._builders.update(original)


def test_register_and_is_registered() -> None:
    PublisherFactory.register("fake", make_fake_builder())
    assert PublisherFactory.is_registered("fake")


def test_get_available_types_reflects_registration() -> None:
    PublisherFactory.register("fake", make_fake_builder())
    assert "fake" in PublisherFactory.get_available_types()


def test_unregister_removes_type() -> None:
    PublisherFactory.register("fake", make_fake_builder())
    result = PublisherFactory.unregister("fake")
    assert result is True
    assert not PublisherFactory.is_registered("fake")


def test_unregister_nonexistent_returns_false() -> None:
    result = PublisherFactory.unregister("nonexistent")
    assert result is False


def test_register_empty_name_raises() -> None:
    with pytest.raises(ValueError):
        PublisherFactory.register("", make_fake_builder())


def test_create_unknown_type_raises_configuration_error() -> None:
    settings = MagicMock()
    with pytest.raises(ConfigurationError):
        PublisherFactory.create("unknown_type", settings)  # type: ignore[arg-type]


def test_create_returns_publisher_instance() -> None:
    PublisherFactory.register("fake", make_fake_builder())
    settings = MagicMock()
    publisher = PublisherFactory.create("fake", settings)  # type: ignore[arg-type]
    assert isinstance(publisher, FakePublisher)


def test_create_all_returns_registered_enabled_publishers() -> None:
    PublisherFactory.register("wunderground", make_fake_builder())
    PublisherFactory.register("windy", make_fake_builder())
    settings = _make_settings_mock(wunderground_enabled=True, windy_enabled=True)
    publishers = PublisherFactory.create_all(settings)
    assert len(publishers) == 2


def test_create_all_skips_disabled_publishers() -> None:
    PublisherFactory.register("wunderground", make_fake_builder())
    PublisherFactory.register("windy", make_fake_builder())
    settings = _make_settings_mock(wunderground_enabled=False, windy_enabled=False)
    publishers = PublisherFactory.create_all(settings)
    assert publishers == []
