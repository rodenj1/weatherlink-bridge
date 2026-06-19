---
name: models-phase1
description: Phase 1 Pydantic v2 models — field names, pyright strict patterns, test conventions
metadata:
  type: project
---

## Phase 1 models — implemented 2026-06-17

Three modules under `src/weatherlink_bridge/models/`:

- `weatherlink.py` — `WeatherLinkResponse`, `Sensor`, `SensorData` (raw API, `extra="allow"`)
- `observation.py` — `WeatherObservation` (canonical, all imperial, all optional except `timestamp`/`station_id`)
- `sensor_map.py` — `SensorMapConfig`, `FieldMapping` (YAML config with shorthand coercion)
- `models/__init__.py` — exports all 5 public classes in `__all__`

## Canonical field names (locked, must not change without migration)

```
pressure_sea_level_inHg   # NOT pressure_inHg
rain_60min_in             # NOT rainfall_last_60_min_in
rain_rate_in_hr           # NOT rain_rate_in
```

## Pyright strict — model_validator(mode="before") pattern

The validator receives `data: object`. After `isinstance(data, dict)`, pyright
narrows to `dict[Unknown, Unknown]`. Use `cast(_RawData, data)` where
`_RawData = dict[str, object]` to pin types, then use the cast variable for all
subsequent returns (returning the pre-cast `data` variable re-introduces Unknown).

```python
_RawData = dict[str, object]

@model_validator(mode="before")
@classmethod
def _coerce(cls, data: object) -> object:
    if not isinstance(data, dict):
        return data
    typed: _RawData = cast(_RawData, data)
    # use typed for all branches, never data after this point
    ...
    merged: _RawData = dict(typed)
    merged["key"] = new_value
    return merged
```

## Test conventions

- Fixture path: `Path(__file__).parents[1] / "fixtures" / "weatherlink" / "current_enviromonitor.json"` (relative to test file, not cwd)
- pytest fixtures typed as `dict` (type: ignore[type-arg]) because ruff N803 is ignored in tests
- `SensorData.model_extra` is `dict[str, Any] | None` — always assert not None before subscripting
- For zero-rain assertions: always assert both `== 0` AND `is not None` to guard the `x or y` coalescing bug documented in ADR 0002

**Why:** ADR 0002 / ADR 0006 live-confirmed: zero rain readings would be silently dropped by `x or y` coalescing.
**How to apply:** Any test for a numeric field that can legitimately be 0 must assert `is not None` separately.
