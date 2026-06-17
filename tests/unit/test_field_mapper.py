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


def test_transform_raises_mapping_error(tmp_path: Path) -> None:
    """A sensor map with a transform field raises MappingError at init time."""
    yaml_content = """\
fields:
  temp_out_f:
    target: tempf
    transform: f_to_c
"""
    map_file = tmp_path / "bad_map.yaml"
    map_file.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(MappingError, match="transforms not yet implemented"):
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
# Task 4: windy.yaml placeholder → MappingError at init
# ---------------------------------------------------------------------------

_WINDY_MAP_PATH = Path(__file__).parents[2] / "config" / "sensor_maps" / "windy.yaml"


def test_windy_yaml_placeholder_raises_mapping_error() -> None:
    """windy.yaml contains only comments (no fields key) — FieldMapper must raise.

    Phase 3 is not yet implemented. The placeholder YAML parses to None after
    yaml.safe_load (all comments, no data), which fails SensorMapConfig schema
    validation → MappingError.  This confirms the eager-rejection behaviour
    works for a map with no usable content.
    """
    with pytest.raises(MappingError, match="schema validation"):
        FieldMapper(_WINDY_MAP_PATH)
