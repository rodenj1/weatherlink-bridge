"""Tests for raw WeatherLink v2 API models (weatherlink.py).

Validates against the real fixture captured in Phase 0:
  tests/fixtures/weatherlink/current_enviromonitor.json
(station 12345, EnviroMonitor / data_structure_type 6).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from weatherlink_bridge.models.weatherlink import (
    Sensor,
    SensorData,
    WeatherLinkResponse,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "weatherlink"
    / "current_enviromonitor.json"
)


@pytest.fixture()
def raw_response() -> dict:  # type: ignore[type-arg]
    """Load the EnviroMonitor fixture as a raw dict."""
    with _FIXTURE_PATH.open() as fh:
        return json.load(fh)  # type: ignore[no-any-return]


@pytest.fixture()
def parsed_response(raw_response: dict) -> WeatherLinkResponse:  # type: ignore[type-arg]
    """Parse the fixture into a WeatherLinkResponse."""
    return WeatherLinkResponse.model_validate(raw_response)


# ---------------------------------------------------------------------------
# Top-level response shape
# ---------------------------------------------------------------------------


def test_fixture_parses_without_error(raw_response: dict) -> None:  # type: ignore[type-arg]
    """model_validate must not raise for the live fixture."""
    response = WeatherLinkResponse.model_validate(raw_response)
    assert isinstance(response, WeatherLinkResponse)


def test_station_id_parsed(parsed_response: WeatherLinkResponse) -> None:
    """station_id is the numeric ID from the fixture."""
    assert parsed_response.station_id == 12345


def test_station_id_uuid_is_none(parsed_response: WeatherLinkResponse) -> None:
    """station_id_uuid is null in the fixture → None."""
    assert parsed_response.station_id_uuid is None


def test_generated_at_parsed(parsed_response: WeatherLinkResponse) -> None:
    """generated_at epoch is present."""
    assert parsed_response.generated_at == 1781713861


def test_response_has_two_sensors(parsed_response: WeatherLinkResponse) -> None:
    """Fixture contains exactly 2 sensors."""
    assert len(parsed_response.sensors) == 2


# ---------------------------------------------------------------------------
# ISS sensor (sensor_type 24, data_structure_type 6)
# ---------------------------------------------------------------------------


def _iss_sensor(response: WeatherLinkResponse) -> Sensor:
    """Return the ISS sensor (sensor_type 24) from the parsed response."""
    matches = [s for s in response.sensors if s.sensor_type == 24]
    assert len(matches) == 1, f"Expected 1 ISS sensor, found {len(matches)}"
    return matches[0]


def test_iss_sensor_lsid(parsed_response: WeatherLinkResponse) -> None:
    """ISS sensor lsid is 100001."""
    assert _iss_sensor(parsed_response).lsid == 100001


def test_iss_sensor_data_structure_type(parsed_response: WeatherLinkResponse) -> None:
    """ISS sensor data_structure_type is 6 (EnviroMonitor)."""
    assert _iss_sensor(parsed_response).data_structure_type == 6


def test_iss_sensor_has_one_data_record(parsed_response: WeatherLinkResponse) -> None:
    """ISS sensor data list has exactly one record."""
    assert len(_iss_sensor(parsed_response).data) == 1


def test_iss_temp_out(parsed_response: WeatherLinkResponse) -> None:
    """temp_out == 67.6 °F (live value, ADR 0006 confirmed)."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.temp_out == 67.6


def test_iss_bar(parsed_response: WeatherLinkResponse) -> None:
    """bar == 29.959 inHg (sea-level pressure, maps to pressure_sea_level_inHg)."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.bar == 29.959


def test_iss_wind_gust_10_min(parsed_response: WeatherLinkResponse) -> None:
    """wind_gust_10_min == 13 mph."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.wind_gust_10_min == 13


def test_iss_rain_60_min_in_is_zero(parsed_response: WeatherLinkResponse) -> None:
    """rain_60_min_in == 0 (valid zero, not None — guards against x or y bug)."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.rain_60_min_in == 0
    assert data.rain_60_min_in is not None


def test_iss_hum_out(parsed_response: WeatherLinkResponse) -> None:
    """hum_out == 81."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.hum_out == 81


def test_iss_dew_point(parsed_response: WeatherLinkResponse) -> None:
    """dew_point == 62 °F."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.dew_point == 62


def test_iss_uv(parsed_response: WeatherLinkResponse) -> None:
    """uv == 2.8."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.uv == 2.8


def test_iss_solar_rad(parsed_response: WeatherLinkResponse) -> None:
    """solar_rad == 731 W/m²."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.solar_rad == 731


def test_iss_timestamp(parsed_response: WeatherLinkResponse) -> None:
    """ts (per-record timestamp) is present."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.ts == 1781713800


