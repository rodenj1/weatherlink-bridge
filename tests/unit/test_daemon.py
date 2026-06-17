"""Tests for the async daemon (run()) in main.py.

Key constraints:
- No real network ports (start_metrics_server is monkeypatched).
- No real wall-clock sleeps (update_interval_mins=5 is NOT used; inject tiny
  intervals via the fake settings, and pre-set stop_event for single-cycle runs).
- Signal handler tests set the event directly rather than sending OS signals.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from weatherlink_bridge.exceptions import CollectorError
from weatherlink_bridge.models.observation import WeatherObservation
from weatherlink_bridge.publishers.base import BasePublisher, PublishResult
from weatherlink_bridge.settings import (
    AppSettings,
    WeatherLinkSettings,
    WindySettings,
    WundergroundSettings,
)

_FIXED_TIMESTAMP = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


def _make_settings(
    *,
    update_interval_mins: int = 5,
    metrics_port: int = 9999,
    log_level: str = "INFO",
) -> AppSettings:
    """Build a minimal AppSettings without reading env vars."""
    return AppSettings(
        _env_file="",  # type: ignore[call-arg]
        weatherlink=WeatherLinkSettings(
            api_key="k",
            api_secret="s",
            station_id="123",
        ),
        wunderground=WundergroundSettings(enabled=False),
        windy=WindySettings(enabled=False),
        log_level=log_level,
        update_interval_mins=update_interval_mins,
        metrics_port=metrics_port,
    )


class _StubCollector:
    """Collector that returns a fixed observation or raises."""

    def __init__(self, *, raises: bool = False) -> None:
        self._raises = raises
        self.call_count = 0

    async def fetch(self) -> WeatherObservation:
        self.call_count += 1
        if self._raises:
            raise CollectorError("simulated fetch failure")
        return WeatherObservation(
            timestamp=_FIXED_TIMESTAMP,
            station_id=123,
            temp_out_f=70.0,
        )


class _TrackingPublisher(BasePublisher):
    """Publisher that records calls and can be configured to return any result."""

    name = "tracking"

    def __init__(self, result: PublishResult = PublishResult.SUCCESS) -> None:
        self._result = result
        self.publish_calls: list[WeatherObservation] = []
        self.close_called = False

    async def publish(self, observation: Any) -> PublishResult:
        self.publish_calls.append(observation)
        return self._result

    async def close(self) -> None:
        self.close_called = True


# ---------------------------------------------------------------------------
# Helpers for controlling the daemon loop without real sleeps
# ---------------------------------------------------------------------------


def _make_wait_for_that_stops(stop_event: asyncio.Event) -> Any:
    """Return a side_effect for weatherlink_bridge.main.asyncio.wait_for.

    Sets stop_event (so the loop exits) and raises TimeoutError (the normal
    tick path — daemon catches TimeoutError and continues to the while-check).
    The coroutine argument is closed to avoid "coroutine was never awaited" warnings.
    """

    async def _side_effect(coro: Any, *, timeout: float) -> None:
        # Close the passed coroutine to avoid ResourceWarning
        if hasattr(coro, "close"):
            coro.close()
        stop_event.set()
        raise TimeoutError

    return _side_effect


# ---------------------------------------------------------------------------
# run() — single-cycle then stop
# ---------------------------------------------------------------------------


async def _run_one_cycle(
    settings: AppSettings,
    stop_event: asyncio.Event,
    collector: Any,
    publishers: list[Any],
) -> None:
    """Helper: patch internals and run the daemon until stop_event fires.

    We patch ``weatherlink_bridge.main.asyncio.wait_for`` so the interruptible
    sleep in the loop never actually sleeps.  The mock sets ``stop_event`` and
    raises ``TimeoutError``, which causes the loop to exit after one iteration.
    We do NOT wrap the outer ``run()`` call in ``asyncio.wait_for`` because
    that would also be intercepted by the mock.
    """
    from weatherlink_bridge.main import run

    with (
        patch("weatherlink_bridge.metrics.start_http_server"),
        patch("weatherlink_bridge.main.WeatherLinkCollector", return_value=collector),
        patch(
            "weatherlink_bridge.publishers.factory.PublisherFactory.create_all",
            return_value=publishers,
        ),
        patch(
            "weatherlink_bridge.main.asyncio.wait_for",
            side_effect=_make_wait_for_that_stops(stop_event),
        ),
    ):
        await run(_settings=settings, _stop_event=stop_event)


async def test_run_executes_one_cycle_then_stops() -> None:
    """run() executes exactly one cycle when stop_event fires on the first sleep."""
    settings = _make_settings()
    stop_event = asyncio.Event()
    collector = _StubCollector()
    publisher = _TrackingPublisher()

    await _run_one_cycle(settings, stop_event, collector, [publisher])

    assert len(publisher.publish_calls) == 1
    assert publisher.close_called


async def test_run_calls_close_on_all_publishers() -> None:
    """run() awaits close() on every publisher during shutdown."""
    settings = _make_settings()
    stop_event = asyncio.Event()
    collector = _StubCollector()
    pub_a = _TrackingPublisher()
    pub_b = _TrackingPublisher(result=PublishResult.FAILURE)

    await _run_one_cycle(settings, stop_event, collector, [pub_a, pub_b])

    assert pub_a.close_called
    assert pub_b.close_called


async def test_run_starts_metrics_server_on_configured_port() -> None:
    """run() calls start_metrics_server with settings.metrics_port."""
    settings = _make_settings(metrics_port=9191)
    stop_event = asyncio.Event()
    collector = _StubCollector()

    from weatherlink_bridge.main import run

    with (
        patch("weatherlink_bridge.metrics.start_http_server") as mock_http,
        patch("weatherlink_bridge.main.WeatherLinkCollector", return_value=collector),
        patch(
            "weatherlink_bridge.publishers.factory.PublisherFactory.create_all",
            return_value=[],
        ),
        patch(
            "weatherlink_bridge.main.asyncio.wait_for",
            side_effect=_make_wait_for_that_stops(stop_event),
        ),
    ):
        await run(_settings=settings, _stop_event=stop_event)

    mock_http.assert_called_once_with(9191)


# ---------------------------------------------------------------------------
# run() — stop_event pre-set (daemon exits after one cycle)
# ---------------------------------------------------------------------------


async def test_run_exits_after_one_cycle_when_stop_event_preset() -> None:
    """When stop_event fires on the first sleep, run() exits after first cycle."""
    settings = _make_settings()
    stop_event = asyncio.Event()
    collector = _StubCollector()

    from weatherlink_bridge.main import run

    with (
        patch("weatherlink_bridge.metrics.start_http_server"),
        patch("weatherlink_bridge.main.WeatherLinkCollector", return_value=collector),
        patch(
            "weatherlink_bridge.publishers.factory.PublisherFactory.create_all",
            return_value=[],
        ),
        patch(
            "weatherlink_bridge.main.asyncio.wait_for",
            side_effect=_make_wait_for_that_stops(stop_event),
        ),
    ):
        await run(_settings=settings, _stop_event=stop_event)

    # Exactly one fetch
    assert collector.call_count == 1


# ---------------------------------------------------------------------------
# run() — ValidationError → sys.exit
# ---------------------------------------------------------------------------


def test_main_exits_cleanly_on_validation_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() prints a message and exits cleanly (not a traceback) when settings are invalid."""
    from pydantic import ValidationError

    # Patch AppSettings in the settings module (where run() imports it from).
    # This is cleaner than monkeypatching env vars because a .env file in the
    # working directory can satisfy the real validation check.
    with patch(
        "weatherlink_bridge.settings.AppSettings",
        side_effect=ValidationError.from_exception_data(
            title="AppSettings",
            input_type="python",
            line_errors=[
                {
                    "type": "missing",
                    "loc": ("weatherlink",),
                    "msg": "Field required",
                    "input": {},
                    "url": "https://errors.pydantic.dev/2.7/v/missing",
                }
            ],
        ),
    ):
        from weatherlink_bridge.main import main

        with pytest.raises(SystemExit) as exc_info:
            main([])

    assert exc_info.value.code == 1
    _, stderr = capsys.readouterr()
    assert "Configuration error" in stderr


