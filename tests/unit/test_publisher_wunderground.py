"""Tests for WundergroundPublisher."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from weatherlink_bridge.exceptions import PublisherError
from weatherlink_bridge.mapping.mapper import FieldMapper
from weatherlink_bridge.models.observation import WeatherObservation
from weatherlink_bridge.publishers.factory import PublisherFactory
from weatherlink_bridge.publishers.wunderground import WundergroundPublisher
from weatherlink_bridge.settings import WundergroundSettings

_WU_URL = (
    "https://weatherstation.wunderground.com/weatherstation/updateweatherstation.php"
)

_WUNDERGROUND_MAP_PATH = (
    Path(__file__).parents[2] / "config" / "sensor_maps" / "wunderground.yaml"
)

_FIXED_TIMESTAMP = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)


def _obs(**kwargs: object) -> WeatherObservation:
    """Minimal WeatherObservation with overridable fields."""
    return WeatherObservation(
        timestamp=_FIXED_TIMESTAMP,
        station_id=12345,
        temp_out_f=72.0,
        **kwargs,  # type: ignore[arg-type]
    )


def _make_settings(
    station_id: str = "KTESTSTA1",
    api_key: str = "testpassword",
) -> WundergroundSettings:
    return WundergroundSettings(
        enabled=True,
        station_id=station_id,
        api_key=api_key,
    )


def _make_publisher(client: httpx.AsyncClient) -> WundergroundPublisher:
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    return WundergroundPublisher(_make_settings(), client, mapper)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@respx.mock
async def test_publish_success() -> None:
    """Returns True when WU responds with body 'success'."""
    respx.get(_WU_URL).mock(return_value=httpx.Response(200, text="success"))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    assert result is True


@respx.mock
async def test_publish_https_url() -> None:
    """Request URL uses HTTPS (defect #1 fix)."""
    route = respx.get(_WU_URL).mock(return_value=httpx.Response(200, text="success"))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        await publisher.publish(_obs())

    request = route.calls[0].request
    assert str(request.url).startswith("https://")


@respx.mock
async def test_publish_includes_id_and_password() -> None:
    """Request query params include ID and PASSWORD."""
    route = respx.get(_WU_URL).mock(return_value=httpx.Response(200, text="success"))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        await publisher.publish(_obs())

    request = route.calls[0].request
    query = request.url.query.decode()
    assert "ID=KTESTSTA1" in query
    assert "PASSWORD=testpassword" in query


# ---------------------------------------------------------------------------
# Failure cases
# ---------------------------------------------------------------------------


@respx.mock
async def test_publish_body_invalidpassword_returns_false() -> None:
    """HTTP 200 with non-'success' body returns False (defect #2 proof)."""
    respx.get(_WU_URL).mock(
        return_value=httpx.Response(200, text="INVALIDPASSWORDID|Reason: bad pw")
    )

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    assert result is False


@respx.mock
async def test_publish_exact_invalidpassword_body_returns_false() -> None:
    """Exact WU auth-failure body 'INVALIDPASSWORDID|Password and/or id are incorrect'.

    Adversarial check: the exact error string WU returns for bad credentials
    must yield False, not True — verifies body-based success detection (defect #2).
    """
    respx.get(_WU_URL).mock(
        return_value=httpx.Response(
            200, text="INVALIDPASSWORDID|Password and/or id are incorrect"
        )
    )

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    assert result is False


@respx.mock
async def test_publish_success_uppercase_with_trailing_whitespace() -> None:
    """Body 'SUCCESS\\n' (uppercase + trailing whitespace) → publish returns True.

    The implementation strips whitespace and lowercases the body before
    comparison.  This test adversarially verifies both normalisations.
    """
    respx.get(_WU_URL).mock(return_value=httpx.Response(200, text="SUCCESS\n"))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    assert result is True


@respx.mock
async def test_publish_http_error_raises_publisher_error() -> None:
    """HTTP 500 raises PublisherError."""
    respx.get(_WU_URL).mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        with pytest.raises(PublisherError):
            await publisher.publish(_obs())


@respx.mock
async def test_publish_network_error_raises_publisher_error() -> None:
    """Network failure raises PublisherError."""
    respx.get(_WU_URL).mock(side_effect=httpx.ConnectError("refused"))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        with pytest.raises(PublisherError):
            await publisher.publish(_obs())


# ---------------------------------------------------------------------------
# Factory registration
# ---------------------------------------------------------------------------


def test_factory_registers_wunderground() -> None:
    """Importing weatherlink_bridge.publishers triggers 'wunderground' registration."""
    import weatherlink_bridge.publishers  # noqa: F401 — triggers __init__ import

    assert PublisherFactory.is_registered("wunderground")


# ---------------------------------------------------------------------------
# Zero-value observation (defect #6 check via publisher path)
# ---------------------------------------------------------------------------


@respx.mock
async def test_publish_zero_rain_included_in_params() -> None:
    """rain_60min_in=0.0 appears as rainin=0.0 in request (defect #6)."""
    route = respx.get(_WU_URL).mock(return_value=httpx.Response(200, text="success"))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        await publisher.publish(_obs(rain_60min_in=0.0))

    query = route.calls[0].request.url.query.decode()
    assert "rainin=0.0" in query


async def test_close_closes_client() -> None:
    """close() calls aclose() on the underlying httpx client."""
    from unittest.mock import AsyncMock

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    publisher = WundergroundPublisher(_make_settings(), mock_client, mapper)
    await publisher.close()
    mock_client.aclose.assert_awaited_once()


def test_factory_builder_creates_publisher() -> None:
    """_build_wunderground creates a WundergroundPublisher via factory."""
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.wunderground = WundergroundSettings(
        enabled=True,
        station_id="KTEST1",
        api_key="pw",
    )
    from weatherlink_bridge.publishers.wunderground import _build_wunderground

    publisher = _build_wunderground(mock_settings)
    assert isinstance(publisher, WundergroundPublisher)
