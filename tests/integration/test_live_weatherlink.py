"""Live smoke test: real WeatherLink API call (opt-in, skipped by default).

Set WLB_LIVE_TESTS=1 and ensure real WeatherLink credentials are available in
the environment (WEATHERLINK__API_KEY, WEATHERLINK__API_SECRET,
WEATHERLINK__STATION_ID) or a .env file before running.
"""

from __future__ import annotations

import os

import httpx
import pytest

from weatherlink_bridge.collectors.weatherlink import WeatherLinkCollector
from weatherlink_bridge.settings import AppSettings


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("WLB_LIVE_TESTS") != "1",
    reason="live test; set WLB_LIVE_TESTS=1 and real creds",
)
async def test_live_fetch_returns_sane_observation() -> None:
    """Real WeatherLink API fetch — read-only, no publishing."""
    settings = AppSettings()  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]
    async with httpx.AsyncClient() as client:
        collector = WeatherLinkCollector(settings.weatherlink, client)
        obs = await collector.fetch()

    assert obs.station_id > 0
    assert obs.timestamp.tzinfo is not None  # tz-aware
    assert obs.temp_out_f is not None
    assert -60.0 <= obs.temp_out_f <= 140.0