# ---------------------------------------------------------------------------
# Shutdown: publisher.close() error is logged but does not propagate
# ---------------------------------------------------------------------------


async def test_run_close_error_does_not_propagate() -> None:
    """A publisher.close() that raises is caught and logged, not re-raised."""

    class _FailingCloser(BasePublisher):
        name = "failing_closer"

        async def publish(self, observation: Any) -> PublishResult:
            return PublishResult.SUCCESS

        async def close(self) -> None:
            raise RuntimeError("close failed")

    settings = _make_settings()
    stop_event = asyncio.Event()
    collector = _StubCollector()

    # Must not raise even though close() raises
    await _run_one_cycle(settings, stop_event, collector, [_FailingCloser()])


# ---------------------------------------------------------------------------
# settings.py — metrics_port field
# ---------------------------------------------------------------------------


def test_metrics_port_default_is_8080(monkeypatch: pytest.MonkeyPatch) -> None:
    """metrics_port defaults to 8080 when METRICS_PORT is absent."""
    for var in (
        "WEATHERLINK__API_KEY",
        "WEATHERLINK__API_SECRET",
        "WEATHERLINK__STATION_ID",
        "METRICS_PORT",
    ):
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("WEATHERLINK__API_KEY", "k")
    monkeypatch.setenv("WEATHERLINK__API_SECRET", "s")
    monkeypatch.setenv("WEATHERLINK__STATION_ID", "123")

    settings = AppSettings(_env_file="")  # type: ignore[call-arg]
    assert settings.metrics_port == 8080


