"""Tests for WeatherLinkCollector and the _to_observation mapping logic.

Validates against:
  * The real EnviroMonitor fixture (tests/fixtures/weatherlink/current_enviromonitor.json)
  * An inline WLL / DST-10 response dict
  * HTTP-level behaviour via respx mocks
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

import httpx
import pytest
import respx

from weatherlink_bridge.collectors.weatherlink import (
    WeatherLinkCollector,
    _to_observation,
)
from weatherlink_bridge.exceptions import CollectorError
from weatherlink_bridge.models.weatherlink import WeatherLinkResponse
from weatherlink_bridge.settings import WeatherLinkSettings

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "weatherlink"
    / "current_enviromonitor.json"
)

_WL_URL_PATTERN = "https://api.weatherlink.com/v2/current/TEST_STATION"


def _load_enviromonitor() -> WeatherLinkResponse:
    """Parse the EnviroMonitor fixture into a WeatherLinkResponse."""
    with _FIXTURE_PATH.open() as fh:
        raw = json.load(fh)
    return WeatherLinkResponse.model_validate(raw)


_DST10_RESPONSE: dict[str, object] = {
    "station_id": 99999,
    "generated_at": 1781713900,
    "sensors": [
        {
            "lsid": 1,
            "sensor_type": 45,
            "data_structure_type": 10,
            "data": [
                {
                    "ts": 1781713900,
                    "temp": 72.4,
                    "hum": 65.0,
                    "wind_speed_last": 8.0,
                    "wind_speed_hi_last_10_min": 15.0,
                    "wind_dir_last": 270,
                    "rain_rate_last_in": 0.0,
                    "rainfall_last_60_min_in": 0.02,
                    "rainfall_daily_in": 0.10,
                    "uv_index": 3.1,
                    "solar_rad": 500,
                    "dew_point": 55.0,
                }
            ],
        },
        {
            "lsid": 2,
            "sensor_type": 242,
            "data_structure_type": 12,
            "data": [{"ts": 1781713900, "bar_sea_level": 29.92}],
        },
    ],
}


def _make_settings(station_id: str = "TEST_STATION") -> WeatherLinkSettings:
    return WeatherLinkSettings(
        api_key="test_key",
        api_secret="test_secret",
        station_id=station_id,
    )


# ---------------------------------------------------------------------------
# EnviroMonitor fixture tests
# ---------------------------------------------------------------------------


def test_to_observation_enviromonitor_temp() -> None:
    """temp_out_f maps from ISS temp_out == 67.6."""
    resp = _load_enviromonitor()
    obs = _to_observation(resp)
    assert obs.temp_out_f == pytest.approx(67.6)


def test_to_observation_enviromonitor_pressure() -> None:
    """pressure_sea_level_inHg == 29.959 from ISS bar (NOT bar_absolute == 29.958)."""
    resp = _load_enviromonitor()
    obs = _to_observation(resp)
    # bar == 29.959, bar_absolute == 29.958 — must use sea-level bar
    assert obs.pressure_sea_level_inHg == pytest.approx(29.959)
    assert obs.pressure_sea_level_inHg != pytest.approx(29.958)


def test_to_observation_enviromonitor_wind_gust() -> None:
    """wind_gust_mph == 13 (coerced from int wind_gust_10_min)."""
    resp = _load_enviromonitor()
    obs = _to_observation(resp)
    assert obs.wind_gust_mph == pytest.approx(13.0)
    # Must be float, not int
    assert isinstance(obs.wind_gust_mph, float)


def test_to_observation_enviromonitor_rain_60min_zero_survives() -> None:
    """rain_60min_in == 0.0 and is not None (defect #6: zero must survive)."""
    resp = _load_enviromonitor()
    obs = _to_observation(resp)
    assert obs.rain_60min_in == 0.0
    assert obs.rain_60min_in is not None


def test_to_observation_enviromonitor_timestamp_utc() -> None:
    """Timestamp is tz-aware UTC derived from ISS ts == 1781713800."""
    resp = _load_enviromonitor()
    obs = _to_observation(resp)
    assert obs.timestamp.tzinfo is not None
    assert obs.timestamp.tzinfo == UTC
    # Unix ts 1781713800 → verify epoch round-trip
    assert int(obs.timestamp.timestamp()) == 1781713800


def test_to_observation_enviromonitor_station_id() -> None:
    """station_id == 12345."""
    resp = _load_enviromonitor()
    obs = _to_observation(resp)
    assert obs.station_id == 12345


# ---------------------------------------------------------------------------
# WLL / DST-10 inline response tests
# ---------------------------------------------------------------------------


def test_to_observation_dst10_temp() -> None:
    """WLL temp field maps to temp_out_f."""
    resp = WeatherLinkResponse.model_validate(_DST10_RESPONSE)
    obs = _to_observation(resp)
    assert obs.temp_out_f == pytest.approx(72.4)


def test_to_observation_dst10_pressure_from_baro_sensor() -> None:
    """pressure_sea_level_inHg comes from the WLL barometer sensor (sensor_type 242)."""
    resp = WeatherLinkResponse.model_validate(_DST10_RESPONSE)
    obs = _to_observation(resp)
    assert obs.pressure_sea_level_inHg == pytest.approx(29.92)


def test_to_observation_dst10_wind_gust() -> None:
    """wind_gust_mph from WLL wind_speed_hi_last_10_min == 15.0."""
    resp = WeatherLinkResponse.model_validate(_DST10_RESPONSE)
    obs = _to_observation(resp)
    assert obs.wind_gust_mph == pytest.approx(15.0)


def test_to_observation_dst10_rain_60min() -> None:
    """rain_60min_in from rainfall_last_60_min_in == 0.02."""
    resp = WeatherLinkResponse.model_validate(_DST10_RESPONSE)
    obs = _to_observation(resp)
    assert obs.rain_60min_in == pytest.approx(0.02)


def test_to_observation_dst10_timestamp_from_ts() -> None:
    """Timestamp comes from ISS record ts, not generated_at."""
    resp = WeatherLinkResponse.model_validate(_DST10_RESPONSE)
    obs = _to_observation(resp)
    assert obs.timestamp.tzinfo == UTC
    assert int(obs.timestamp.timestamp()) == 1781713900


def test_to_observation_dst10_station_id() -> None:
    """station_id is taken from the top-level response field."""
    resp = WeatherLinkResponse.model_validate(_DST10_RESPONSE)
    obs = _to_observation(resp)
    assert obs.station_id == 99999


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_to_observation_no_iss_sensor() -> None:
    """Response with no ISS sensor yields None for all ISS-derived fields."""
    raw: dict[str, object] = {
        "station_id": 1,
        "generated_at": 1000000,
        "sensors": [],
    }
    resp = WeatherLinkResponse.model_validate(raw)
    obs = _to_observation(resp)
    assert obs.temp_out_f is None
    assert obs.humidity_pct is None
    assert obs.pressure_sea_level_inHg is None
    assert obs.wind_speed_mph is None
    assert obs.rain_60min_in is None
    # Timestamp falls back to generated_at
    assert int(obs.timestamp.timestamp()) == 1000000


def test_to_observation_fallback_timestamp_when_no_ts() -> None:
    """When ISS data record has no ts, generated_at is used."""
    raw: dict[str, object] = {
        "station_id": 2,
        "generated_at": 1781713861,
        "sensors": [
            {
                "lsid": 1,
                "sensor_type": 45,
                "data_structure_type": 10,
                "data": [{"temp": 70.0}],  # no ts field
            }
        ],
    }
    resp = WeatherLinkResponse.model_validate(raw)
    obs = _to_observation(resp)
    assert int(obs.timestamp.timestamp()) == 1781713861


# ---------------------------------------------------------------------------
# HTTP fetch tests via respx
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_sends_correct_auth_headers() -> None:
    """fetch() sends x-api-secret header; secret NOT in query string."""
    fixture_data = json.loads(_FIXTURE_PATH.read_text())
    route = respx.get(_WL_URL_PATTERN).mock(
        return_value=httpx.Response(200, json=fixture_data)
    )

    settings = _make_settings()
    async with httpx.AsyncClient() as client:
        collector = WeatherLinkCollector(settings, client)
        await collector.fetch()

    assert route.called
    request = route.calls[0].request
    # Secret must be in header
    assert request.headers.get("x-api-secret") == "test_secret"
    # API key must be in query params
    assert b"api-key=test_key" in request.url.query
    # Secret must NOT appear in query string
    assert b"test_secret" not in request.url.query


@respx.mock
async def test_fetch_401_raises_collector_error() -> None:
    """HTTP 401 from WeatherLink raises CollectorError."""
    respx.get(_WL_URL_PATTERN).mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )

    settings = _make_settings()
    async with httpx.AsyncClient() as client:
        collector = WeatherLinkCollector(settings, client)
        with pytest.raises(CollectorError):
            await collector.fetch()


