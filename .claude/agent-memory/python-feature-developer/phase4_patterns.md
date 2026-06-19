---
name: phase4_patterns
description: Phase 4 observability patterns — metrics, daemon loop, PublishResult enum, test strategies
metadata:
  type: project
---

## PublishResult enum (`publishers/base.py`)

`publish()` now returns `PublishResult` (SUCCESS/FAILURE/SKIPPED) instead of `bool`. SKIPPED is used by WindyPublisher when the 429 backoff window is active. All publisher tests and loop tests were updated accordingly.

**Why:** Needed to distinguish `skipped` from `failure` in Prometheus metrics. `bool` can't carry three states cleanly.

## Prometheus metrics (`metrics.py`)

All metric objects defined at **module import time** (never inside functions) to avoid duplicate registration errors:
- `wl_fetch_total`, `wl_fetch_duration_seconds` — labeled `station_id`
- `publish_total`, `publish_duration_seconds` — labeled `publisher`
- `collection_run_total`, `collection_run_duration_seconds`
- `update_interval_seconds`, `last_successful_cycle_timestamp` — gauges
- `observation_value` — labeled `field`, `station_id`
- `app_info` — Info metric

`record_observation_metrics(obs)` iterates `obs.model_dump()`, skips `timestamp`/`station_id` and `None`/non-numeric values (only `int | float` get recorded).

`start_metrics_server(port)` wraps `prometheus_client.start_http_server`.

**Test pattern for counters/gauges:** read `metric.labels(...)._value.get()` before and after; assert delta = 1. Do NOT re-register metrics. The default registry persists across tests.

## /healthz approach

No second HTTP server. Liveness derived from `last_successful_cycle_timestamp` gauge on `/metrics`. K8s probe (Phase 5) compares gauge to `now - 2 * update_interval_seconds`.

## Daemon loop (`main.py`)

`run()` is the async entrypoint (injecting `_settings`, `_stop_event` for testing).

**Interruptible sleep pattern:**
```python
with contextlib.suppress(TimeoutError):
    await asyncio.wait_for(stop_event.wait(), timeout=interval_secs)
```

**Signal handler:** `loop.add_signal_handler(sig, _handle_signal, sig)` — installs a callback that calls `stop_event.set()`. Mid-cycle signals let the in-flight cycle finish; signals during sleep exit promptly.

**Graceful shutdown:** `finally` block calls `await pub.close()` for each publisher; exceptions are caught and logged.

**pyright ignore needed:** `AppSettings()` call with no args needs `# type: ignore[call-arg]  # pyright: ignore[reportCallIssue]` because pydantic-settings reads from env, but pyright/mypy see `weatherlink` as required.

## Test strategy — daemon loop

Patch `weatherlink_bridge.main.asyncio.wait_for` (not the global `asyncio.wait_for`) with a side_effect that:
1. Closes the passed coroutine: `if hasattr(coro, "close"): coro.close()` (prevents "coroutine never awaited" warning)
2. Sets `stop_event`
3. Raises `TimeoutError` (the normal tick path)

Do NOT wrap the outer `run()` call in `asyncio.wait_for` since that would also be intercepted by the mock.

## Test strategy — ValidationError in main()

Do not rely on env var removal (real `.env` files may satisfy validation). Patch `weatherlink_bridge.settings.AppSettings` with `side_effect=ValidationError.from_exception_data(...)`.

## settings.py

Added `metrics_port: int = Field(default=8080, ge=1, le=65535)` with env var `METRICS_PORT`.

## Coverage

Phase 4 achieves **99.43%** (3 uncovered lines: signal handler body in main.py, unreachable `continue` branch in metrics.py). 260 tests.
