"""Tests for FieldMapper — sensor map YAML loading and observation translation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from weatherlink_bridge.exceptions import MappingError
from weatherlink_bridge.mapping.mapper import FieldMapper
from weatherlink_bridge.models.observation import WeatherObservation

_WUNDERGROUND_MAP_PATH = (
    Path(__file__).parents[2] / "config" / "sensor_maps" / "wunderground.yaml"
)
_WINDY_MAP_PATH = Path(__file__).parents[2] / "config" / "sensor_maps" / "windy.yaml"

_FIXED_TIMESTAMP = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)


def _obs(**kwargs: object) -> WeatherObservation:
    """Return a WeatherObservation with all fields None except those in kwargs."""
    return WeatherObservation(
        timestamp=_FIXED_TIMESTAMP,
        station_id=12345,
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Happy-path: wunderground.yaml loads without error
# ---------------------------------------------------------------------------


def test_wunderground_yaml_loads() -> None:
    """wunderground.yaml is valid and FieldMapper initialises without error."""
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    assert mapper is not None


# ---------------------------------------------------------------------------
# Field mapping tests
# ---------------------------------------------------------------------------


def test_wunderground_map_baromin() -> None:
    """pressure_sea_level_inHg → baromin."""
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    result = mapper.map(_obs(pressure_sea_level_inHg=29.959))
    assert result["baromin"] == "29.959"


def test_wunderground_map_rainin_from_60min() -> None:
    """rain_60min_in → rainin."""
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    result = mapper.map(_obs(rain_60min_in=0.05))
    assert result["rainin"] == "0.05"


def test_wunderground_map_uv_uppercase() -> None:
    """uv_index maps to uppercase 'UV' key — critical for WU protocol."""
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    result = mapper.map(_obs(uv_index=3.5))
    assert "UV" in result
    assert result["UV"] == "3.5"
    # Lowercase must NOT be present
    assert "uv" not in result


def test_wunderground_map_wind_gust_1_to_many() -> None:
    """wind_gust_mph fans out to both windgustmph and windgustmph_10m."""
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    result = mapper.map(_obs(wind_gust_mph=13.0))
    assert "windgustmph" in result
    assert "windgustmph_10m" in result
    assert result["windgustmph"] == "13.0"
    assert result["windgustmph_10m"] == "13.0"


def test_zero_value_included_not_skipped() -> None:
    """rain_60min_in == 0.0 must appear in result — 0.0 is not None (defect #6)."""
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    result = mapper.map(_obs(rain_60min_in=0.0))
    assert "rainin" in result
    assert result["rainin"] == "0.0"


def test_none_value_skipped() -> None:
    """temp_out_f == None must not appear in result."""
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    result = mapper.map(_obs(temp_out_f=None))
    assert "tempf" not in result


def test_static_params_included() -> None:
    """Static params (action, dateutc) are always included in the result."""
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    result = mapper.map(_obs())
    assert result.get("action") == "updateraw"
    assert result.get("dateutc") == "now"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_unknown_transform_raises_mapping_error(tmp_path: Path) -> None:
    """A sensor map with an unknown transform name raises MappingError at init time."""
    yaml_content = """\
fields:
  temp_out_f:
    target: tempf
    transform: not_a_real_transform
"""
    map_file = tmp_path / "bad_map.yaml"
    map_file.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(MappingError, match="Unknown transform"):
        FieldMapper(map_file)


def test_invalid_yaml_raises_mapping_error(tmp_path: Path) -> None:
    """Malformed YAML raises MappingError."""
    map_file = tmp_path / "invalid.yaml"
    map_file.write_text("fields: {unclosed: brace", encoding="utf-8")

    with pytest.raises(MappingError, match="Failed to parse"):
        FieldMapper(map_file)


def test_invalid_schema_raises_mapping_error(tmp_path: Path) -> None:
    """Valid YAML with invalid schema raises MappingError."""
    map_file = tmp_path / "bad_schema.yaml"
    map_file.write_text("fields: not_a_dict\n", encoding="utf-8")

    with pytest.raises(MappingError, match="schema validation"):
        FieldMapper(map_file)


# ---------------------------------------------------------------------------
# rain_rate_in_hr intentionally NOT in the wunderground map
# ---------------------------------------------------------------------------


def test_rain_rate_not_mapped_to_wunderground() -> None:
    """rain_rate_in_hr is intentionally excluded from the WU sensor map."""
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    result = mapper.map(_obs(rain_rate_in_hr=0.5))
    # No WU parameter should carry rain rate
    assert "rainratein" not in result
    assert "rain_rate" not in result


# ---------------------------------------------------------------------------
# Defect #6 (adversarial): temp_out_f == 0.0 must survive field mapping
# ---------------------------------------------------------------------------


def test_temp_out_zero_survives_field_mapping() -> None:
    """temp_out_f == 0.0 appears as tempf=0.0 in the result (defect #6).

    The FieldMapper's value == None check must not treat 0.0 as missing.
    """
    mapper = FieldMapper(_WUNDERGROUND_MAP_PATH)
    result = mapper.map(_obs(temp_out_f=0.0))
    assert "tempf" in result
    assert result["tempf"] == "0.0"


# ---------------------------------------------------------------------------
# Windy sensor map (Phase 3)
# ---------------------------------------------------------------------------


def test_windy_yaml_loads() -> None:
    """windy.yaml is valid and FieldMapper initialises without error."""
    mapper = FieldMapper(_WINDY_MAP_PATH)
    assert mapper is not None


def test_windy_mapper_metric_values() -> None:
    """Windy mapper converts imperial inputs to metric outputs."""
    mapper = FieldMapper(_WINDY_MAP_PATH)
    result = mapper.map(
        _obs(
            temp_out_f=67.6,
            pressure_sea_level_inHg=29.92,
            wind_speed_mph=10.0,
            wind_gust_mph=15.0,
            rain_60min_in=0.5,
            humidity_pct=80.0,
            wind_dir_deg=180.0,
            uv_index=3.0,
            solar_rad_wm2=400.0,
            dew_point_f=50.0,
        )
    )
    # Transformed fields
    assert abs(float(result["temp"]) - 19.7778) < 0.01, f"temp={result['temp']}"
    assert abs(float(result["pressure"]) - 101320.76) < 1.0, (
        f"pressure={result['pressure']}"
    )
    assert abs(float(result["wind"]) - 4.4704) < 0.001, f"wind={result['wind']}"
    assert abs(float(result["gust"]) - 6.7056) < 0.001, f"gust={result['gust']}"
    assert abs(float(result["precip"]) - 12.7) < 0.001, f"precip={result['precip']}"
    assert abs(float(result["dewpoint"]) - 10.0) < 0.01, (
        f"dewpoint={result['dewpoint']}"
    )
    # Passthrough fields (no transform)
    assert result["humidity"] == "80.0"
    assert result["winddir"] == "180.0"
    assert result["uv"] == "3.0"
    assert result["solarradiation"] == "400.0"
    # Imperial fallback params must NOT be present
    assert "tempf" not in result
    assert "windspeedmph" not in result


def test_windy_mapper_no_imperial_fallback() -> None:
    """Windy result must not contain any imperial param names."""
    mapper = FieldMapper(_WINDY_MAP_PATH)
    result = mapper.map(_obs(temp_out_f=72.0, wind_speed_mph=5.0))
    for key in result:
        assert key not in {"tempf", "windspeedmph", "baromin", "rainin"}, (
            f"Imperial param {key!r} found in Windy output"
        )


def test_windy_zero_value_survives_transform() -> None:
    """temp_out_f=0.0 must be transformed and emitted (defect #6 with transform path).

    0.0°F = -17.7778°C — must appear in the output, not be skipped.
    """
    mapper = FieldMapper(_WINDY_MAP_PATH)
    result = mapper.map(_obs(temp_out_f=0.0))
    assert "temp" in result
    assert abs(float(result["temp"]) - (-17.7778)) < 0.01, f"temp={result['temp']}"