def test_iss_rain_day_in_is_zero(parsed_response: WeatherLinkResponse) -> None:
    """rain_day_in == 0 (valid zero)."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.rain_day_in == 0
    assert data.rain_day_in is not None


def test_iss_rain_rate_in_is_zero(parsed_response: WeatherLinkResponse) -> None:
    """rain_rate_in == 0 (valid zero)."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.rain_rate_in == 0
    assert data.rain_rate_in is not None


def test_iss_metric_rain_variants_present(parsed_response: WeatherLinkResponse) -> None:
    """Metric rain variants (rain_60_min_mm, rain_day_mm) are modelled and parsed."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.rain_60_min_mm == 0
    assert data.rain_day_mm == 0
    assert data.rain_rate_mm == 0


# ---------------------------------------------------------------------------
# extra="allow" — unmodelled fields land in model_extra
# ---------------------------------------------------------------------------


def test_extra_fields_preserved_in_model_extra(
    parsed_response: WeatherLinkResponse,
) -> None:
    """heat_index is not a declared field; it must appear in model_extra."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.model_extra is not None
    assert "heat_index" in data.model_extra
    assert data.model_extra["heat_index"] == 69


def test_extra_fields_do_not_raise(parsed_response: WeatherLinkResponse) -> None:
    """Additional unknown fields (thsw_index, wet_bulb, etc.) do not cause errors."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.model_extra is not None
    # Several extra fields present in the fixture
    for field in ("thsw_index", "wet_bulb", "wind_chill", "forecast_rule"):
        assert field in data.model_extra, f"Expected {field!r} in model_extra"


# ---------------------------------------------------------------------------
# Barometer sensor (sensor_type 3, data_structure_type 9)
# ---------------------------------------------------------------------------


def _baro_sensor(response: WeatherLinkResponse) -> Sensor:
    matches = [s for s in response.sensors if s.sensor_type == 3]
    assert len(matches) == 1
    return matches[0]


def test_baro_sensor_parsed(parsed_response: WeatherLinkResponse) -> None:
    """Barometer sensor (sensor_type 3) is present."""
    baro = _baro_sensor(parsed_response)
    assert baro.lsid == 100002
    assert baro.data_structure_type == 9


def test_baro_sensor_has_data(parsed_response: WeatherLinkResponse) -> None:
    """Barometer sensor has exactly one data record."""
    assert len(_baro_sensor(parsed_response).data) == 1


def test_baro_sensor_extra_pressure_last(parsed_response: WeatherLinkResponse) -> None:
    """pressure_last is not a declared SensorData field; it lands in model_extra."""
    data = _baro_sensor(parsed_response).data[0]
    assert data.model_extra is not None
    assert "pressure_last" in data.model_extra
    assert data.model_extra["pressure_last"] == pytest.approx(29.959)


# ---------------------------------------------------------------------------
# WLL / DST-10 portability fields default to None for EnviroMonitor fixture
# ---------------------------------------------------------------------------


def test_wll_fields_absent_in_enviromonitor(
    parsed_response: WeatherLinkResponse,
) -> None:
    """WLL-specific fields (temp, hum, wind_speed_last, …) are None for DST 6."""
    data = _iss_sensor(parsed_response).data[0]
    assert data.temp is None
    assert data.hum is None
    assert data.wind_speed_last is None
    assert data.uv_index is None
    assert data.bar_sea_level is None
    assert data.rainfall_last_60_min_in is None


# ---------------------------------------------------------------------------
# SensorData model construction
# ---------------------------------------------------------------------------


def test_sensor_data_all_optional_defaults() -> None:
    """SensorData can be constructed with no arguments (all fields optional)."""
    sd = SensorData()
    assert sd.temp_out is None
    assert sd.bar is None
    assert sd.wind_speed is None


def test_sensor_data_direct_construction() -> None:
    """SensorData accepts keyword arguments for any declared field."""
    sd = SensorData(temp_out=72.0, bar=29.92, wind_speed=5.0)
    assert sd.temp_out == 72.0
    assert sd.bar == pytest.approx(29.92)
    assert sd.wind_speed == 5.0


# ---------------------------------------------------------------------------
# WLL / DST-10 portability — positive path (inline dict, no fixture file)
# ---------------------------------------------------------------------------

_DST10_ISS_RECORD: dict[str, object] = {
    "ts": 1781713800,
    "temp": 72.4,
    "hum": 65.0,
    "wind_speed_hi_last_10_min": 15.0,
    "uv_index": 3.1,
    "bar_sea_level": 29.92,
    "rainfall_last_60_min_in": 0.02,
}


def test_dst10_wll_fields_populated() -> None:
    """DST-10 ISS dict populates all WLL-generation fields."""
    sd = SensorData.model_validate(_DST10_ISS_RECORD)
    assert sd.temp == pytest.approx(72.4)
    assert sd.hum == pytest.approx(65.0)
    assert sd.wind_speed_hi_last_10_min == pytest.approx(15.0)
    assert sd.uv_index == pytest.approx(3.1)
    assert sd.bar_sea_level == pytest.approx(29.92)
    assert sd.rainfall_last_60_min_in == pytest.approx(0.02)


def test_dst10_enviromonitor_fields_absent() -> None:
    """A DST-10 dict that omits EnviroMonitor fields leaves them None.

    This proves both device generations coexist in the same model without
    cross-contamination — the WLL fields don't bleed into DST-6 names.
    """
    sd = SensorData.model_validate(_DST10_ISS_RECORD)
    assert sd.temp_out is None
    assert sd.hum_out is None
    assert sd.wind_speed is None
    assert sd.wind_gust_10_min is None
    assert sd.uv is None
    assert sd.bar is None
    assert sd.rain_60_min_in is None


# ---------------------------------------------------------------------------
# extra="allow" round-trip — unmodelled fields land in model_extra only
# ---------------------------------------------------------------------------


def test_extra_field_not_in_model_fields() -> None:
    """heat_index must not appear in model_fields — it is not a declared field."""
    assert "heat_index" not in SensorData.model_fields
    assert "thsw_index" not in SensorData.model_fields


def test_extra_field_in_model_extra_not_promoted() -> None:
    """An unmodelled field is captured in model_extra, not promoted to model_fields.

    Verifies the invariant: extra data is accessible via model_extra, and the
    model's declared-field set does not grow at validation time.
    """
    sd = SensorData.model_validate(
        {"temp_out": 67.6, "heat_index": 69, "thsw_index": 78}
    )
    assert sd.model_extra is not None
    assert sd.model_extra["heat_index"] == 69
    assert sd.model_extra["thsw_index"] == 78
    # The model's declared-field catalog must not include these runtime extras.
    assert "heat_index" not in SensorData.model_fields
    assert "thsw_index" not in SensorData.model_fields


# ---------------------------------------------------------------------------
# Dual-unit rain — in and mm are independent, separately captured fields
# ---------------------------------------------------------------------------


def test_dual_unit_rain_captured_independently() -> None:
    """rain_60_min_in and rain_60_min_mm are separate fields that can diverge.

    Populating both with distinct values proves they are independently modelled
    and that one does not alias or overwrite the other.
    """
    sd = SensorData.model_validate(
        {
            "rain_60_min_in": 0.5,
            "rain_60_min_mm": 12.7,
        }
    )
    assert sd.rain_60_min_in == pytest.approx(0.5)
    assert sd.rain_60_min_mm == pytest.approx(12.7)
    # They are distinct values — not aliases
    assert sd.rain_60_min_in != sd.rain_60_min_mm


def test_dual_unit_rain_fields_exist_in_model_fields() -> None:
    """Both rain_60_min_in and rain_60_min_mm are declared model fields."""
    assert "rain_60_min_in" in SensorData.model_fields
    assert "rain_60_min_mm" in SensorData.model_fields


# ---------------------------------------------------------------------------
# Numeric-0 integrity — zero is not coalesced to None (guards defect #6)
# ---------------------------------------------------------------------------


def test_rain_60_min_in_zero_preserved_via_model_validate() -> None:
    """SensorData.model_validate keeps rain_60_min_in=0.0 as 0.0, not None.

    Explicitly constructed via model_validate (not from the fixture) to prove
    the model itself does not coalesce zeros — guards against an ``x or y``
    bug in downstream code (defect #6).
    """
    sd = SensorData.model_validate({"rain_60_min_in": 0.0})
    assert sd.rain_60_min_in == 0.0
    assert sd.rain_60_min_in is not None


def test_all_rain_zeros_preserved() -> None:
    """All rain fields set to 0.0 are retained as 0.0, not coerced to None."""
    sd = SensorData.model_validate(
        {
            "rain_rate_in": 0.0,
            "rain_60_min_in": 0.0,
            "rain_day_in": 0.0,
            "rain_rate_mm": 0.0,
            "rain_60_min_mm": 0.0,
            "rain_day_mm": 0.0,
        }
    )
    assert sd.rain_rate_in == 0.0
    assert sd.rain_60_min_in == 0.0
    assert sd.rain_day_in == 0.0
    assert sd.rain_rate_mm == 0.0
    assert sd.rain_60_min_mm == 0.0
    assert sd.rain_day_mm == 0.0
    # None of them should be None
    assert sd.rain_rate_in is not None
    assert sd.rain_60_min_in is not None
    assert sd.rain_day_in is not None
