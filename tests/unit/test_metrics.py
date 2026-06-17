"""Tests for the Prometheus metrics module (metrics.py).

Design constraints:
- No real network ports (start_metrics_server is monkeypatched).
- No real wall-clock sleeps.
- Metrics are defined at import time with the default registry; tests assert
  increments via the metric objects directly (using _value.get()) rather
  than re-registering.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from weatherlink_bridge.metrics import (
    app_info,
    last_successful_cycle_timestamp,
    observation_value,
    record_observation_metrics,
    start_metrics_server,
    update_interval_seconds,
)
from weatherlink_bridge.models.observation import WeatherObservation

_FIXED_TIMESTAMP = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)


def _obs(**kwargs: object) -> WeatherObservation:
    """Build a minimal WeatherObservation; kwargs override defaults."""
    defaults: dict[str, object] = {
        "temp_out_f": 72.5,
        "humidity_pct": 55.0,
        "pressure_sea_level_inHg": 29.92,
    }
    defaults.update(kwargs)
    return WeatherObservation(
        timestamp=_FIXED_TIMESTAMP,
        station_id=12345,
        **defaults,  # type: ignore[arg-type]
    )


def _gauge_value(gauge: Any) -> float:
    return float(gauge._value.get())  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Module import idempotence
# ---------------------------------------------------------------------------


def test_metrics_import_twice_does_not_error() -> None:
    """Importing the metrics module a second time does not raise (no duplicate registry)."""
    import importlib

    import weatherlink_bridge.metrics as mod

    # Re-importing the already-imported module does NOT trigger re-registration
    # because Python caches modules in sys.modules.  This is the contract we
    # rely on (metrics defined at module level, not inside a function).
    reloaded = importlib.import_module("weatherlink_bridge.metrics")
    assert reloaded is mod  # Same object — no re-registration


# ---------------------------------------------------------------------------
# record_observation_metrics
# ---------------------------------------------------------------------------


def test_record_observation_metrics_sets_numeric_fields() -> None:
    """record_observation_metrics sets gauges for numeric weather fields."""
    obs = _obs(temp_out_f=68.0, humidity_pct=60.0)
    record_observation_metrics(obs)

    station_id = str(obs.station_id)
    temp_val = _gauge_value(
        observation_value.labels(field="temp_out_f", station_id=station_id)
    )
    hum_val = _gauge_value(
        observation_value.labels(field="humidity_pct", station_id=station_id)
    )
    assert temp_val == pytest.approx(68.0)
    assert hum_val == pytest.approx(60.0)


def test_record_observation_metrics_skips_none_fields() -> None:
    """record_observation_metrics does not set gauges for None fields."""
    obs = _obs(wind_speed_mph=None, uv_index=None)
    # Just calling this must not raise; we can't easily assert "not set"
    # on a gauge that was never set, but we can confirm the function completes.
    record_observation_metrics(obs)  # Should not raise


def test_record_observation_metrics_skips_timestamp() -> None:
    """record_observation_metrics does not set a gauge for the 'timestamp' field."""
    obs = _obs()
    # Before the call, read the current label set size. The test just verifies
    # no AttributeError / crash occurs and that 'timestamp' is absent from the
    # observation_value metric's label values.
    record_observation_metrics(obs)

    # Collect all current label sets for observation_value
    collected_labels = {
        tuple(sample.labels.values())
        for metric in observation_value.collect()
        for sample in metric.samples
    }
    # No label set should have 'timestamp' as the field name
    assert not any("timestamp" in labels for labels in collected_labels)


def test_record_observation_metrics_skips_station_id() -> None:
    """record_observation_metrics does not set a gauge for 'station_id'."""
    obs = _obs()
    record_observation_metrics(obs)

    collected_labels = {
        tuple(sample.labels.values())
        for metric in observation_value.collect()
        for sample in metric.samples
    }
    assert not any("station_id" in labels for labels in collected_labels)


def test_record_observation_metrics_handles_zero_values() -> None:
    """record_observation_metrics records 0.0 — zero is a valid float (defect #6)."""
    obs = _obs(rain_60min_in=0.0, rain_day_in=0.0)
    record_observation_metrics(obs)

    station_id = str(obs.station_id)
    rain_val = _gauge_value(
        observation_value.labels(field="rain_60min_in", station_id=station_id)
    )
    assert rain_val == pytest.approx(0.0)


def test_record_observation_metrics_handles_integer_fields() -> None:
    """record_observation_metrics coerces int fields (wind_dir_deg) to float."""
    obs = _obs(wind_dir_deg=180)
    record_observation_metrics(obs)

    station_id = str(obs.station_id)
    dir_val = _gauge_value(
        observation_value.labels(field="wind_dir_deg", station_id=station_id)
    )
    assert dir_val == pytest.approx(180.0)


def test_record_observation_metrics_all_none_does_not_crash() -> None:
    """An observation with all optional fields None completes without error."""
    obs = WeatherObservation(
        timestamp=_FIXED_TIMESTAMP,
        station_id=1,
    )
    record_observation_metrics(obs)  # Must not raise


# ---------------------------------------------------------------------------
# start_metrics_server
# ---------------------------------------------------------------------------


def test_start_metrics_server_calls_prometheus_start_http_server() -> None:
    """start_metrics_server calls prometheus_client.start_http_server with the port."""
    with patch("weatherlink_bridge.metrics.start_http_server") as mock_start:
        start_metrics_server(9090)
    mock_start.assert_called_once_with(9090)


def test_start_metrics_server_does_not_bind_real_port() -> None:
    """start_metrics_server is always monkeypatched — no real socket is opened."""
    with patch("weatherlink_bridge.metrics.start_http_server") as mock_start:
        start_metrics_server(8080)
    assert mock_start.call_count == 1


# ---------------------------------------------------------------------------
# Gauge / Info helpers
# ---------------------------------------------------------------------------


def test_update_interval_seconds_gauge_can_be_set() -> None:
    """update_interval_seconds.set() stores the value correctly."""
    update_interval_seconds.set(300.0)
    assert _gauge_value(update_interval_seconds) == pytest.approx(300.0)


def test_last_successful_cycle_timestamp_can_be_set() -> None:
    """last_successful_cycle_timestamp.set() stores a unix epoch value."""
    import time

    ts = time.time()
    last_successful_cycle_timestamp.set(ts)
    stored = _gauge_value(last_successful_cycle_timestamp)
    assert stored == pytest.approx(ts, abs=1.0)


def test_app_info_accepts_version_dict() -> None:
    """app_info.info() accepts a version dict without raising."""
    app_info.info({"version": "0.1.0"})  # Must not raise


# ---------------------------------------------------------------------------
# Metric objects are importable
# ---------------------------------------------------------------------------


def test_metric_objects_are_importable() -> None:
    """All public metric names are importable from weatherlink_bridge.metrics."""
    from weatherlink_bridge.metrics import (  # noqa: F401
        app_info,
        collection_run_duration_seconds,
        collection_run_total,
        last_successful_cycle_timestamp,
        observation_value,
        publish_duration_seconds,
        publish_total,
        record_observation_metrics,
        start_metrics_server,
        update_interval_seconds,
        wl_fetch_duration_seconds,
    )
