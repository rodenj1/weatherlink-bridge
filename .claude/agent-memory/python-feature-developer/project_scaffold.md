---
name: project-scaffold
description: Phase 0 scaffold decisions — src layout, module roles, settings pattern, factory pattern, and ADR bindings
metadata:
  type: project
---

## Scaffold completed 2026-06-17

### Source layout
`src/weatherlink_bridge/` with: `__init__.py` (version 0.1.0), `__main__.py`, `main.py`, `settings.py`, `logger.py`, `exceptions.py`, `metrics.py` (stub), `py.typed`, plus sub-packages: `models/`, `collectors/`, `publishers/`, `mapping/`.

### Settings pattern (ADR 0001)
Each sub-settings class (WeatherLinkSettings, WundergroundSettings, WindySettings) is its own `BaseSettings` with `env_prefix="WEATHERLINK__"` etc. AppSettings does NOT use `env_nested_delimiter` — each sub-model reads its own env vars via `default_factory=lambda: SubSettings()`. This avoids double-prefix expansion. WeatherLinkSettings fields have no defaults (required). `AppSettings.log_level` uses `validation_alias="LOG_LEVEL"`, `update_interval_mins` uses `validation_alias="UPDATE_INTERVAL_MINS"` with `ge=5` (ADR 0007).

### Factory pattern (ADR 0003)
`PublisherFactory` in `publishers/factory.py` mirrors `DestinationFactory`: class-level `_builders: ClassVar[dict[str, PublisherBuilder]]`, methods `register/unregister/is_registered/get_available_types/create/create_all`. `create_all` checks `settings.wunderground.enabled` and `settings.windy.enabled`. Uses structlog not stdlib logging.

### BasePublisher (publishers/base.py)
`BasePublisher(ABC)` with `name: ClassVar[str]`, `async def publish(self, observation: Any) -> bool` (Any until WeatherObservation exists in Phase 1), `async def close(self) -> None` (default no-op). TYPE_CHECKING import of WeatherObservation was dropped since observation.py is a stub with no classes.

### Exception hierarchy (exceptions.py)
`WeatherLinkBridgeError(Exception)` with `message`, `details`, `full_message` attrs (details is keyword-only). Subclasses: `ConfigurationError`, `CollectorError`, `PublisherError`, `MappingError` — all simple pass-through, no extra attrs.

### Structlog logger (logger.py)
`configure_logging(log_level: str, *, development: bool = False)` — JSON renderer in prod, ConsoleRenderer in dev. Routes stdlib logging through structlog.stdlib.ProcessorFormatter.

### Stub modules
All stub modules have ONLY a module docstring (+ optional `from __future__ import annotations`) — zero executable statements — so they produce 100% coverage automatically.

### pyproject.toml notes
- `reportUnusedParameter` was dropped from `[tool.pyright]` (not a valid key in pyright schema).
- mypy override for `prometheus_client.*` will emit an "unused section" note until metrics.py is implemented (Phase 4). This is expected.
- `[tool.commitizen]` uses `major_version_zero = true` (project < 1.0).
- Ruff ignore list is clean: only `E501`. No legacy baseline ignores (greenfield project).
- `asyncio_mode = "auto"` in pytest config.

### Quality gates (all pass)
ruff check: clean; ruff format: 33 files formatted; pyright: 0 errors; mypy: 0 issues in 22 files; pytest: 32 passed, 100% coverage (threshold 95%); CLI `--help`: exits 0.

**Why:** Phase 0 scaffold. Real feature logic begins in Phase 1 (models), Phase 2 (collectors + mapper), Phase 3 (publishers), Phase 4 (metrics).
**How to apply:** When implementing future phases, add to existing stubs; run all 6 gates before declaring done.