@respx.mock
async def test_fetch_500_raises_collector_error() -> None:
    """HTTP 500 from WeatherLink raises CollectorError."""
    respx.get(_WL_URL_PATTERN).mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    settings = _make_settings()
    async with httpx.AsyncClient() as client:
        collector = WeatherLinkCollector(settings, client)
        with pytest.raises(CollectorError):
            await collector.fetch()


@respx.mock
async def test_fetch_network_error_raises_collector_error() -> None:
    """Network-level failure raises CollectorError."""
    respx.get(_WL_URL_PATTERN).mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    settings = _make_settings()
    async with httpx.AsyncClient() as client:
        collector = WeatherLinkCollector(settings, client)
        with pytest.raises(CollectorError):
            await collector.fetch()


# ---------------------------------------------------------------------------
# Soil sensor tests
# ---------------------------------------------------------------------------


def test_to_observation_soil_temp_from_model_extra() -> None:
    """temp_soil_1 from soil sensor model_extra maps to soil_temp_1_f."""
    raw: dict[str, object] = {
        "station_id": 3,
        "generated_at": 1000000,
        "sensors": [
            {
                "lsid": 1,
                "sensor_type": 24,
                "data_structure_type": 6,
                "data": [{"ts": 1000000, "temp_out": 70.0}],
            },
            {
                "lsid": 2,
                "sensor_type": 56,  # soil sensor
                "data_structure_type": 9,
                "data": [{"ts": 1000000, "temp_soil_1": 65.3}],
            },
        ],
    }
    resp = WeatherLinkResponse.model_validate(raw)
    obs = _to_observation(resp)
    assert obs.soil_temp_1_f == pytest.approx(65.3)


