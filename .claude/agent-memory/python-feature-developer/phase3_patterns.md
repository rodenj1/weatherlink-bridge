---
name: phase3_patterns
description: Phase 3 transform registry, Windy publisher, and test patterns for weatherlink-bridge
metadata:
  type: project
---

## Transform registry (`mapping/transforms.py`)

Five converters: `f_to_c`, `mph_to_ms`, `inhg_to_pa`, `in_to_mm`, `identity`. All registered in `TRANSFORMS: dict[str, Callable[[float], float]]`. `get_transform(name)` raises `MappingError` for unknown names (ADR 0006 fail-fast).

## FieldMapper transform resolution (ADR 0006)

- At `__init__` time, each `FieldMapping.transform` name is resolved via `get_transform()` → callable stored in `self._transforms: dict[str, Callable[[float], float]]`.
- Unknown transform → `MappingError` at init, not at observation time.
- In `map()`: after None-skip, apply transform if present, `round(..., 4)`, then `str()`.
- `0.0` survives because the check is `if value is None`, not `if not value` (defect #6).

## Pressure conversion constant

`inhg_to_pa` uses factor `3386.389`. 29.92 inHg = **101320.76 Pa**, NOT 101317. Standard atmosphere (101325 Pa) corresponds to ≈29.9213 inHg, which rounds to 101325 Pa. Tests must use `pytest.approx(101320.76, abs=1.0)`.

## WindyPublisher (`publishers/windy.py`)

- Endpoint: GET `https://stations.windy.com/api/v2/observation/update`
- `id` = string station id, `PASSWORD` = api_key, `time` = `%Y-%m-%dT%H:%M:%SZ`
- `_skip_until: datetime | None` — set on 429, checked at start of each `publish()` call.
- 429 body: `{"retry_after": "<RFC-3339>"}` → parse with `.replace("Z", "+00:00")` for Python 3.10 compat; fallback = now + 5min on any parse failure.
- `_parse_retry_after` uses bare `except Exception` (BLE001) — ruff does NOT have BLE001 in select list, so the noqa comment gets auto-removed by ruff.

## publishers/__init__.py after ruff fix

Ruff splits a multi-import into two separate `from ... import (...)` blocks (one per symbol). Correct after `--fix`.

## Test patterns — windy publisher

`_obs(**kwargs)` helper in `test_publisher_windy.py` uses a `defaults: dict` that is `.update()`'d with kwargs so callers can override any default field without duplicate-kwarg errors. Pattern:
```python
defaults: dict[str, object] = {"temp_out_f": 67.6, ...}
defaults.update(kwargs)
return WeatherObservation(timestamp=..., station_id=..., **defaults)
```

## Factory registration pattern

Publisher modules register at module import time with `PublisherFactory.register(...)` at module bottom. `publishers/__init__.py` imports all publisher modules (even with `noqa: F401`) so registration fires on any import of the `publishers` package.

## Coverage

Phase 3 achieves 100% coverage (100/100 branch) across all 22 source files, 220 tests.
