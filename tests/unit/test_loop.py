"""Tests for the run_collection_cycle function in main.py."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from weatherlink_bridge.exceptions import CollectorError
from weatherlink_bridge.main import run_collection_cycle
from weatherlink_bridge.models.observation import WeatherObservation
from weatherlink_bridge.publishers.base import PublishResult

_FIXED_TIMESTAMP = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)

_SAMPLE_OBS = WeatherObservation(
    timestamp=_FIXED_TIMESTAMP,
    station_id=99999,
    temp_out_f=70.0,
)


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------


class _StubCollector:
    """Collector stub that returns a fixed observation or raises."""

    def __init__(self, *, raises: bool = False) -> None:
        self._raises = raises

    async def fetch(self) -> WeatherObservation:
        if self._raises:
            raise CollectorError("Simulated collection failure")
        return _SAMPLE_OBS


class _StubPublisher:
    """Publisher stub that returns a fixed PublishResult or raises."""

    name = "stub"

    def __init__(
        self,
        *,
        result: PublishResult = PublishResult.SUCCESS,
        raises: bool = False,
    ) -> None:
        self._result = result
        self._raises = raises
        self.called = False

    async def publish(self, observation: Any) -> PublishResult:
        self.called = True
        if self._raises:
            raise RuntimeError("Simulated publish failure")
        return self._result

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Tests — cycle outcomes
# ---------------------------------------------------------------------------


async def test_cycle_all_success() -> None:
    """All publishers succeed → 'success'."""
    collector = _StubCollector()
    publishers = [
        _StubPublisher(result=PublishResult.SUCCESS),
        _StubPublisher(result=PublishResult.SUCCESS),
    ]
    result = await run_collection_cycle(collector, publishers)
    assert result == "success"


async def test_cycle_partial_success() -> None:
    """One publisher SUCCESS, one FAILURE → 'partial'."""
    collector = _StubCollector()
    publishers = [
        _StubPublisher(result=PublishResult.SUCCESS),
        _StubPublisher(result=PublishResult.FAILURE),
    ]
    result = await run_collection_cycle(collector, publishers)
    assert result == "partial"


async def test_cycle_all_publishers_fail() -> None:
    """All publishers return FAILURE → 'error'."""
    collector = _StubCollector()
    publishers = [
        _StubPublisher(result=PublishResult.FAILURE),
        _StubPublisher(result=PublishResult.FAILURE),
    ]
    result = await run_collection_cycle(collector, publishers)
    assert result == "error"


async def test_cycle_collector_error() -> None:
    """CollectorError → 'error'; publishers are not called."""
    collector = _StubCollector(raises=True)
    pub = _StubPublisher()
    result = await run_collection_cycle(collector, [pub])
    assert result == "error"
    assert not pub.called


async def test_cycle_no_publishers_returns_success() -> None:
    """Empty publisher list still returns 'success' after collection."""
    collector = _StubCollector()
    result = await run_collection_cycle(collector, [])
    assert result == "success"


async def test_cycle_one_publisher_exception_does_not_stop_others() -> None:
    """An exception in the first publisher does not prevent the second from running."""
    collector = _StubCollector()
    first = _StubPublisher(raises=True)
    second = _StubPublisher(result=PublishResult.SUCCESS)
    result = await run_collection_cycle(collector, [first, second])

    # Second publisher must have been called
    assert second.called
    # First raised, second succeeded → partial (1 success out of 2)
    assert result == "partial"


async def test_cycle_publisher_exception_counts_as_failure() -> None:
    """A publisher that raises contributes to the failure count."""
    collector = _StubCollector()
    first = _StubPublisher(raises=True)
    result = await run_collection_cycle(collector, [first])
    # 1 publisher, 0 successes → error
    assert result == "error"


async def test_cycle_skipped_publisher_counts_as_non_success() -> None:
    """A SKIPPED publisher does not count as a success → 'partial' if any succeed."""
    collector = _StubCollector()
    # One success, one skipped → partial (skipped ≠ success)
    publishers = [
        _StubPublisher(result=PublishResult.SUCCESS),
        _StubPublisher(result=PublishResult.SKIPPED),
    ]
    result = await run_collection_cycle(collector, publishers)
    assert result == "partial"


async def test_cycle_all_skipped_is_partial() -> None:
    """All publishers SKIPPED → 'partial' (fetch succeeded, no hard failures)."""
    collector = _StubCollector()
    publishers = [
        _StubPublisher(result=PublishResult.SKIPPED),
        _StubPublisher(result=PublishResult.SKIPPED),
    ]
    result = await run_collection_cycle(collector, publishers)
    assert result == "partial"


# ---------------------------------------------------------------------------
# Tests — Prometheus metric instrumentation
# ---------------------------------------------------------------------------


async def test_cycle_success_increments_wl_fetch_total_success() -> None:
    """A successful fetch increments wl_fetch_total{status='success'}."""
    from weatherlink_bridge.metrics import wl_fetch_total

    before = _counter_value(wl_fetch_total.labels(station_id="99999", status="success"))
    await run_collection_cycle(_StubCollector(), [])
    after = _counter_value(wl_fetch_total.labels(station_id="99999", status="success"))
    assert after == before + 1


async def test_cycle_collector_error_increments_wl_fetch_total_error() -> None:
    """A failed fetch increments wl_fetch_total{status='error'}."""
    from weatherlink_bridge.metrics import wl_fetch_total

    before = _counter_value(wl_fetch_total.labels(station_id="unknown", status="error"))
    await run_collection_cycle(_StubCollector(raises=True), [])
    after = _counter_value(wl_fetch_total.labels(station_id="unknown", status="error"))
    assert after == before + 1


async def test_cycle_publish_success_increments_publish_total() -> None:
    """A successful publish increments publish_total{publisher='stub', status='success'}."""
    from weatherlink_bridge.metrics import publish_total

    before = _counter_value(publish_total.labels(publisher="stub", status="success"))
    await run_collection_cycle(
        _StubCollector(), [_StubPublisher(result=PublishResult.SUCCESS)]
    )
    after = _counter_value(publish_total.labels(publisher="stub", status="success"))
    assert after == before + 1


async def test_cycle_publish_failure_increments_publish_total() -> None:
    """A failed publish increments publish_total{publisher='stub', status='failure'}."""
    from weatherlink_bridge.metrics import publish_total

    before = _counter_value(publish_total.labels(publisher="stub", status="failure"))
    await run_collection_cycle(
        _StubCollector(), [_StubPublisher(result=PublishResult.FAILURE)]
    )
    after = _counter_value(publish_total.labels(publisher="stub", status="failure"))
    assert after == before + 1


async def test_cycle_publish_skipped_increments_publish_total_skipped() -> None:
    """A skipped publisher increments publish_total{publisher='stub', status='skipped'}."""
    from weatherlink_bridge.metrics import publish_total

    before = _counter_value(publish_total.labels(publisher="stub", status="skipped"))
    await run_collection_cycle(
        _StubCollector(), [_StubPublisher(result=PublishResult.SKIPPED)]
    )
    after = _counter_value(publish_total.labels(publisher="stub", status="skipped"))
    assert after == before + 1


async def test_cycle_success_increments_collection_run_total_success() -> None:
    """A fully successful cycle increments collection_run_total{status='success'}."""
    from weatherlink_bridge.metrics import collection_run_total

    before = _counter_value(collection_run_total.labels(status="success"))
    await run_collection_cycle(
        _StubCollector(), [_StubPublisher(result=PublishResult.SUCCESS)]
    )
    after = _counter_value(collection_run_total.labels(status="success"))
    assert after == before + 1


async def test_cycle_partial_increments_collection_run_total_partial() -> None:
    """A partial success cycle increments collection_run_total{status='partial'}."""
    from weatherlink_bridge.metrics import collection_run_total

    before = _counter_value(collection_run_total.labels(status="partial"))
    publishers = [
        _StubPublisher(result=PublishResult.SUCCESS),
        _StubPublisher(result=PublishResult.FAILURE),
    ]
    await run_collection_cycle(_StubCollector(), publishers)
    after = _counter_value(collection_run_total.labels(status="partial"))
    assert after == before + 1


async def test_cycle_error_increments_collection_run_total_error() -> None:
    """A failed cycle increments collection_run_total{status='error'}."""
    from weatherlink_bridge.metrics import collection_run_total

    before = _counter_value(collection_run_total.labels(status="error"))
    await run_collection_cycle(_StubCollector(raises=True), [])
    after = _counter_value(collection_run_total.labels(status="error"))
    assert after == before + 1


async def test_cycle_success_updates_last_successful_cycle_timestamp() -> None:
    """A fully-successful cycle updates last_successful_cycle_timestamp."""
    import time

    from weatherlink_bridge.metrics import last_successful_cycle_timestamp

    before = time.time()
    await run_collection_cycle(
        _StubCollector(), [_StubPublisher(result=PublishResult.SUCCESS)]
    )
    value = last_successful_cycle_timestamp._value.get()  # type: ignore[attr-defined]
    assert value >= before


async def test_cycle_partial_updates_last_successful_cycle_timestamp() -> None:
    """A partial cycle DOES update last_successful_cycle_timestamp.

    Liveness is fetch-based: the timestamp advances on every successful fetch
    regardless of publisher outcomes (ENH-001).
    """
    import time

    from weatherlink_bridge.metrics import last_successful_cycle_timestamp

    before = time.time()
    publishers = [
        _StubPublisher(result=PublishResult.SUCCESS),
        _StubPublisher(result=PublishResult.FAILURE),
    ]
    await run_collection_cycle(_StubCollector(), publishers)

    value = last_successful_cycle_timestamp._value.get()  # type: ignore[attr-defined]
    assert value >= before


async def test_cycle_publisher_exception_increments_failure() -> None:
    """A publisher that raises contributes a 'failure' to publish_total."""
    from weatherlink_bridge.metrics import publish_total

    before = _counter_value(publish_total.labels(publisher="stub", status="failure"))
    await run_collection_cycle(_StubCollector(), [_StubPublisher(raises=True)])
    after = _counter_value(publish_total.labels(publisher="stub", status="failure"))
    assert after == before + 1


# ---------------------------------------------------------------------------
# Adversarial: PublishResult accounting in run_collection_cycle
# ---------------------------------------------------------------------------


async def test_all_success_updates_last_successful_and_metric() -> None:
    """All SUCCESS: cycle_status='success', last_successful updated, metric incremented."""
    import time

    from weatherlink_bridge.metrics import (
        collection_run_total,
        last_successful_cycle_timestamp,
    )

    before_ts = time.time()
    before_count = _counter_value(collection_run_total.labels(status="success"))

    result = await run_collection_cycle(
        _StubCollector(),
        [
            _StubPublisher(result=PublishResult.SUCCESS),
            _StubPublisher(result=PublishResult.SUCCESS),
        ],
    )

    assert result == "success"
    assert (
        _counter_value(collection_run_total.labels(status="success"))
        == before_count + 1
    )
    stored_ts = last_successful_cycle_timestamp._value.get()  # type: ignore[attr-defined]
    assert stored_ts >= before_ts


async def test_mixed_success_failure_is_partial_timestamp_advances() -> None:
    """SUCCESS+FAILURE: cycle='partial', last_successful IS updated (fetch-based liveness),
    partial metric incremented (ENH-001).
    """
    import time

    from weatherlink_bridge.metrics import (
        collection_run_total,
        last_successful_cycle_timestamp,
    )

    before_ts = time.time()
    before_partial = _counter_value(collection_run_total.labels(status="partial"))

    result = await run_collection_cycle(
        _StubCollector(),
        [
            _StubPublisher(result=PublishResult.SUCCESS),
            _StubPublisher(result=PublishResult.FAILURE),
        ],
    )

    assert result == "partial"
    assert (
        _counter_value(collection_run_total.labels(status="partial"))
        == before_partial + 1
    )
    stored_ts = last_successful_cycle_timestamp._value.get()  # type: ignore[attr-defined]
    assert stored_ts >= before_ts


async def test_all_failure_is_error_timestamp_still_advances() -> None:
    """All FAILURE: cycle='error', but last_successful IS updated because fetch succeeded (ENH-001).

    Liveness is fetch-based; publisher-only failures do not gate the timestamp.
    """
    import time

    from weatherlink_bridge.metrics import (
        collection_run_total,
        last_successful_cycle_timestamp,
    )

    before_ts = time.time()
    before_error = _counter_value(collection_run_total.labels(status="error"))

    result = await run_collection_cycle(
        _StubCollector(),
        [
            _StubPublisher(result=PublishResult.FAILURE),
            _StubPublisher(result=PublishResult.FAILURE),
        ],
    )

    assert result == "error"
    assert (
        _counter_value(collection_run_total.labels(status="error")) == before_error + 1
    )
    stored_ts = last_successful_cycle_timestamp._value.get()  # type: ignore[attr-defined]
    assert stored_ts >= before_ts


async def test_raising_publisher_counted_as_failure_cycle_continues() -> None:
    """Publisher that raises: publish_total{status=failure} incremented; cycle continues to others."""
    from weatherlink_bridge.metrics import publish_total

    # Use a unique publisher name to isolate the counter delta.
    class _RaisingPublisher(_StubPublisher):
        name = "raising_pub_adversarial"

        async def publish(self, observation: Any) -> PublishResult:
            raise RuntimeError("boom")

    class _OkPublisher(_StubPublisher):
        name = "ok_pub_adversarial"

    before_fail = _counter_value(
        publish_total.labels(publisher="raising_pub_adversarial", status="failure")
    )
    before_success = _counter_value(
        publish_total.labels(publisher="ok_pub_adversarial", status="success")
    )

    ok_pub = _OkPublisher(result=PublishResult.SUCCESS)
    result = await run_collection_cycle(
        _StubCollector(),
        [_RaisingPublisher(raises=True), ok_pub],
    )

    # Second publisher must have been called (cycle must continue).
    assert ok_pub.called
    # Result: 1 success out of 2 → partial
    assert result == "partial"
    assert (
        _counter_value(
            publish_total.labels(publisher="raising_pub_adversarial", status="failure")
        )
        == before_fail + 1
    )
    assert (
        _counter_value(
            publish_total.labels(publisher="ok_pub_adversarial", status="success")
        )
        == before_success + 1
    )


async def test_all_skipped_is_partial_timestamp_advances_skipped_metric() -> None:
    """All SKIPPED: cycle='partial' (ENH-001), publish_total{status=skipped} incremented,
    last_successful_cycle_timestamp advances (fetch succeeded).

    A healthy-but-rate-limited cycle must not be classified as 'error' — the
    liveness probe would otherwise kill a functioning service during backoff.
    """
    import time

    from weatherlink_bridge.metrics import (
        collection_run_total,
        last_successful_cycle_timestamp,
        publish_total,
    )

    before_ts = time.time()

    class _SkippedPub(_StubPublisher):
        name = "skipped_pub_probe"

    before_partial = _counter_value(collection_run_total.labels(status="partial"))
    before_skipped = _counter_value(
        publish_total.labels(publisher="skipped_pub_probe", status="skipped")
    )

    result = await run_collection_cycle(
        _StubCollector(),
        [_SkippedPub(result=PublishResult.SKIPPED)],
    )

    assert result == "partial"
    assert (
        _counter_value(collection_run_total.labels(status="partial"))
        == before_partial + 1
    )
    stored_ts = last_successful_cycle_timestamp._value.get()  # type: ignore[attr-defined]
    assert stored_ts >= before_ts
    assert (
        _counter_value(
            publish_total.labels(publisher="skipped_pub_probe", status="skipped")
        )
        == before_skipped + 1
    )


async def test_success_skip_mix_is_partial_timestamp_advances() -> None:
    """SUCCESS + SKIP mix → 'partial', last_successful_cycle_timestamp advances (ENH-001)."""
    import time

    from weatherlink_bridge.metrics import (
        collection_run_total,
        last_successful_cycle_timestamp,
    )

    before_ts = time.time()
    before_partial = _counter_value(collection_run_total.labels(status="partial"))

    result = await run_collection_cycle(
        _StubCollector(),
        [
            _StubPublisher(result=PublishResult.SUCCESS),
            _StubPublisher(result=PublishResult.SKIPPED),
        ],
    )

    assert result == "partial"
    assert (
        _counter_value(collection_run_total.labels(status="partial"))
        == before_partial + 1
    )
    stored_ts = last_successful_cycle_timestamp._value.get()  # type: ignore[attr-defined]
    assert stored_ts >= before_ts


async def test_collector_error_does_not_advance_timestamp() -> None:
    """CollectorError → timestamp NOT advanced, status 'error' (ENH-001)."""
    from weatherlink_bridge.metrics import (
        collection_run_total,
        last_successful_cycle_timestamp,
    )

    last_successful_cycle_timestamp.set(0.0)
    before_error = _counter_value(collection_run_total.labels(status="error"))

    result = await run_collection_cycle(_StubCollector(raises=True), [])

    assert result == "error"
    assert (
        _counter_value(collection_run_total.labels(status="error")) == before_error + 1
    )
    assert last_successful_cycle_timestamp._value.get() == pytest.approx(0.0)  # type: ignore[attr-defined]


async def test_collector_error_wl_fetch_metric_and_publishers_not_called() -> None:
    """CollectorError: wl_fetch_total{status=error} incremented, publishers NOT called."""
    from weatherlink_bridge.metrics import collection_run_total, wl_fetch_total

    before_fetch_err = _counter_value(
        wl_fetch_total.labels(station_id="unknown", status="error")
    )
    before_cycle_err = _counter_value(collection_run_total.labels(status="error"))

    pub = _StubPublisher(result=PublishResult.SUCCESS)
    result = await run_collection_cycle(_StubCollector(raises=True), [pub])

    assert result == "error"
    assert not pub.called
    assert (
        _counter_value(wl_fetch_total.labels(station_id="unknown", status="error"))
        == before_fetch_err + 1
    )
    assert (
        _counter_value(collection_run_total.labels(status="error"))
        == before_cycle_err + 1
    )


async def test_skipped_publisher_publish_total_skipped_incremented() -> None:
    """SKIPPED publisher increments publish_total{status=skipped}, not success or failure."""
    from weatherlink_bridge.metrics import publish_total

    class _SkippedNamedPub(_StubPublisher):
        name = "skipped_named_pub"

    before_skipped = _counter_value(
        publish_total.labels(publisher="skipped_named_pub", status="skipped")
    )
    before_success = _counter_value(
        publish_total.labels(publisher="skipped_named_pub", status="success")
    )
    before_failure = _counter_value(
        publish_total.labels(publisher="skipped_named_pub", status="failure")
    )

    await run_collection_cycle(
        _StubCollector(), [_SkippedNamedPub(result=PublishResult.SKIPPED)]
    )

    assert (
        _counter_value(
            publish_total.labels(publisher="skipped_named_pub", status="skipped")
        )
        == before_skipped + 1
    )
    assert (
        _counter_value(
            publish_total.labels(publisher="skipped_named_pub", status="success")
        )
        == before_success
    )
    assert (
        _counter_value(
            publish_total.labels(publisher="skipped_named_pub", status="failure")
        )
        == before_failure
    )


# ---------------------------------------------------------------------------
# Adversarial: record_observation_metrics in run_collection_cycle
# ---------------------------------------------------------------------------


async def test_cycle_record_observation_metrics_called_with_zero_values() -> None:
    """record_observation_metrics is called during cycle; 0.0 fields are recorded."""
    from weatherlink_bridge.metrics import observation_value

    obs_with_zero = WeatherObservation(
        timestamp=_FIXED_TIMESTAMP,
        station_id=77777,
        temp_out_f=0.0,
        rain_60min_in=0.0,
    )

    class _ZeroCollector:
        async def fetch(self) -> WeatherObservation:
            return obs_with_zero

    await run_collection_cycle(_ZeroCollector(), [])

    temp_val = float(
        observation_value.labels(field="temp_out_f", station_id="77777")._value.get()  # type: ignore[attr-defined]
    )
    rain_val = float(
        observation_value.labels(field="rain_60min_in", station_id="77777")._value.get()  # type: ignore[attr-defined]
    )
    assert temp_val == pytest.approx(0.0)
    assert rain_val == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Adversarial: metrics.py — record_observation_metrics non-numeric non-None skip
# ---------------------------------------------------------------------------


def test_record_observation_metrics_skips_non_numeric_non_none() -> None:
    """record_observation_metrics skips fields that are not int/float and not None.

    This test verifies the guard at metrics.py line 131-132 by constructing a
    duck-type observation whose model_dump() returns a string-valued field not in
    skip_fields.  Pydantic models are frozen and do not support patching
    model_dump() directly, so we use a lightweight proxy object instead.
    """
    from weatherlink_bridge.metrics import observation_value, record_observation_metrics
    from weatherlink_bridge.models.observation import WeatherObservation

    real_obs = WeatherObservation(
        timestamp=_FIXED_TIMESTAMP,
        station_id=11111,
        temp_out_f=50.0,
    )

    class _ObsProxy:
        """Proxy that wraps a real WeatherObservation but injects an extra string field."""

        station_id = real_obs.station_id

        def model_dump(self) -> dict[str, object]:
            d = real_obs.model_dump()
            d["synthetic_str_field"] = "not_a_number"
            return d

    # Must not raise, and must not set a gauge for synthetic_str_field.
    record_observation_metrics(_ObsProxy())  # type: ignore[arg-type]

    collected_labels = {
        tuple(sample.labels.values())
        for metric in observation_value.collect()
        for sample in metric.samples
    }
    # The synthetic string field must not have been recorded.
    assert not any("synthetic_str_field" in labels for labels in collected_labels)


# ---------------------------------------------------------------------------
# Adversarial: double-import / duplicate registration guard
# ---------------------------------------------------------------------------


def test_main_import_does_not_cause_duplicate_registry() -> None:
    """Importing main (which imports metrics) after metrics is already imported
    does NOT raise Duplicated timeseries in CollectorRegistry.

    Prometheus_client raises on duplicate registrations if metrics are ever
    defined inside a function instead of at module level.
    """
    import sys

    # Ensure both modules are loaded; neither import must raise.
    import weatherlink_bridge.main
    import weatherlink_bridge.metrics  # noqa: F401

    # Re-importing (from cache) must also not raise.
    main_mod = sys.modules.get("weatherlink_bridge.main")
    metrics_mod = sys.modules.get("weatherlink_bridge.metrics")
    assert main_mod is not None
    assert metrics_mod is not None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _counter_value(counter: Any) -> float:
    """Read the current value of a prometheus_client Counter or Gauge label set."""
    return float(counter._value.get())  # type: ignore[attr-defined]