def test_to_observation_no_soil_sensor() -> None:
    """soil_temp_1_f is None when no soil sensor is present."""
    resp = _load_enviromonitor()
    obs = _to_observation(resp)
    assert obs.soil_temp_1_f is None


# ---------------------------------------------------------------------------
# Coverage gap: _find_iss skips ISS-type sensor with empty data list (51->50)
# ---------------------------------------------------------------------------


def test_find_iss_skips_empty_data_list() -> None:
    """_find_iss skips an ISS-type sensor whose data list is empty.

    Covers the branch: data_structure_type in {6,10,23} but sensor.data == [].
    The function must continue to the next sensor rather than crashing.
    """
    raw: dict[str, object] = {
        "station_id": 10,
        "generated_at": 1000000,
        "sensors": [
            {
                "lsid": 1,
                "sensor_type": 24,
                "data_structure_type": 6,
                "data": [],  # ISS type but empty — must be skipped
            },
            {
                "lsid": 2,
                "sensor_type": 45,
                "data_structure_type": 10,
                "data": [{"ts": 1000000, "temp": 68.0}],  # second ISS wins
            },
        ],
    }
    resp = WeatherLinkResponse.model_validate(raw)
    obs = _to_observation(resp)
    # Second ISS sensor's data should be used
    assert obs.temp_out_f == pytest.approx(68.0)
    assert obs.station_id == 10


def test_to_observation_iss_empty_data_no_indexerror() -> None:
    """No IndexError when ISS sensor has empty data AND no fallback ISS exists.

    Edge case (Task 4): a response whose only ISS sensor has data: [] must
    produce a valid obs with all ISS fields None rather than crashing.
    """
    raw: dict[str, object] = {
        "station_id": 11,
        "generated_at": 1781713800,
        "sensors": [
            {
                "lsid": 1,
                "sensor_type": 24,
                "data_structure_type": 6,
                "data": [],  # only ISS sensor, empty data
            },
        ],
    }
    resp = WeatherLinkResponse.model_validate(raw)
    obs = _to_observation(resp)
    assert obs.temp_out_f is None
    assert obs.pressure_sea_level_inHg is None
    assert obs.wind_speed_mph is None
    # Timestamp falls back to generated_at
    assert int(obs.timestamp.timestamp()) == 1781713800


# ---------------------------------------------------------------------------
# Coverage gap: soil sensor data with no extra fields → model_extra == {} (118->121)
# ---------------------------------------------------------------------------


def test_to_observation_soil_sensor_no_extra_fields() -> None:
    """soil_temp_1_f is None when soil sensor's data has no model_extra fields.

    Covers the branch: soil.model_extra is empty dict (falsy) — code path
    weatherlink.py line 118 (if soil.model_extra) evaluates to False.
    """
    raw: dict[str, object] = {
        "station_id": 12,
        "generated_at": 1000000,
        "sensors": [
            {
                "lsid": 1,
                "sensor_type": 24,
                "data_structure_type": 6,
                "data": [{"ts": 1000000, "temp_out": 70.0}],
            },
            {
                "lsid": 2,
                "sensor_type": 56,  # soil sensor
                "data_structure_type": 9,
                "data": [{"ts": 1000000}],  # no temp_soil_1 → model_extra == {}
            },
        ],
    }
    resp = WeatherLinkResponse.model_validate(raw)
    obs = _to_observation(resp)
    # Soil sensor found but no temp_soil_1 in model_extra → must be None
    assert obs.soil_temp_1_f is None
    # ISS fields still map correctly
    assert obs.temp_out_f == pytest.approx(70.0)


