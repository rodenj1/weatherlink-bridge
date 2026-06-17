"""Tests for the WeatherLinkBridgeError exception hierarchy."""

import pytest

from weatherlink_bridge.exceptions import (
    CollectorError,
    ConfigurationError,
    MappingError,
    PublisherError,
    WeatherLinkBridgeError,
)


def test_base_error_message_only() -> None:
    err = WeatherLinkBridgeError("something went wrong")
    assert err.message == "something went wrong"
    assert err.details is None
    assert str(err) == "something went wrong"


def test_base_error_with_details() -> None:
    err = WeatherLinkBridgeError("something went wrong", details="extra info")
    assert err.details == "extra info"
    assert "something went wrong" in str(err)
    assert "extra info" in str(err)


def test_subclasses_inherit_base() -> None:
    for cls in (ConfigurationError, CollectorError, PublisherError, MappingError):
        err = cls("test error")
        assert isinstance(err, WeatherLinkBridgeError)
        assert isinstance(err, Exception)
        assert err.message == "test error"


def test_configuration_error_with_details() -> None:
    err = ConfigurationError("bad config", details="missing field")
    assert isinstance(err, WeatherLinkBridgeError)
    assert err.details == "missing field"


@pytest.mark.parametrize(
    "cls", [ConfigurationError, CollectorError, PublisherError, MappingError]
)
def test_subclass_is_catchable_as_base(cls: type) -> None:
    with pytest.raises(WeatherLinkBridgeError):
        raise cls("test")
