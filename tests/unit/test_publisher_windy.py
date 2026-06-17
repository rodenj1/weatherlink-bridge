"""Tests for WindyPublisher."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from weatherlink_bridge.mapping.mapper import FieldMapper
from weatherlink_bridge.models.observation import WeatherObservation
from weatherlink_bridge.publishers.factory import PublisherFactory
from weatherlink_bridge.publishers.windy import WindyPublisher
from weatherlink_bridge.settings import WindySettings

_WINDY_URL = "https://stations.windy.com/api/v2/observation/update"
_WINDY_MAP_PATH = Path(__file__).parents[2] / "config" / "sensor_maps" / "windy.yaml"

_FIXED_TIMESTAMP = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)


def _obs(**kwargs: object) -> WeatherObservation:
    """Minimal WeatherObservation with representative defaults; kwargs override."""
    defaults: dict[str, object] = {
        "temp_out_f": 67.6,
        "wind_speed_mph": 10.0,
        "pressure_sea_level_inHg": 29.92,
    }
    defaults.update(kwargs)
    return WeatherObservation(
        timestamp=_FIXED_TIMESTAMP,
        station_id=12345,
        **defaults,  # type: ignore[arg-type]
    )


def _make_settings(
    station_id: str = "YZjgOxm",
    api_key: str = "testpassword",
) -> WindySettings:
    return WindySettings(
        enabled=True,
        station_id=station_id,
        api_key=api_key,
    )


def _make_publisher(client: httpx.AsyncClient) -> WindyPublisher:
    mapper = FieldMapper(_WINDY_MAP_PATH)
    return WindyPublisher(_make_settings(), client, mapper)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@respx.mock
async def test_publish_success_returns_true() -> None:
    """Returns True when Windy responds with HTTP 200."""
    respx.get(_WINDY_URL).mock(return_value=httpx.Response(200, text=""))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    assert result is True


@respx.mock
async def test_publish_uses_https_v2_endpoint() -> None:
    """Request URL is the v2 HTTPS endpoint."""
    route = respx.get(_WINDY_URL).mock(return_value=httpx.Response(200, text=""))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        await publisher.publish(_obs())

    request = route.calls[0].request
    assert str(request.url).startswith("https://stations.windy.com/api/v2/")


@respx.mock
async def test_publish_includes_id_as_string() -> None:
    """id query param is present and is the station id string."""
    route = respx.get(_WINDY_URL).mock(return_value=httpx.Response(200, text=""))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        await publisher.publish(_obs())

    query = route.calls[0].request.url.query.decode()
    assert "id=YZjgOxm" in query


@respx.mock
async def test_publish_includes_password() -> None:
    """PASSWORD query param is present."""
    route = respx.get(_WINDY_URL).mock(return_value=httpx.Response(200, text=""))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        await publisher.publish(_obs())

    query = route.calls[0].request.url.query.decode()
    assert "PASSWORD=testpassword" in query


@respx.mock
async def test_publish_time_ends_with_z() -> None:
    """time query param is RFC-3339 with trailing Z."""
    route = respx.get(_WINDY_URL).mock(return_value=httpx.Response(200, text=""))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        await publisher.publish(_obs())

    query = route.calls[0].request.url.query.decode()
    assert "time=" in query
    # Find the time param value
    for part in query.split("&"):
        if part.startswith("time="):
            assert part.endswith("Z"), f"time param does not end with Z: {part}"


@respx.mock
async def test_publish_sends_metric_temp() -> None:
    """temp param is in Celsius (metric), not Fahrenheit."""
    route = respx.get(_WINDY_URL).mock(return_value=httpx.Response(200, text=""))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        await publisher.publish(_obs(temp_out_f=32.0))  # 32°F = 0°C

    query = route.calls[0].request.url.query.decode()
    # temp=0.0 (or -0.0)
    assert "temp=0.0" in query or "temp=-0.0" in query


# ---------------------------------------------------------------------------
# 429 backoff (ADR 0007)
# ---------------------------------------------------------------------------


@respx.mock
async def test_429_returns_false_and_sets_skip_until() -> None:
    """HTTP 429 with retry_after body → returns False and sets _skip_until."""
    future = datetime(2099, 1, 1, 0, 0, 0, tzinfo=UTC)
    body = json.dumps({"retry_after": future.strftime("%Y-%m-%dT%H:%M:%S.000Z")})
    respx.get(_WINDY_URL).mock(
        return_value=httpx.Response(
            429, text=body, headers={"content-type": "application/json"}
        )
    )

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    assert result is False
    assert publisher._skip_until is not None
    assert publisher._skip_until >= future - timedelta(seconds=1)


@respx.mock
async def test_429_subsequent_call_skipped() -> None:
    """After a 429, subsequent publish while in backoff window makes NO new HTTP request."""
    future = datetime(2099, 1, 1, 0, 0, 0, tzinfo=UTC)
    body = json.dumps({"retry_after": future.strftime("%Y-%m-%dT%H:%M:%S.000Z")})
    route = respx.get(_WINDY_URL).mock(
        return_value=httpx.Response(
            429, text=body, headers={"content-type": "application/json"}
        )
    )

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        # First call → 429
        await publisher.publish(_obs())
        call_count_after_first = route.call_count
        # Second call → should be skipped (backoff active)
        result = await publisher.publish(_obs())

    assert result is False
    # No additional HTTP request should have been made
    assert route.call_count == call_count_after_first


@respx.mock
async def test_429_no_retry_after_defaults_to_5min() -> None:
    """429 with missing retry_after → _skip_until ≈ now + 5 minutes."""
    body = json.dumps({})
    respx.get(_WINDY_URL).mock(
        return_value=httpx.Response(
            429, text=body, headers={"content-type": "application/json"}
        )
    )

    before = datetime.now(UTC)

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    after = datetime.now(UTC)
    assert result is False
    assert publisher._skip_until is not None
    # Should be approximately now + 5 minutes
    expected_min = before + timedelta(minutes=5) - timedelta(seconds=2)
    expected_max = after + timedelta(minutes=5) + timedelta(seconds=2)
    assert expected_min <= publisher._skip_until <= expected_max


@respx.mock
async def test_429_invalid_retry_after_defaults_to_5min() -> None:
    """429 with invalid retry_after string → _skip_until ≈ now + 5 minutes."""
    body = json.dumps({"retry_after": "not-a-date"})
    respx.get(_WINDY_URL).mock(
        return_value=httpx.Response(
            429, text=body, headers={"content-type": "application/json"}
        )
    )

    before = datetime.now(UTC)

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    after = datetime.now(UTC)
    assert result is False
    assert publisher._skip_until is not None
    expected_min = before + timedelta(minutes=5) - timedelta(seconds=2)
    expected_max = after + timedelta(minutes=5) + timedelta(seconds=2)
    assert expected_min <= publisher._skip_until <= expected_max


@respx.mock
async def test_429_naive_datetime_retry_after_defaults_to_5min() -> None:
    """429 with naive (no-tz) retry_after → fallback to now + 5 min, not host-tz 2099.

    A naive ISO-8601 string like "2099-01-01T00:00:00" is not valid RFC-3339
    (timezone is required).  The parser must reject it and use the fallback
    instead of silently localising it via the host's local timezone.

    Regression test for BR-002.
    """
    body = json.dumps({"retry_after": "2099-01-01T00:00:00"})
    respx.get(_WINDY_URL).mock(
        return_value=httpx.Response(
            429, text=body, headers={"content-type": "application/json"}
        )
    )

    before = datetime.now(UTC)

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    after = datetime.now(UTC)
    assert result is False
    assert publisher._skip_until is not None
    # Must be tz-aware — no accidental naive datetime leaking through.
    assert publisher._skip_until.tzinfo is not None
    # Must be the fallback (≈ now + 5 min), NOT a 2099 host-localised value.
    expected_min = before + timedelta(minutes=5) - timedelta(seconds=2)
    expected_max = after + timedelta(minutes=5) + timedelta(seconds=2)
    assert expected_min <= publisher._skip_until <= expected_max


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@respx.mock
async def test_publish_http_500_raises_publisher_error() -> None:
    """HTTP 500 raises PublisherError."""
    from weatherlink_bridge.exceptions import PublisherError

    respx.get(_WINDY_URL).mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        with pytest.raises(PublisherError):
            await publisher.publish(_obs())


@respx.mock
async def test_publish_network_error_raises_publisher_error() -> None:
    """Network failure raises PublisherError."""
    from weatherlink_bridge.exceptions import PublisherError

    respx.get(_WINDY_URL).mock(side_effect=httpx.ConnectError("refused"))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        with pytest.raises(PublisherError):
            await publisher.publish(_obs())


# ---------------------------------------------------------------------------
# Disabled path
# ---------------------------------------------------------------------------


def test_windy_disabled_not_in_create_all() -> None:
    """WINDY__ENABLED=false → no WindyPublisher created by create_all."""
    from unittest.mock import MagicMock

    import weatherlink_bridge.publishers  # noqa: F401 — triggers registration

    mock_settings = MagicMock()
    mock_settings.wunderground.enabled = False
    mock_settings.windy.enabled = False
    publishers = PublisherFactory.create_all(mock_settings)  # type: ignore[arg-type]
    names = [p.name for p in publishers]
    assert "windy" not in names


# ---------------------------------------------------------------------------
# Factory registration
# ---------------------------------------------------------------------------


def test_factory_registers_windy() -> None:
    """Importing weatherlink_bridge.publishers triggers 'windy' registration."""
    import weatherlink_bridge.publishers  # noqa: F401 — triggers __init__ import

    assert PublisherFactory.is_registered("windy")


def test_factory_builder_creates_windy_publisher() -> None:
    """_build_windy creates a WindyPublisher via factory."""
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.windy = WindySettings(
        enabled=True,
        station_id="YZjgOxm",
        api_key="testpw",
    )
    from weatherlink_bridge.publishers.windy import _build_windy

    publisher = _build_windy(mock_settings)
    assert isinstance(publisher, WindyPublisher)


async def test_close_closes_client() -> None:
    """close() calls aclose() on the underlying httpx client."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mapper = FieldMapper(_WINDY_MAP_PATH)
    publisher = WindyPublisher(_make_settings(), mock_client, mapper)
    await publisher.close()
    mock_client.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# 429 backoff expiry and RFC-3339 +00:00 format (adversarial hardening)
