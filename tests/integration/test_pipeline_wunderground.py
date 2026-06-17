"""Integration: WeatherLink collector → WU publisher (real components, mocked HTTP)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from weatherlink_bridge.collectors.weatherlink import WeatherLinkCollector
from weatherlink_bridge.mapping.mapper import FieldMapper
from weatherlink_bridge.publishers.base import PublishResult
from weatherlink_bridge.publishers.wunderground import WundergroundPublisher
from weatherlink_bridge.settings import WeatherLinkSettings, WundergroundSettings

_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "weatherlink"
    / "current_enviromonitor.json"
)
_WL_STATION_ID = "12345"
_WL_URL = f"https://api.weatherlink.com/v2/current/{_WL_STATION_ID}"
_WU_URL = (
    "https://weatherstation.wunderground.com/weatherstation/updateweatherstation.php"
)
_WU_MAP = Path(__file__).parents[2] / "config" / "sensor_maps" / "wunderground.yaml"


def _load_fixture() -> dict[object, object]:
    with _FIXTURE.open() as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def _wu_settings() -> WundergroundSettings:
    return WundergroundSettings(
        enabled=True,
        station_id="KTEST001",
        password="testpw",
    )


def _wl_settings() -> WeatherLinkSettings:
    return WeatherLinkSettings(
        api_key="wlkey",
        api_secret="wlsecret",
        station_id=_WL_STATION_ID,
    )


@pytest.mark.integration
@respx.mock
async def test_wunderground_success_path() -> None:
    """Full pipeline: WeatherLink → WU — both HTTP endpoints mocked; SUCCESS result."""
    fixture_data = _load_fixture()

    # Mock WeatherLink API
    respx.get(_WL_URL).mock(return_value=httpx.Response(200, json=fixture_data))
    # Mock WU endpoint — success body
    wu_route = respx.get(_WU_URL).mock(return_value=httpx.Response(200, text="success"))

    async with httpx.AsyncClient() as wl_client:
        collector = WeatherLinkCollector(_wl_settings(), wl_client)
        obs = await collector.fetch()

    mapper = FieldMapper(_WU_MAP)
    async with httpx.AsyncClient() as wu_client:
        publisher = WundergroundPublisher(_wu_settings(), wu_client, mapper)
        result = await publisher.publish(obs)

    assert result is PublishResult.SUCCESS

    # Decode the WU request query string
    assert wu_route.call_count == 1
    sent_request = wu_route.calls[0].request
    parsed = urlparse(str(sent_request.url))
    qs = parse_qs(parsed.query)

    def _single(key: str) -> str:
        values = qs.get(key)
        assert values is not None, f"missing key {key!r} in WU request"
        return values[0]

    assert float(_single("tempf")) == pytest.approx(67.6)
    assert float(_single("baromin")) == pytest.approx(29.959)
    assert float(_single("rainin")) == pytest.approx(0.0)
    assert float(_single("UV")) == pytest.approx(2.8)
    assert float(_single("windgustmph")) == pytest.approx(13.0)
    assert float(_single("windgustmph_10m")) == pytest.approx(13.0)
    assert _single("ID") == "KTEST001"
    assert _single("PASSWORD") == "testpw"


@pytest.mark.integration
@respx.mock
async def test_wunderground_invalid_password_returns_failure() -> None:
    """Pipeline: WU responds with INVALIDPASSWORDID body → FAILURE result."""
    fixture_data = _load_fixture()

    respx.get(_WL_URL).mock(return_value=httpx.Response(200, json=fixture_data))
    respx.get(_WU_URL).mock(
        return_value=httpx.Response(
            200, text="INVALIDPASSWORDID|Password and/or id are incorrect"
        )
    )

    async with httpx.AsyncClient() as wl_client:
        collector = WeatherLinkCollector(_wl_settings(), wl_client)
        obs = await collector.fetch()

    mapper = FieldMapper(_WU_MAP)
    async with httpx.AsyncClient() as wu_client:
        publisher = WundergroundPublisher(_wu_settings(), wu_client, mapper)
        result = await publisher.publish(obs)

    assert result is PublishResult.FAILURE
