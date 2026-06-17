"""Prometheus metrics for WeatherLink Bridge.

All metric objects are defined at **module import time** so they are registered
with the default CollectorRegistry exactly once.  Never define metrics inside
functions — the default registry rejects duplicate registrations.

Health / liveness approach (Phase 4 decision):
  We do NOT stand up a second HTTP server for ``/healthz``.  Instead, the
  ``last_successful_cycle_timestamp`` gauge is set to the Unix epoch of the
  most-recent **successful WeatherLink fetch** (regardless of publisher
  outcomes).  A Kubernetes liveness probe (Phase 5) queries ``/metrics`` on
  ``METRICS_PORT`` and alerts if this gauge is older than
  ``2 * update_interval_seconds``.  This avoids a second port and keeps all
  observability on one endpoint.

  Liveness semantics: ``last_successful_cycle_timestamp`` advances on every
  successful fetch.  Publisher failures are alerted separately via
  ``publish_total`` and do **not** gate liveness.  A rate-limited (all-SKIPPED)
  cycle is classified as ``"partial"``, not ``"error"``.
"""

from __future__ import annotations

import structlog
from prometheus_client import Counter, Gauge, Histogram, Info, start_http_server

from weatherlink_bridge.models.observation import WeatherObservation

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Collector metrics
# ---------------------------------------------------------------------------

wl_fetch_total: Counter = Counter(
    "wl_fetch_total",
    "Total WeatherLink API fetch attempts, labelled by outcome.",
    ["station_id", "status"],  # status: success | error
)

wl_fetch_duration_seconds: Histogram = Histogram(
    "wl_fetch_duration_seconds",
    "Elapsed time for WeatherLink API fetch calls.",
)

# ---------------------------------------------------------------------------
# Publisher metrics
# ---------------------------------------------------------------------------

publish_total: Counter = Counter(
    "publish_total",
    "Total publisher attempts, labelled by publisher name and outcome.",
    ["publisher", "status"],  # status: success | failure | skipped
)

publish_duration_seconds: Histogram = Histogram(
    "publish_duration_seconds",
    "Elapsed time for publisher calls.",
    ["publisher"],
)

# ---------------------------------------------------------------------------
# Collection-cycle metrics
# ---------------------------------------------------------------------------

collection_run_total: Counter = Counter(
    "collection_run_total",
    "Total collection cycle runs, labelled by outcome.",
    ["status"],  # status: success | partial | error
)

collection_run_duration_seconds: Histogram = Histogram(
    "collection_run_duration_seconds",
    "Elapsed time for a full collect-and-publish cycle.",
)

# ---------------------------------------------------------------------------
# Configuration / liveness gauges
# ---------------------------------------------------------------------------

update_interval_seconds: Gauge = Gauge(
    "update_interval_seconds",
    "Configured collection interval in seconds.",
)

last_successful_cycle_timestamp: Gauge = Gauge(
    "last_successful_cycle_timestamp",
    "Unix timestamp of the last fully-successful collection cycle. "
    "Used as a liveness signal: if this is older than "
    "2 * update_interval_seconds the service may be stalled.",
)

# ---------------------------------------------------------------------------
# Per-field observation gauge
# ---------------------------------------------------------------------------

observation_value: Gauge = Gauge(
    "observation_value",
    "Latest numeric weather observation value, labelled by field name.",
    ["field", "station_id"],
)

# ---------------------------------------------------------------------------
# Application info
# ---------------------------------------------------------------------------

app_info: Info = Info(
    "weatherlink_bridge",
    "Application build info (version, etc.).",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def record_observation_metrics(obs: WeatherObservation) -> None:
    """Set ``observation_value`` gauges for every numeric weather field.

    Iterates ``obs.model_dump()`` and records only fields whose values are
    ``int`` or ``float`` (and not ``None``).  The identity fields
    ``timestamp`` and ``station_id`` are explicitly skipped.

    Args:
        obs: The canonical weather observation to record.
    """
    skip_fields = {"timestamp", "station_id"}
    station_id = str(obs.station_id)

    for field, value in obs.model_dump().items():
        if field in skip_fields:
            continue
        if value is None:
            continue
        if not isinstance(value, (int, float)):
            continue  # pragma: no cover — WeatherObservation has no non-numeric non-skipped fields
        observation_value.labels(field=field, station_id=station_id).set(float(value))


def start_metrics_server(port: int) -> None:
    """Start the Prometheus HTTP metrics server on the given port.

    Wraps ``prometheus_client.start_http_server``.  Call once at startup.

    Args:
        port: TCP port to listen on (default ``METRICS_PORT`` env var → 8080).
    """
    start_http_server(port)
    log.info("metrics_server_started", port=port)