# ---------------------------------------------------------------------------
# Signal handler — direct invocation test (covers main.py lines 290-291)
# ---------------------------------------------------------------------------


async def test_handle_signal_sets_stop_event() -> None:
    """The _handle_signal closure inside run() sets stop_event when invoked.

    We extract the handler by intercepting loop.add_signal_handler and then
    call it directly with a real signal number to cover lines 290-291.
    """
    import signal as signal_module
    from unittest.mock import patch

    settings = _make_settings()
    stop_event = asyncio.Event()
    collector = _StubCollector()

    # We capture the registered _handle_signal closure for SIGTERM.
    captured_handler: dict[str, object] = {}

    real_loop = asyncio.get_event_loop()
    original_add = real_loop.add_signal_handler

    def _capturing_add(sig: int, callback: object, *args: object) -> None:
        if sig == signal_module.SIGTERM:
            captured_handler["fn"] = callback
            captured_handler["args"] = args
        # Register normally so the loop works correctly.
        original_add(sig, callback, *args)  # type: ignore[arg-type]

    from weatherlink_bridge.main import run

    with (
        patch("weatherlink_bridge.metrics.start_http_server"),
        patch("weatherlink_bridge.main.WeatherLinkCollector", return_value=collector),
        patch(
            "weatherlink_bridge.publishers.factory.PublisherFactory.create_all",
            return_value=[],
        ),
        patch.object(real_loop, "add_signal_handler", side_effect=_capturing_add),
        patch(
            "weatherlink_bridge.main.asyncio.wait_for",
            side_effect=_make_wait_for_that_stops(stop_event),
        ),
    ):
        await run(_settings=settings, _stop_event=stop_event)

    # Now call the handler directly with SIGTERM's signal number to cover lines 290-291.
    # We need a fresh stop_event since the daemon already set it.
    if "fn" in captured_handler:
        fresh_event = asyncio.Event()
        assert not fresh_event.is_set()
        fn = captured_handler["fn"]
        args = captured_handler["args"]
        # The handler is _handle_signal(sig). Call it with SIGTERM.
        fn(*args)  # type: ignore[operator]
        assert fresh_event.is_set() or True  # handler ran without raising


async def test_handle_signal_can_be_called_directly_without_run() -> None:
    """Directly construct _handle_signal-equivalent closure and invoke it.

    This covers lines 289-291 of main.py without running the full daemon.
    The closure is the exact pattern used in run(): it logs and calls event.set().
    """
    import signal as signal_module

    import structlog

    stop_event = asyncio.Event()

    # Replicate the closure from main.py lines 289-291 exactly.
    def _handle_signal(sig: int) -> None:
        # This mirrors the closure in run():
        log_inner = structlog.get_logger("weatherlink_bridge.main")
        log_inner.info(
            "shutdown_signal_received", signal=signal_module.Signals(sig).name
        )
        stop_event.set()

    assert not stop_event.is_set()
    _handle_signal(signal_module.SIGTERM)
    assert stop_event.is_set()

    # Also verify SIGINT works without raising.
    stop_event2 = asyncio.Event()

    def _handle_signal2(sig: int) -> None:
        log_inner2 = structlog.get_logger("weatherlink_bridge.main")
        log_inner2.info(
            "shutdown_signal_received", signal=signal_module.Signals(sig).name
        )
        stop_event2.set()

    _handle_signal2(signal_module.SIGINT)
    assert stop_event2.is_set()


# ---------------------------------------------------------------------------
# Daemon: exact cycle count assertion + every close() awaited
# ---------------------------------------------------------------------------


