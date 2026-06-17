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


# ---------------------------------------------------------------------------
# BUG B regression: disabled publishers must not be built
# ---------------------------------------------------------------------------


def test_create_all_both_disabled_builds_zero_publishers() -> None:
    """create_all with both publishers disabled returns [] and never calls any builder.

    Regression for BUG B: disabled publishers must not be constructed (and
    therefore cannot trigger any side-effects such as FileNotFoundError when
    loading sensor maps in a container where config_dir is wrong).
    """
    wunderground_calls: list[object] = []
    windy_calls: list[object] = []

    def _tracking_wu_builder(settings: AppSettings) -> BasePublisher:
        wunderground_calls.append(settings)
        return FakePublisher()

    def _tracking_windy_builder(settings: AppSettings) -> BasePublisher:
        windy_calls.append(settings)
        return FakePublisher()

    PublisherFactory.register("wunderground", _tracking_wu_builder)
    PublisherFactory.register("windy", _tracking_windy_builder)

    settings = _make_settings_mock(wunderground_enabled=False, windy_enabled=False)
    result = PublisherFactory.create_all(settings)

    assert result == []
    # Neither builder must have been called
    assert wunderground_calls == [], (
        "wunderground builder was called despite being disabled"
    )
    assert windy_calls == [], "windy builder was called despite being disabled"


def test_create_all_only_wunderground_enabled_builds_exactly_one() -> None:
    """create_all with only wunderground enabled builds exactly [wunderground].

    Regression for BUG B: the windy builder must not be called when windy is disabled.
    """
    windy_calls: list[object] = []

    def _tracking_windy_builder(settings: AppSettings) -> BasePublisher:
        windy_calls.append(settings)
        return FakePublisher()

    PublisherFactory.register("wunderground", make_fake_builder())
    PublisherFactory.register("windy", _tracking_windy_builder)

    settings = _make_settings_mock(wunderground_enabled=True, windy_enabled=False)
    result = PublisherFactory.create_all(settings)

    assert len(result) == 1
    assert isinstance(result[0], FakePublisher)
    assert windy_calls == [], "windy builder was called despite windy being disabled"


def test_create_all_only_windy_enabled_builds_exactly_one() -> None:
    """create_all with only windy enabled builds exactly [windy]."""
    wunderground_calls: list[object] = []

    def _tracking_wu_builder(settings: AppSettings) -> BasePublisher:
        wunderground_calls.append(settings)
        return FakePublisher()

    PublisherFactory.register("wunderground", _tracking_wu_builder)
    PublisherFactory.register("windy", make_fake_builder())

    settings = _make_settings_mock(wunderground_enabled=False, windy_enabled=True)
    result = PublisherFactory.create_all(settings)

    assert len(result) == 1
    assert isinstance(result[0], FakePublisher)
    assert wunderground_calls == [], (
        "wunderground builder was called despite being disabled"
    )
