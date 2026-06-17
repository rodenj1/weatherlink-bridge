"""Integration: run() daemon — one full cycle with all external HTTP mocked.

Design:
- AppSettings with both wunderground and windy enabled.
- start_metrics_server patched (no real port).
- WeatherLink, WU, and Windy HTTP endpoints mocked via respx.
- asyncio.wait_for patched to fire stop_event and raise TimeoutError after
  one cycle (same pattern as unit/test_daemon.py).
- Assertions: route call counts, Prometheus counter increments, metric
  text output, collector client closed.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx

from weatherlink_bridge.metrics import (
    collection_run_total,
    last_successful_cycle_timestamp,
)
from weatherlink_bridge.settings import (
    AppSettings,
    WeatherLinkSettings,
    WindySettings,
    WundergroundSettings,
)

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
_WINDY_URL = "https://stations.windy.com/api/v2/observation/update"


def _load_fixture() -> dict[object, object]:
    with _FIXTURE.open() as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def _make_settings() -> AppSettings:
    return AppSettings(
        _env_file="",  # type: ignore[call-arg]
        weatherlink=WeatherLinkSettings(
            api_key="wlkey",
            api_secret="wlsecret",
            station_id=_WL_STATION_ID,
        ),
        wunderground=WundergroundSettings(
            enabled=True,
            station_id="KTEST001",
            api_key="testpw",
        ),
        windy=WindySettings(
            enabled=True,
            station_id="WINDYtest1",
            api_key="windypw",
        ),
        update_interval_mins=5,
        metrics_port=19898,
    )


def _make_wait_for_that_stops(stop_event: asyncio.Event) -> Any:
    """Return a side_effect for weatherlink_bridge.main.asyncio.wait_for.

    Sets stop_event (so the loop exits) and raises TimeoutError (the normal
    tick path — daemon catches TimeoutError and continues to the while-check).
    The coroutine argument is closed to avoid "coroutine was never awaited" warnings.
    """

    async def _side_effect(coro: Any, *, timeout: float) -> None:
        if hasattr(coro, "close"):
            coro.close()
        stop_event.set()
        raise TimeoutError

    return _side_effect


def _gauge_value(gauge: Any) -> float:
    return float(gauge._value.get())  # type: ignore[attr-defined]


@pytest.mark.integration
@respx.mock
async def test_daemon_one_cycle_both_publishers() -> None:
    """run() executes one full cycle with both publishers active; asserts metrics and HTTP calls."""
    from weatherlink_bridge.main import run

    fixture_data = _load_fixture()
    settings = _make_settings()
    stop_event = asyncio.Event()

    # Snapshot counter values before the run so we can check increments
    before_success = _gauge_value(collection_run_total.labels(status="success"))
    before_ts = _gauge_value(last_successful_cycle_timestamp)

    # Mock all three HTTP endpoints
    wl_route = respx.get(_WL_URL).mock(
        return_value=httpx.Response(200, json=fixture_data)
    )
    wu_route = respx.get(_WU_URL).mock(return_value=httpx.Response(200, text="success"))
    windy_route = respx.get(_WINDY_URL).mock(return_value=httpx.Response(200, text=""))

    # Track the collector's httpx.AsyncClient to verify it gets closed
    captured_collector_clients: list[httpx.AsyncClient] = []
    real_async_client = httpx.AsyncClient

    def _capturing_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        client = real_async_client(*args, **kwargs)  # type: ignore[arg-type]
        captured_collector_clients.append(client)
        return client

    with (
        patch("weatherlink_bridge.metrics.start_http_server"),
        patch(
            "weatherlink_bridge.main.httpx.AsyncClient",
            side_effect=_capturing_client,
        ),
        patch(
            "weatherlink_bridge.main.asyncio.wait_for",
            side_effect=_make_wait_for_that_stops(stop_event),
        ),
    ):
        await run(_settings=settings, _stop_event=stop_event)

    # Each HTTP endpoint was called exactly once
    assert wl_route.call_count == 1
    assert wu_route.call_count == 1
    assert windy_route.call_count == 1

    # collection_run_total{status="success"} incremented by 1
    after_success = _gauge_value(collection_run_total.labels(status="success"))
    assert after_success == before_success + 1

    # last_successful_cycle_timestamp advanced past zero
    after_ts = _gauge_value(last_successful_cycle_timestamp)
    assert after_ts > 0
    assert after_ts > before_ts

    # Prometheus text output contains the expected metric names
    from prometheus_client import REGISTRY, generate_latest

    output = generate_latest(REGISTRY).decode("utf-8")
    assert "wl_fetch_total" in output
    assert "observation_value" in output

    # run() creates three httpx.AsyncClient instances: one for the collector
    # (in main.py) and one each for the WU and Windy publisher builders
    # (called via PublisherFactory.create_all from within run()).  All three
    # must be closed on shutdown.
    assert len(captured_collector_clients) == 3
    for client in captured_collector_clients:
        assert client.is_closed, f"client {client!r} was not closed on shutdown"
