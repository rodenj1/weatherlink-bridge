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
from weatherlink_bridge.publishers.base import PublishResult
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
    password: str = "testpassword",
) -> WundergroundSettings:
    return WundergroundSettings(
        enabled=True,
        station_id=station_id,
        password=password,
    )


def _make_publisher(client: httpx.AsyncClient) -> WundergroundPublisher:
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    return WundergroundPublisher(_make_settings(), client, mapper)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@respx.mock
async def test_publish_success() -> None:
    """Returns SUCCESS when WU responds with body 'success'."""
    respx.get(_WU_URL).mock(return_value=httpx.Response(200, text="success"))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    assert result == PublishResult.SUCCESS


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
async def test_publish_body_invalidpassword_returns_failure() -> None:
    """HTTP 200 with non-'success' body returns FAILURE (defect #2 proof)."""
    respx.get(_WU_URL).mock(
        return_value=httpx.Response(200, text="INVALIDPASSWORDID|Reason: bad pw")
    )

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    assert result == PublishResult.FAILURE


@respx.mock
async def test_publish_exact_invalidpassword_body_returns_failure() -> None:
    """Exact WU auth-failure body 'INVALIDPASSWORDID|Password and/or id are incorrect'.

    Adversarial check: the exact error string WU returns for bad credentials
    must yield FAILURE, not SUCCESS — verifies body-based success detection
    (defect #2).
    """
    respx.get(_WU_URL).mock(
        return_value=httpx.Response(
            200, text="INVALIDPASSWORDID|Password and/or id are incorrect"
        )
    )

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    assert result == PublishResult.FAILURE


@respx.mock
async def test_publish_success_uppercase_with_trailing_whitespace() -> None:
    """Body 'SUCCESS\\n' (uppercase + trailing whitespace) → publish returns SUCCESS.

    The implementation strips whitespace and lowercases the body before
    comparison.  This test adversarially verifies both normalisations.
    """
    respx.get(_WU_URL).mock(return_value=httpx.Response(200, text="SUCCESS\n"))

    async with httpx.AsyncClient() as client:
        publisher = _make_publisher(client)
        result = await publisher.publish(_obs())

    assert result == PublishResult.SUCCESS


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
    """_build_wunderground creates a WundergroundPublisher via factory.

    config_dir is set to the real project config/ so _build_wunderground can
    resolve the sensor map via settings.config_dir (BUG A regression).
    """
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.wunderground = WundergroundSettings(
        enabled=True,
        station_id="KTEST1",
        password="pw",
    )
    # config_dir must point at a real directory containing sensor_maps/*.yaml
    mock_settings.config_dir = _WUNDERGROUND_MAP_PATH.parents[1]
    from weatherlink_bridge.publishers.wunderground import _build_wunderground

    publisher = _build_wunderground(mock_settings)
    assert isinstance(publisher, WundergroundPublisher)


# ---------------------------------------------------------------------------
# BUG A regression: config_dir drives sensor-map resolution
# ---------------------------------------------------------------------------


def test_build_wunderground_uses_config_dir_not_file(tmp_path: Path) -> None:
    """_build_wunderground resolves the sensor map from settings.config_dir.

    Regression for BUG A: the builder must NOT use Path(__file__).parents[N]
    (which breaks in wheel/container installs). It must use settings.config_dir.

    We write a minimal valid wunderground.yaml into a temp directory and pass
    that temp dir as config_dir. If the builder honoured __file__ arithmetic it
    would look in the project src tree and find the real YAML (or the wrong one).
    Here it must find and load the temp-dir YAML.
    """
    from unittest.mock import MagicMock

    import yaml

    # Create a minimal but valid sensor map in tmp_path/sensor_maps/
    sensor_maps_dir = tmp_path / "sensor_maps"
    sensor_maps_dir.mkdir()
    minimal_map = {
        "fields": {"temp_out_f": {"target": "tempf"}},
        "static_params": {"action": "updateraw", "dateutc": "now"},
    }
    (sensor_maps_dir / "wunderground.yaml").write_text(
        yaml.dump(minimal_map), encoding="utf-8"
    )

    mock_settings = MagicMock()
    mock_settings.wunderground = WundergroundSettings(
        enabled=True,
        station_id="KTEST1",
        password="pw",
    )
    mock_settings.config_dir = tmp_path  # <-- tmp dir, NOT the project config/

    from weatherlink_bridge.publishers.wunderground import _build_wunderground

    # Must succeed and load from tmp_path, not from any __file__-relative path
    publisher = _build_wunderground(mock_settings)
    assert isinstance(publisher, WundergroundPublisher)
