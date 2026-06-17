"""Tests for the canonical WeatherObservation model (observation.py).

Verifies:
  * Correct canonical field names (ADR 0002 / ADR 0006).
  * All weather fields default to None.
  * Wrong / legacy names are absent from model_fields.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from weatherlink_bridge.models.observation import WeatherObservation

# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------

_UTC_NOW = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)


def _minimal() -> WeatherObservation:
    """Construct a WeatherObservation with only required fields."""
    return WeatherObservation(timestamp=_UTC_NOW, station_id=12345)


def _full() -> WeatherObservation:
    """Construct a WeatherObservation with all weather fields populated."""
    return WeatherObservation(
        timestamp=_UTC_NOW,
        station_id=12345,
        temp_out_f=67.6,
        humidity_pct=81.0,
        dew_point_f=62.0,
        pressure_sea_level_inHg=29.959,
        wind_speed_mph=12.0,
        wind_gust_mph=13.0,
        wind_dir_deg=248.0,
        rain_rate_in_hr=0.0,
        rain_60min_in=0.0,
        rain_day_in=0.0,
        uv_index=2.8,
        solar_rad_wm2=731.0,
        soil_temp_1_f=None,
    )


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------


def test_timestamp_required() -> None:
    """timestamp must be supplied; missing it raises ValidationError."""
    with pytest.raises(Exception):
        WeatherObservation(station_id=12345)  # type: ignore[call-arg]


def test_station_id_required() -> None:
    """station_id must be supplied; missing it raises ValidationError."""
    with pytest.raises(Exception):
        WeatherObservation(timestamp=_UTC_NOW)  # type: ignore[call-arg]


def test_timestamp_round_trips() -> None:
    """timestamp is preserved exactly."""
    obs = _minimal()
    assert obs.timestamp == _UTC_NOW


def test_station_id_round_trips() -> None:
    """station_id is preserved exactly."""
    obs = _minimal()
    assert obs.station_id == 12345


# ---------------------------------------------------------------------------
# Optional weather fields default to None
# ---------------------------------------------------------------------------


def test_all_optional_fields_default_to_none() -> None:
    """Every optional field is None when not provided."""
    obs = _minimal()
    assert obs.temp_out_f is None
    assert obs.humidity_pct is None
    assert obs.dew_point_f is None
    assert obs.pressure_sea_level_inHg is None
    assert obs.wind_speed_mph is None
    assert obs.wind_gust_mph is None
    assert obs.wind_dir_deg is None
    assert obs.rain_rate_in_hr is None
    assert obs.rain_60min_in is None
    assert obs.rain_day_in is None
    assert obs.uv_index is None
    assert obs.solar_rad_wm2 is None
    assert obs.soil_temp_1_f is None


def test_rain_zero_is_not_none() -> None:
    """rain_60min_in=0.0 is a valid zero, not None (guards against ``x or y`` bug)."""
    obs = WeatherObservation(
        timestamp=_UTC_NOW,
        station_id=12345,
        rain_60min_in=0.0,
    )
    assert obs.rain_60min_in == 0.0
    assert obs.rain_60min_in is not None


# ---------------------------------------------------------------------------
# Canonical field names exist (positive)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name",
    [
        "pressure_sea_level_inHg",
        "rain_60min_in",
        "rain_rate_in_hr",
        "rain_day_in",
        "temp_out_f",
        "humidity_pct",
        "dew_point_f",
        "wind_speed_mph",
        "wind_gust_mph",
        "wind_dir_deg",
        "uv_index",
        "solar_rad_wm2",
        "soil_temp_1_f",
    ],
)
def test_canonical_field_exists(field_name: str) -> None:
    """Each canonical field name must be present in model_fields."""
    assert field_name in WeatherObservation.model_fields, (
        f"Canonical field {field_name!r} missing from WeatherObservation"
    )


# ---------------------------------------------------------------------------
# Wrong / legacy field names do NOT exist (negative)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "wrong_name",
    [
        "pressure_inHg",  # wrong prefix — must be pressure_sea_level_inHg
        "rain_last_60min_in",  # wrong — canonical is rain_60min_in
        "rainfall_last_60_min_in",  # WLL raw name — must not leak into canonical
        "rain_rate_in",  # raw DST-6 name — canonical is rain_rate_in_hr
        "temp_f",  # wrong — canonical is temp_out_f
        "bar",  # raw WeatherLink name — not canonical
        "bar_sea_level",  # raw WLL name — not canonical
    ],
)
def test_legacy_field_absent(wrong_name: str) -> None:
    """Legacy / wrong names must not appear in model_fields."""
    assert wrong_name not in WeatherObservation.model_fields, (
        f"Legacy/wrong field {wrong_name!r} must not exist on WeatherObservation"
    )


# ---------------------------------------------------------------------------
# Full construction round-trip
# ---------------------------------------------------------------------------


def test_full_construction_round_trips() -> None:
    """All weather fields survive a round-trip through model_validate."""
    obs = _full()
    assert obs.temp_out_f == pytest.approx(67.6)
    assert obs.humidity_pct == pytest.approx(81.0)
    assert obs.pressure_sea_level_inHg == pytest.approx(29.959)
    assert obs.wind_gust_mph == pytest.approx(13.0)
    assert obs.uv_index == pytest.approx(2.8)
    assert obs.solar_rad_wm2 == pytest.approx(731.0)