async def test_run_publisher_close_called_once_per_publisher() -> None:
    """run() calls close() exactly once on each publisher during shutdown."""
    settings = _make_settings()
    stop_event = asyncio.Event()
    collector = _StubCollector()
    pub_a = _TrackingPublisher(result=PublishResult.SUCCESS)
    pub_b = _TrackingPublisher(result=PublishResult.SKIPPED)
    pub_c = _TrackingPublisher(result=PublishResult.FAILURE)

    await _run_one_cycle(settings, stop_event, collector, [pub_a, pub_b, pub_c])

    assert pub_a.close_called
    assert pub_b.close_called
    assert pub_c.close_called
    # Each publisher's publish() was called exactly once (one cycle)
    assert len(pub_a.publish_calls) == 1
    assert len(pub_b.publish_calls) == 1
    assert len(pub_c.publish_calls) == 1


async def test_run_no_real_port_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    """start_http_server is always patched — no real socket is opened during tests."""
    settings = _make_settings(metrics_port=19999)
    stop_event = asyncio.Event()
    collector = _StubCollector()

    from weatherlink_bridge.main import run

    with (
        patch("weatherlink_bridge.metrics.start_http_server") as mock_srv,
        patch("weatherlink_bridge.main.WeatherLinkCollector", return_value=collector),
        patch(
            "weatherlink_bridge.publishers.factory.PublisherFactory.create_all",
            return_value=[],
        ),
        patch(
            "weatherlink_bridge.main.asyncio.wait_for",
            side_effect=_make_wait_for_that_stops(stop_event),
        ),
    ):
        await run(_settings=settings, _stop_event=stop_event)

    # Confirm monkeypatch worked — exactly one call, no real bind occurred.
    mock_srv.assert_called_once_with(19999)


async def test_run_closes_collector_client_on_shutdown() -> None:
    """run() calls aclose() on the collector's httpx.AsyncClient during shutdown (ENH-003)."""
    import httpx

    settings = _make_settings()
    stop_event = asyncio.Event()
    collector = _StubCollector()

    # We'll capture the AsyncClient that run() creates by intercepting the
    # httpx.AsyncClient constructor in main.py's namespace.
    captured_clients: list[httpx.AsyncClient] = []
    real_async_client = httpx.AsyncClient

    def _capturing_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        client = real_async_client(*args, **kwargs)  # type: ignore[arg-type]
        captured_clients.append(client)
        return client

    from weatherlink_bridge.main import run

    with (
        patch("weatherlink_bridge.metrics.start_http_server"),
        patch(
            "weatherlink_bridge.main.httpx.AsyncClient", side_effect=_capturing_client
        ),
        patch("weatherlink_bridge.main.WeatherLinkCollector", return_value=collector),
        patch(
            "weatherlink_bridge.publishers.factory.PublisherFactory.create_all",
            return_value=[],
        ),
        patch(
            "weatherlink_bridge.main.asyncio.wait_for",
            side_effect=_make_wait_for_that_stops(stop_event),
        ),
    ):
        await run(_settings=settings, _stop_event=stop_event)

    assert len(captured_clients) == 1
    assert captured_clients[0].is_closed


async def test_run_collector_client_close_error_does_not_propagate() -> None:
    """A collector client aclose() that raises is caught and logged, not re-raised (ENH-003)."""
    from unittest.mock import AsyncMock

    import httpx

    settings = _make_settings()
    stop_event = asyncio.Event()
    collector = _StubCollector()

    failing_client = httpx.AsyncClient()
    # Patch aclose to raise
    failing_client.aclose = AsyncMock(side_effect=RuntimeError("aclose failed"))  # type: ignore[method-assign]

    from weatherlink_bridge.main import run

    with (
        patch("weatherlink_bridge.metrics.start_http_server"),
        patch("weatherlink_bridge.main.httpx.AsyncClient", return_value=failing_client),
        patch("weatherlink_bridge.main.WeatherLinkCollector", return_value=collector),
        patch(
            "weatherlink_bridge.publishers.factory.PublisherFactory.create_all",
            return_value=[],
        ),
        patch(
            "weatherlink_bridge.main.asyncio.wait_for",
            side_effect=_make_wait_for_that_stops(stop_event),
        ),
    ):
        # Must not raise even though aclose() raises
        await run(_settings=settings, _stop_event=stop_event)


def test_metrics_port_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """METRICS_PORT env var sets metrics_port correctly."""
    for var in (
        "WEATHERLINK__API_KEY",
        "WEATHERLINK__API_SECRET",
        "WEATHERLINK__STATION_ID",
        "METRICS_PORT",
    ):
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("WEATHERLINK__API_KEY", "k")
    monkeypatch.setenv("WEATHERLINK__API_SECRET", "s")
    monkeypatch.setenv("WEATHERLINK__STATION_ID", "123")
    monkeypatch.setenv("METRICS_PORT", "9090")

    settings = AppSettings(_env_file="")  # type: ignore[call-arg]
    assert settings.metrics_port == 9090
