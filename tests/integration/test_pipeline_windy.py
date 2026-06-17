"""Integration: WeatherLink collector → Windy publisher (real components, mocked HTTP)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from weatherlink_bridge.collectors.weatherlink import WeatherLinkCollector
from weatherlink_bridge.mapping.mapper import FieldMapper
from weatherlink_bridge.publishers.base import PublishResult
from weatherlink_bridge.publishers.windy import WindyPublisher
from weatherlink_bridge.settings import WeatherLinkSettings, WindySettings

_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "weatherlink"
    / "current_enviromonitor.json"
)
_WL_STATION_ID = "12345"
_WL_URL = f"https://api.weatherlink.com/v2/current/{_WL_STATION_ID}"
_WINDY_URL = "https://stations.windy.com/api/v2/observation/update"
_WINDY_MAP = Path(__file__).parents[2] / "config" / "sensor_maps" / "windy.yaml"


def _load_fixture() -> dict[object, object]:
    with _FIXTURE.open() as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def _windy_settings() -> WindySettings:
    return WindySettings(
        enabled=True,
        station_id="WINDYtest1",
        api_key="windypw",
    )


def _wl_settings() -> WeatherLinkSettings:
    return WeatherLinkSettings(
        api_key="wlkey",
        api_secret="wlsecret",
        station_id=_WL_STATION_ID,
    )


@pytest.mark.integration
@respx.mock
async def test_windy_success_path() -> None:
    """Full pipeline: WeatherLink → Windy — both HTTP endpoints mocked; SUCCESS result."""
    fixture_data = _load_fixture()

    respx.get(_WL_URL).mock(return_value=httpx.Response(200, json=fixture_data))
    windy_route = respx.get(_WINDY_URL).mock(return_value=httpx.Response(200, text=""))

    async with httpx.AsyncClient() as wl_client:
        collector = WeatherLinkCollector(_wl_settings(), wl_client)
        obs = await collector.fetch()

    mapper = FieldMapper(_WINDY_MAP)
    async with httpx.AsyncClient() as windy_client:
        publisher = WindyPublisher(_windy_settings(), windy_client, mapper)
        result = await publisher.publish(obs)

    assert result is PublishResult.SUCCESS

    # Decode Windy request query string
    assert windy_route.call_count == 1
    sent_request = windy_route.calls[0].request
    parsed = urlparse(str(sent_request.url))
    qs = parse_qs(parsed.query)

    def _single(key: str) -> str:
        values = qs.get(key)
        assert values is not None, f"missing key {key!r} in Windy request"
        return values[0]

    # temp: f_to_c(67.6) = (67.6-32)*5/9 = 19.7778
    assert float(_single("temp")) == pytest.approx(round((67.6 - 32) * 5 / 9, 4))
    # pressure: inhg_to_pa(29.959) = 29.959 * 3386.389
    assert float(_single("pressure")) == pytest.approx(round(29.959 * 3386.389, 4))
    # wind: mph_to_ms(12) = 12 * 0.44704 = 5.3645
    assert float(_single("wind")) == pytest.approx(round(12 * 0.44704, 4))
    # gust: mph_to_ms(13) = 13 * 0.44704 = 5.8115
    assert float(_single("gust")) == pytest.approx(round(13 * 0.44704, 4))
    # precip: in_to_mm(0) = 0.0 — zero must survive
    assert float(_single("precip")) == pytest.approx(0.0)
    # station id and auth
    assert _single("id") == "WINDYtest1"
    assert _single("PASSWORD") == "windypw"
    # time must be a UTC ISO timestamp ending with Z
    assert _single("time").endswith("Z")
    # imperial keys must NOT appear
    assert "tempf" not in qs
    assert "windspeedmph" not in qs
    assert "baromin" not in qs


@pytest.mark.integration
@respx.mock
async def test_windy_429_backoff_skips_second_publish() -> None:
    """Pipeline: 429 response arms backoff; second publish returns SKIPPED without HTTP call."""
    fixture_data = _load_fixture()

    respx.get(_WL_URL).mock(return_value=httpx.Response(200, json=fixture_data))
    # Windy returns 429 on the first call; retry_after set far in the future
    future_time = (datetime.now(UTC) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    windy_route = respx.get(_WINDY_URL).mock(
        return_value=httpx.Response(200, json={"retry_after": future_time}),
        side_effect=None,
    )
    # Override the mock to return 429 status
    windy_route.mock(
        return_value=httpx.Response(429, json={"retry_after": future_time})
    )

    async with httpx.AsyncClient() as wl_client:
        collector = WeatherLinkCollector(_wl_settings(), wl_client)
        obs = await collector.fetch()

    mapper = FieldMapper(_WINDY_MAP)
    async with httpx.AsyncClient() as windy_client:
        publisher = WindyPublisher(_windy_settings(), windy_client, mapper)

        # First publish — hits Windy, gets 429, returns FAILURE and arms backoff
        first_result = await publisher.publish(obs)
        assert first_result is PublishResult.FAILURE

        # Second publish — backoff is active; must return SKIPPED without HTTP call
        second_result = await publisher.publish(obs)
        assert second_result is PublishResult.SKIPPED

    # Windy endpoint was called exactly once (second publish skipped HTTP)
    assert windy_route.call_count == 1
