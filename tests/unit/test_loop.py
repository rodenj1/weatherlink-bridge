"""Tests for the run_collection_cycle function in main.py."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from weatherlink_bridge.exceptions import CollectorError
from weatherlink_bridge.main import run_collection_cycle
from weatherlink_bridge.models.observation import WeatherObservation

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
    """Publisher stub that returns a fixed result or raises."""

    name = "stub"

    def __init__(self, *, result: bool = True, raises: bool = False) -> None:
        self._result = result
        self._raises = raises
        self.called = False

    async def publish(self, observation: Any) -> bool:
        self.called = True
        if self._raises:
            raise RuntimeError("Simulated publish failure")
        return self._result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_cycle_all_success() -> None:
    """All publishers succeed → 'success'."""
    collector = _StubCollector()
    publishers = [_StubPublisher(result=True), _StubPublisher(result=True)]
    result = await run_collection_cycle(collector, publishers)
    assert result == "success"


async def test_cycle_partial_success() -> None:
    """One publisher True, one False → 'partial'."""
    collector = _StubCollector()
    publishers = [_StubPublisher(result=True), _StubPublisher(result=False)]
    result = await run_collection_cycle(collector, publishers)
    assert result == "partial"


async def test_cycle_all_publishers_fail() -> None:
    """All publishers return False → 'error'."""
    collector = _StubCollector()
    publishers = [_StubPublisher(result=False), _StubPublisher(result=False)]
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
    second = _StubPublisher(result=True)
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