# ---------------------------------------------------------------------------
# Defect #6 (adversarial): temp_out == 0.0 must survive collector mapping
# ---------------------------------------------------------------------------


def test_to_observation_temp_out_zero_survives() -> None:
    """temp_out_f == 0.0 is preserved, not treated as missing (defect #6).

    _first() uses explicit 'is not None' — a 0.0 value must survive both
    _first() coalescing and the WeatherObservation field assignment.
    """
    raw: dict[str, object] = {
        "station_id": 13,
        "generated_at": 1000000,
        "sensors": [
            {
                "lsid": 1,
                "sensor_type": 24,
                "data_structure_type": 6,
                "data": [{"ts": 1000000, "temp_out": 0.0, "rain_60_min_in": 0.0}],
            },
        ],
    }
    resp = WeatherLinkResponse.model_validate(raw)
    obs = _to_observation(resp)
    # Both zero values must survive — 0.0 is not None
    assert obs.temp_out_f == 0.0
    assert obs.temp_out_f is not None
    assert obs.rain_60min_in == 0.0
    assert obs.rain_60min_in is not None


# ---------------------------------------------------------------------------
# Task 4: baro-only response (no ISS sensor) — should not crash
# ---------------------------------------------------------------------------


def test_to_observation_baro_only_no_iss_pressure_last() -> None:
    """A baro-only response (sensor_type 3 / DST 9) with pressure_last but no ISS.

    After ER-002: pressure_last is a declared field, so pressure_sea_level_inHg
    is populated from the baro sensor even without an ISS sensor.
    Uses 30.12 (distinct value) to prove it came from pressure_last.
    Timestamp falls back to generated_at when no ISS ts is available.
    """
    raw: dict[str, object] = {
        "station_id": 14,
        "generated_at": 1781713800,
        "sensors": [
            {
                "lsid": 1,
                "sensor_type": 3,  # EnviroMonitor baro
                "data_structure_type": 9,
                "data": [{"ts": 1781713800, "pressure_last": 30.12}],
            },
        ],
    }
    resp = WeatherLinkResponse.model_validate(raw)
    obs = _to_observation(resp)
    # No ISS → all ISS fields None
    assert obs.temp_out_f is None
    assert obs.humidity_pct is None
    assert obs.wind_speed_mph is None
    # pressure_last (30.12) is now a declared field — must be used
    assert obs.pressure_sea_level_inHg == pytest.approx(30.12)
    # Timestamp falls back to generated_at
    assert int(obs.timestamp.timestamp()) == 1781713800


def test_to_observation_baro_pressure_last_wins_over_iss_bar() -> None:
    """Baro pressure_last takes priority over ISS bar when both are present.

    The baro branch is evaluated first; a different ISS bar value confirms
    the baro sensor's pressure_last was selected, not the ISS bar.
    """
    raw: dict[str, object] = {
        "station_id": 15,
        "generated_at": 1781713800,
        "sensors": [
            {
                "lsid": 1,
                "sensor_type": 24,
                "data_structure_type": 6,
                "data": [{"ts": 1781713800, "temp_out": 68.0, "bar": 29.50}],
            },
            {
                "lsid": 2,
                "sensor_type": 3,  # EnviroMonitor baro — evaluated first
                "data_structure_type": 9,
                "data": [{"ts": 1781713800, "pressure_last": 30.12}],
            },
        ],
    }
    resp = WeatherLinkResponse.model_validate(raw)
    obs = _to_observation(resp)
    # Baro pressure_last (30.12) must win over ISS bar (29.50)
    assert obs.pressure_sea_level_inHg == pytest.approx(30.12)
    assert obs.pressure_sea_level_inHg != pytest.approx(29.50)


def test_to_observation_bar_absolute_never_selected() -> None:
    """bar_absolute (station pressure) is never selected as sea-level pressure.

    Even when bar and bar_sea_level are absent and bar_absolute is present,
    pressure_sea_level_inHg must remain None (ADR 0005).
    """
    raw: dict[str, object] = {
        "station_id": 16,
        "generated_at": 1781713800,
        "sensors": [
            {
                "lsid": 1,
                "sensor_type": 24,
                "data_structure_type": 6,
                "data": [{"ts": 1781713800, "temp_out": 68.0, "bar_absolute": 29.10}],
            },
        ],
    }
    resp = WeatherLinkResponse.model_validate(raw)
    obs = _to_observation(resp)
    # bar_absolute must never be published as sea-level pressure
    assert obs.pressure_sea_level_inHg is None
