# Agent Memory — weatherlink-bridge

- [Project scaffold](project_scaffold.md) — Phase 0 scaffold structure, key module decisions, and ADR bindings
- [Models Phase 1](models_phase1.md) — canonical field names, pyright strict cast pattern for model_validator, test conventions
- [Phase 2 patterns](phase2_patterns.md) — collector/mapper/publisher patterns, _first coercion, pressure fallback, pyright override fix, path math for builders
- [Phase 3 patterns](phase3_patterns.md) — transform registry, Windy publisher, 429 backoff, pressure constant (101320.76 Pa), _obs override pattern in tests
- [Phase 4 patterns](phase4_patterns.md) — PublishResult enum, Prometheus metrics, daemon loop, /healthz via gauge, asyncio.wait_for mock pattern, ValidationError test strategy
- [Phase 5 integration tests](phase5_integration_tests.md) — integration test suite patterns, respx usage, daemon end-to-end httpx patch scope (3 clients captured), query string decode pattern, live test marker
- [Phase 5 packaging](phase5_packaging.md) — Dockerfile uv --no-editable fix, docker-compose urllib healthcheck, K8s env var names, CI workflow shape, image size ~130 MB
- [BUG A+B config_dir fix](bug_fixes_config_dir.md) — sensor-map path broke in container (Path(__file__) → settings.config_dir), BUG B investigation (factory was already correct; .env had publishers enabled), Docker syntax-directive workaround
