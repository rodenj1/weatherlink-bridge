---
name: project-layout
description: Test locations, fixture paths, coverage command, and source package for weatherlink-bridge
metadata:
  type: project
---

## Project: weatherlink-bridge

**Source package**: `weatherlink_bridge` (under `src/weatherlink_bridge/`)

**Coverage command**: `uv run pytest --cov=weatherlink_bridge --cov-report=term-missing`

**Test layout**:
- `tests/unit/` — all unit tests (no integration tests active yet)
- `tests/fixtures/weatherlink/current_enviromonitor.json` — real Phase 0 fixture, station 148534, EnviroMonitor/DST-6

**Test files for Phase 1 models**:
- `tests/unit/test_models_weatherlink.py` — SensorData, Sensor, WeatherLinkResponse
- `tests/unit/test_models_observation.py` — WeatherObservation canonical model
- `tests/unit/test_models_sensor_map.py` — FieldMapping, SensorMapConfig

**Baseline after Phase 3 hardening (2026-06-17)**: 223 tests, 100% coverage.
**Baseline after Phase 4 hardening (2026-06-17)**: 274 tests, 100% coverage.

**Type checker notes**: mypy emits an unused-section note for `prometheus_client.*` — this is known/harmless.

**Phase 2 test files added**:
- `tests/unit/test_collector_weatherlink.py` — WeatherLinkCollector + _to_observation (incl. auth header, zero-value, empty-data-list, baro-only edge cases)
- `tests/unit/test_field_mapper.py` — FieldMapper (incl. zero-value, windy.yaml placeholder, schema errors)
- `tests/unit/test_publisher_wunderground.py` — WundergroundPublisher (incl. SUCCESS\n uppercase, exact INVALIDPASSWORDID body)
- `tests/unit/test_loop.py` — run_collection_cycle

**Phase 3 test files added**:
- `tests/unit/test_transforms.py` — conversion registry (f_to_c, mph_to_ms, inhg_to_pa, in_to_mm, identity, get_transform)
- `tests/unit/test_publisher_windy.py` — WindyPublisher (respx-based; 429 backoff state machine, +00:00 timezone format, backoff expiry, disabled path, id/PASSWORD/time params)
- Updated `tests/unit/test_field_mapper.py` — windy.yaml end-to-end, transform application, zero-survives-transform, no-imperial-fallback

**Phase 4 test files added/modified**:
- `tests/unit/test_daemon.py` — signal handler direct invocation (lines 290-291 coverage), close-once-per-publisher, no-real-port-bound
- `tests/unit/test_loop.py` — adversarial PublishResult accounting, all-SKIPPED probe (ENH-001), collector error metrics, double-import guard, non-numeric field proxy test
- `tests/unit/test_metrics.py` — import idempotence, all record_observation_metrics edge cases, server mock

**Phase 4 coverage gaps closed**:
- `main.py` lines 290-291 (_handle_signal body): covered by `test_handle_signal_can_be_called_directly_without_run` which replicates the closure inline and verifies stop_event.set() is called. The `test_handle_signal_sets_stop_event` test captures via add_signal_handler interception as a belt-and-suspenders approach.
- `metrics.py` line 132 (non-numeric continue): applied `# pragma: no cover` with justification ("WeatherObservation has no non-numeric non-skipped fields"). A proxy-based test was ALSO added (`test_record_observation_metrics_skips_non_numeric_non_none`) that injects a string field via a duck-type proxy to exercise the branch despite the pragma.

**Phase 4 key decisions/gotchas**:
- Pydantic v2 models are frozen — you CANNOT `patch.object(obs, 'model_dump', ...)`. Use a duck-type proxy class instead.
- Signal handler `_handle_signal` inside `run()` can't be extracted by name; must be intercepted via `loop.add_signal_handler`. Simpler approach: replicate the closure inline in the test.
- `asyncio.wait_for` patch target is `weatherlink_bridge.main.asyncio.wait_for` (not `asyncio.wait_for`).
- All-SKIPPED cycle returns "error" (success_count==0). This is a known semantics issue filed as ENH-001.
- `wl_fetch_duration_seconds` always uses `station_id="unknown"` — the histogram is observed before the fetch completes so the real ID isn't available. Filed as ENH-002.
- httpx.AsyncClient in `run()` (the collector client) is never explicitly closed. Filed as ENH-003.

**Phase 3 key decisions/gotchas**:
- `inhg_to_pa` uses NIST 3386.389 Pa/inHg; 29.92 inHg = 101320.76 Pa (NOT 101317.4 as an old spec draft said — that's wrong)
- `FieldMapper` resolves transforms at init time and raises `MappingError` eagerly for unknown transform names
- WindyPublisher `_parse_retry_after` uses `str(raw).replace("Z", "+00:00")` + `fromisoformat` + `astimezone(UTC)` — handles both Z and +00:00 formats correctly
- Subtle unresolved behavior: a naive RFC-3339 string (no tz suffix) in `retry_after` gets localized via the system tz by `astimezone(UTC)` — returns tz-aware but value is system-tz-dependent (filed as low-severity bug BR-003)
- `windy.yaml` has NO `static_params` — id, PASSWORD, time are injected directly by WindyPublisher
- Windy `id` must be a STRING — enforced by `str(settings.station_id)` in publish()

**Fixture notes**:
- Real fixture (station 148534): ISS sensor_type=24 DST=6; baro sensor_type=3 DST=9 with `pressure_last` in model_extra (NOT bar/bar_sea_level). Pressure comes from ISS `bar` field.
- `bar=29.959` (ISS) is sea-level; `bar_absolute=29.958` is station pressure — must NOT publish the latter.

**Why:** Phase 1 added Pydantic v2 models; tests validated against a real EnviroMonitor fixture. No WLL/DST-10 fixture file exists; portability tests use inline dicts.
