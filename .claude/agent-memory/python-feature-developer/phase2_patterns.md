---
name: phase2-patterns
description: Phase 2 implementation patterns — collector, mapper, publisher, loop; pyright override fix; coverage gaps
metadata:
  type: project
---

## Phase 2 implementation completed (2026-06-17)

### Files added or changed
- `src/weatherlink_bridge/collectors/weatherlink.py` — `WeatherLinkCollector`, `_first`, `_find_iss/baro/soil`, `_to_observation`
- `src/weatherlink_bridge/mapping/mapper.py` — `FieldMapper` (YAML load, transforms rejected eagerly)
- `config/sensor_maps/wunderground.yaml` — WU field map with uppercase `UV` key
- `src/weatherlink_bridge/publishers/wunderground.py` — `WundergroundPublisher` + module-level `PublisherFactory.register`
- `src/weatherlink_bridge/publishers/__init__.py` — imports wunderground to trigger registration
- `src/weatherlink_bridge/main.py` — added `run_collection_cycle`, `CollectorProtocol`
- `tests/unit/test_collector_weatherlink.py`, `test_field_mapper.py`, `test_publisher_wunderground.py`, `test_loop.py`

### Key patterns

**`_first(*vals: float | int | None) -> float | None`**: Always use `float(v)` conversion — SensorData has `int | None` fields (wind_gust_10_min, wind_dir, solar_rad) that must coerce to float. Never use `x or y` for numeric fields (defect #6: 0.0 is falsy but valid).

**Pressure mapping**: Baro sensor (sensor_type 3/242) `bar_sea_level/bar` first, then fall back to ISS `bar_sea_level/bar`. The EnviroMonitor baro sensor (DST=9, sensor_type=3) stores `pressure_last` in model_extra — its declared `bar` field is None. The ISS (DST=6) has `bar=29.959` (sea-level). Never use `bar_absolute`.

**Soil temp**: `temp_soil_1` is NOT a declared SensorData field — read from `sensor.data[0].model_extra.get("temp_soil_1")` since `extra="allow"`.

**BasePublisher override**: `publish(self, observation: ...)` — parameter name MUST match the base class (`observation`, not `obs`). Pyright `reportIncompatibleMethodOverride` catches this.

**publishers/__init__.py import**: Use `# noqa: F401  # pyright: ignore[reportUnusedImport]` to suppress both ruff and pyright complaints about a side-effect-only import.

**`_build_wunderground` path (FIXED, was BUG A)**: Now uses `settings.config_dir / "sensor_maps" / "wunderground.yaml"`. The old `Path(__file__).parents[3]` broke in wheel/container installs because `site-packages` is not at a predictable depth. `config_dir` is a `Path` field on `AppSettings` (env `CONFIG_DIR`, default `Path("config")`). The default resolves correctly in dev (cwd = project root → `./config`) and in Docker (WORKDIR /app, config copied to /app/config → `/app/config`).

**CollectorProtocol in main.py**: Use a `Protocol` class at module level (not inside the function) to avoid E402 module-level import ordering issues. Lazy imports inside async functions also work but create import ordering violations.

**Why:** Avoids circular import; `main.py` must not import the collector at module level.
**How to apply:** Always define structural types (Protocol) near the top of the module, before the functions that use them.

### Test conventions (Phase 2)
- `respx.mock` as decorator or context manager for HTTP tests (both work; decorator preferred for async test functions)
- `asyncio_mode = "auto"` → no `@pytest.mark.asyncio` needed
- `_obs(**kwargs)` helper pattern: create `WeatherObservation` with all fields None + overrides
- `_make_settings()` helper pattern for settings objects
- Coverage gaps to watch: `_find_soil` no-soil-sensor branch, `close()` on publishers, factory builder functions

### Known issue: ruff reformats multi-line string constants
ruff will consolidate multi-line string constants (like `_WU_UPLOAD_URL`) to single line — allow it.

**Why:** Ruff 88-char line length. The formatter's judgment is authoritative.
**How to apply:** Don't fight formatter output on string concatenation.
