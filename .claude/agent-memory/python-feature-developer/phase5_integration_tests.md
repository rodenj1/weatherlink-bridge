---
name: phase5-integration-tests
description: Integration test suite patterns, respx usage, daemon end-to-end test mechanics, and httpx.AsyncClient patch scope discovery
metadata:
  type: project
---

## Integration test suite (Phase 5)

### File locations
- `tests/integration/test_pipeline_wunderground.py` — WL collector → WU publisher, 2 tests
- `tests/integration/test_pipeline_windy.py` — WL collector → Windy publisher (incl. 429 backoff), 2 tests
- `tests/integration/test_daemon_end_to_end.py` — full `run()` with both publishers, 1 test
- `tests/integration/test_live_weatherlink.py` — opt-in live API smoke test (skipped unless WLB_LIVE_TESTS=1)

### pyproject.toml changes
- `norecursedirs` changed from `["integration", "manual"]` to `["manual"]` — integration tests are now part of normal `uv run pytest`
- Added `markers` list for `integration` and `live`

### respx usage pattern
Use `@respx.mock` decorator on the async test function; `respx.get(url).mock(return_value=httpx.Response(...))`. Respx patches the httpx transport globally for all real AsyncClient instances within the mock context. Works with real `httpx.AsyncClient` instances.

For 429 backoff tests: call `.mock(...)` twice on the same route — the second call replaces the first mock. The final mock is what gets used.

### httpx.AsyncClient patch scope — critical discovery
Patching `weatherlink_bridge.main.httpx.AsyncClient` replaces `AsyncClient` on the shared `httpx` MODULE OBJECT (not just in main.py's namespace). This means ALL modules that reference `httpx.AsyncClient` (not just ones that did `from httpx import AsyncClient`) are affected. In the daemon end-to-end test, this captures 3 clients: collector (created in main.py line 298) + WU publisher builder (wunderground.py) + Windy publisher builder (windy.py). Assert `len == 3` and all are closed.

**Why:** `_build_wunderground` and `_build_windy` are called from within `PublisherFactory.create_all(settings)` inside `run()`, and they use `httpx.AsyncClient()` from their own module scope — but since it's the same `httpx` module object, the patch intercepts them too.

### Daemon end-to-end test pattern
```python
with (
    patch("weatherlink_bridge.metrics.start_http_server"),
    patch("weatherlink_bridge.main.httpx.AsyncClient", side_effect=_capturing_client),
    patch("weatherlink_bridge.main.asyncio.wait_for", side_effect=_make_wait_for_that_stops(stop_event)),
):
    await run(_settings=settings, _stop_event=stop_event)
```
Do NOT patch `WeatherLinkCollector` or `PublisherFactory.create_all` — the integration test uses real components.

### Prometheus counter value access
`float(counter.labels(status="success")._value.get())` — consistent with existing unit tests.

### Query string decoding
Use `from urllib.parse import parse_qs, urlparse; qs = parse_qs(urlparse(str(request.url)).query)` to decode sent query params. `parse_qs` returns `dict[str, list[str]]`.

### Coverage result
100% line and branch coverage achieved with integration tests included in the normal test run.

**Why:** integration tests exercise real component wiring paths that unit tests mock, pushing coverage over any remaining gap.

### Live test marker
`@pytest.mark.live` + `@pytest.mark.skipif(os.environ.get("WLB_LIVE_TESTS") != "1", ...)` — skipped in all normal CI runs.
