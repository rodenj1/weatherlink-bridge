"""Entry point for the WeatherLink Bridge service.

Daemon lifecycle
----------------
``run()`` is the async entrypoint:

1. Load ``AppSettings`` — any ``ValidationError`` is caught and surfaced as a
   clean message; no traceback.
2. ``configure_logging`` — JSON in production, console in DEBUG/development.
3. ``start_metrics_server`` — Prometheus ``/metrics`` on ``METRICS_PORT``.
4. Build the collector and publishers via the factory.
5. Set startup metrics (``update_interval_seconds``, ``app_info``).
6. Loop: ``run_collection_cycle`` → interruptible sleep via
   ``asyncio.wait_for(stop_event.wait(), timeout=interval)``.

Graceful shutdown
-----------------
SIGTERM / SIGINT set ``_stop_event``.  If the signal arrives **during sleep**,
the daemon exits at the next ``asyncio.wait_for`` timeout (< 1 s for the test
harness; up to ``interval`` in prod — which is the documented behaviour).  If
the signal arrives **mid-cycle**, the in-flight cycle completes before the loop
checks the event.  This is intentional: a cycle is short (one HTTP fetch +
N publishes); letting it finish avoids partial data windows.

Liveness (``/healthz``)
------------------------
We do not stand up a second HTTP server.  Liveness is derived from the
``last_successful_cycle_timestamp`` Prometheus gauge on ``/metrics``.  A K8s
probe (Phase 5) compares that gauge to ``now - 2 * update_interval_seconds``.

``last_successful_cycle_timestamp`` advances on every **successful fetch**,
regardless of publisher outcomes.  A rate-limited (all-SKIPPED) cycle is
classified as ``"partial"``, not ``"error"``.  Publisher failures are alerted
separately via ``publish_total`` and must not gate liveness.

See ``metrics.py`` for the full rationale.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys
import time
from typing import TYPE_CHECKING, Protocol

import httpx
import structlog
from pydantic import ValidationError

from weatherlink_bridge import __version__
from weatherlink_bridge.collectors.weatherlink import WeatherLinkCollector
from weatherlink_bridge.exceptions import CollectorError
from weatherlink_bridge.logger import configure_logging
from weatherlink_bridge.metrics import (
    app_info,
    collection_run_duration_seconds,
    collection_run_total,
    last_successful_cycle_timestamp,
    publish_duration_seconds,
    publish_total,
    record_observation_metrics,
    start_metrics_server,
    update_interval_seconds,
    wl_fetch_duration_seconds,
    wl_fetch_total,
)
from weatherlink_bridge.publishers.base import BasePublisher, PublishResult

if TYPE_CHECKING:
    from weatherlink_bridge.models.observation import WeatherObservation
    from weatherlink_bridge.settings import AppSettings

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# CollectorProtocol
# ---------------------------------------------------------------------------


class CollectorProtocol(Protocol):
    """Structural protocol for weather data collectors."""

    async def fetch(self) -> WeatherObservation: ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Instrumented collection cycle
# ---------------------------------------------------------------------------


async def run_collection_cycle(
    collector: CollectorProtocol,
    publishers: list[BasePublisher],
) -> str:
    """Run one collect→publish cycle with full Prometheus instrumentation.

    Cycle status rules (``collection_run_total`` label):

    * Fetch failed (``CollectorError``) → ``"error"``.  Liveness timestamp
      is **not** advanced.
    * No publishers configured → ``"success"``.
    * All publishers returned ``SUCCESS`` → ``"success"``.
    * All publishers returned hard ``FAILURE`` (zero successes, zero skips)
      → ``"error"``.
    * Any other mix — including all-``SKIPPED``, or success+skip, or
      success+failure — → ``"partial"``.

    Liveness semantics: ``last_successful_cycle_timestamp`` is set right after
    every **successful fetch**, regardless of publisher outcomes.  Publisher
    failures are alerted separately via ``publish_total``; they must not gate
    liveness.  The only path that does NOT advance the timestamp is the
    ``CollectorError`` fetch-failure path.

    Skipped publishers (ADR 0007 backoff) are recorded with
    ``status="skipped"`` in ``publish_total``.

    Args:
        collector: A collector implementing ``async fetch() -> WeatherObservation``.
        publishers: Publishers to forward the observation to.

    Returns:
        One of ``"success"``, ``"partial"``, or ``"error"``.
    """
    cycle_start = time.monotonic()

    # --- Fetch ---------------------------------------------------------------
    station_id: str = "unknown"
    obs: WeatherObservation | None = None

    try:
        with wl_fetch_duration_seconds.time():
            obs = await collector.fetch()
        station_id = str(obs.station_id)
        wl_fetch_total.labels(station_id=station_id, status="success").inc()
    except CollectorError as exc:
        wl_fetch_total.labels(station_id=station_id, status="error").inc()
        log.error("collection_failed", error=str(exc))
        elapsed_ms = (time.monotonic() - cycle_start) * 1000
        collection_run_total.labels(status="error").inc()
        collection_run_duration_seconds.observe(time.monotonic() - cycle_start)
        log.error(
            "collection_cycle_complete",
            status="error",
            duration_ms=round(elapsed_ms, 1),
        )
        return "error"

    # --- Record observation metrics ------------------------------------------
    record_observation_metrics(obs)

    # --- Advance liveness timestamp (fetch succeeded) -----------------------
    last_successful_cycle_timestamp.set(time.time())

    # --- Publish -------------------------------------------------------------
    if not publishers:
        elapsed = time.monotonic() - cycle_start
        collection_run_total.labels(status="success").inc()
        collection_run_duration_seconds.observe(elapsed)
        log.info(
            "collection_cycle_complete",
            status="success",
            duration_ms=round(elapsed * 1000, 1),
        )
        return "success"

    success_count = 0
    failure_count = 0
    skip_count = 0
    for publisher in publishers:
        pub_start = time.monotonic()
        try:
            with publish_duration_seconds.labels(publisher=publisher.name).time():
                result = await publisher.publish(obs)
            pub_elapsed_ms = (time.monotonic() - pub_start) * 1000
            if result == PublishResult.SUCCESS:
                success_count += 1
                publish_total.labels(publisher=publisher.name, status="success").inc()
                log.debug(
                    "publish_ok",
                    publisher=publisher.name,
                    duration_ms=round(pub_elapsed_ms, 1),
                )
            elif result == PublishResult.SKIPPED:
                skip_count += 1
                publish_total.labels(publisher=publisher.name, status="skipped").inc()
                log.info("publish_skipped", publisher=publisher.name)
            else:
                failure_count += 1
                publish_total.labels(publisher=publisher.name, status="failure").inc()
                log.warning(
                    "publish_returned_failure",
                    publisher=publisher.name,
                    duration_ms=round(pub_elapsed_ms, 1),
                )
        except Exception as exc:
            failure_count += 1
            pub_elapsed_ms = (time.monotonic() - pub_start) * 1000
            publish_total.labels(publisher=publisher.name, status="failure").inc()
            log.error(
                "publish_error",
                publisher=publisher.name,
                error=str(exc),
                duration_ms=round(pub_elapsed_ms, 1),
            )

    # --- Determine cycle status ---------------------------------------------
    # all SUCCESS → "success"
    # all hard-failed (zero successes, zero skips) → "error"
    # everything else (any mix, all-skipped, success+skip, success+fail) → "partial"
    if success_count == len(publishers):
        cycle_status = "success"
    elif success_count == 0 and skip_count == 0:
        cycle_status = "error"
    else:
        cycle_status = "partial"

    elapsed = time.monotonic() - cycle_start
    collection_run_total.labels(status=cycle_status).inc()
    collection_run_duration_seconds.observe(elapsed)

    log.info(
        "collection_cycle_complete",
        status=cycle_status,
        success_count=success_count,
        failure_count=failure_count,
        skip_count=skip_count,
        total_publishers=len(publishers),
        duration_ms=round(elapsed * 1000, 1),
    )
    return cycle_status


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------


async def run(
    *,
    _settings: AppSettings | None = None,
    _stop_event: asyncio.Event | None = None,
) -> None:
    """Async daemon entrypoint.

    Loads settings, wires up the collector + publishers, starts the metrics
    server, then loops until ``_stop_event`` is set (via SIGTERM/SIGINT or
    test injection).

    Args:
        _settings: Pre-built AppSettings; if None, loads from environment.
            Injected in tests to avoid real env-var loading.
        _stop_event: Pre-built asyncio.Event for shutdown signalling.
            Injected in tests to control the loop lifecycle.
    """
    # Import here to avoid a circular-import chain at module level
    # (settings → (nothing); main → settings, metrics, publishers…).
    import weatherlink_bridge.publishers  # noqa: F401  # pyright: ignore[reportUnusedImport]
    from weatherlink_bridge.settings import AppSettings as _AppSettings

    # --- Settings -----------------------------------------------------------
    if _settings is None:
        try:
            settings = _AppSettings()  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]
        except ValidationError as exc:
            print(
                f"Configuration error: {exc}\n"
                "Check that all required environment variables are set.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        settings = _settings

    # --- Logging ------------------------------------------------------------
    development = settings.log_level.upper() == "DEBUG"
    configure_logging(settings.log_level, development=development)

    log.info(
        "service_starting",
        version=__version__,
        update_interval_mins=settings.update_interval_mins,
        metrics_port=settings.metrics_port,
    )

    # --- Metrics server -----------------------------------------------------
    start_metrics_server(settings.metrics_port)

    # --- Startup metrics ----------------------------------------------------
    interval_secs = settings.update_interval_mins * 60
    update_interval_seconds.set(interval_secs)
    app_info.info({"version": __version__})

    # --- Build collector + publishers ----------------------------------------
    from weatherlink_bridge.publishers.factory import PublisherFactory

    collector_client = httpx.AsyncClient()
    collector = WeatherLinkCollector(
        settings.weatherlink,
        collector_client,
    )
    publishers = PublisherFactory.create_all(settings)

    log.info(
        "service_ready",
        publishers=[p.name for p in publishers],
        interval_seconds=interval_secs,
    )

    # --- Stop event + signal handlers ----------------------------------------
    stop_event = _stop_event if _stop_event is not None else asyncio.Event()

    loop = asyncio.get_running_loop()

    def _handle_signal(sig: int) -> None:
        log.info("shutdown_signal_received", signal=signal.Signals(sig).name)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal, sig)

    # --- Main loop -----------------------------------------------------------
    try:
        while not stop_event.is_set():
            await run_collection_cycle(collector, publishers)

            # Interruptible sleep: exits immediately when stop_event fires.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=interval_secs)
    finally:
        # --- Graceful shutdown -----------------------------------------------
        for publisher in publishers:
            try:
                await publisher.close()
            except Exception as exc:
                log.warning(
                    "publisher_close_error",
                    publisher=publisher.name,
                    error=str(exc),
                )
        try:
            await collector_client.aclose()
        except Exception as exc:
            log.warning("collector_client_close_error", error=str(exc))
        log.info("shutdown_complete")


# ---------------------------------------------------------------------------
# Sync console-script entry point
# ---------------------------------------------------------------------------


def main(args: list[str] | None = None) -> None:
    """Parse command-line arguments and start the bridge service.

    This is the console-script entry point registered in ``pyproject.toml``.
    It is intentionally thin: validates CLI flags, then hands off to
    ``asyncio.run(run())``.

    Args:
        args: Argument list (defaults to sys.argv[1:] when None).
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="weatherlink-bridge",
        description="WeatherLink PWS bridge service forwarding to Weather Underground and Windy.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.parse_args(args)

    with contextlib.suppress(KeyboardInterrupt):
        # asyncio.run() re-raises KeyboardInterrupt after cancellation; swallow
        # it here for a clean exit (SIGINT is already handled inside run()).
        asyncio.run(run())


if __name__ == "__main__":
    main()