# ---------------------------------------------------------------------------


@respx.mock
async def test_429_backoff_expired_resumes_publishing() -> None:
    """After _skip_until passes, the next publish() makes a real HTTP request.

    This tests the transition OUT of backoff: manually set _skip_until to a
    past datetime and assert the endpoint is called again.
    """
    route = respx.get(_WINDY_URL).mock(return_value=httpx.Response(200, text=""))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        # Simulate a backoff window that has ALREADY expired
        publisher._skip_until = datetime(2000, 1, 1, 0, 0, 0, tzinfo=UTC)

        result = await publisher.publish(_obs())

    assert result is True
    # The expired backoff must NOT have blocked the request
    assert route.call_count == 1


@respx.mock
async def test_429_retry_after_offset_timezone_format() -> None:
    """429 with retry_after in +00:00 timezone form (not trailing Z) is parsed correctly.

    RFC-3339 allows both '...Z' and '...+00:00'. The parser must handle either.
    """
    future = datetime(2099, 6, 1, 12, 0, 0, tzinfo=UTC)
    # Use +00:00 format instead of Z
    retry_after_str = future.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    body = json.dumps({"retry_after": retry_after_str})
    respx.get(_WINDY_URL).mock(
        return_value=httpx.Response(
            429, text=body, headers={"content-type": "application/json"}
        )
    )

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    assert result is False
    assert publisher._skip_until is not None
    # Must be tz-aware (no naive/aware comparison error in a subsequent publish)
    assert publisher._skip_until.tzinfo is not None
    # Must be close to the future datetime in the response (within 60 seconds)
    assert abs((publisher._skip_until - future).total_seconds()) < 60
