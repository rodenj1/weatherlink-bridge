---
name: bug-fixes-config-dir
description: BUG A+B post-mortem — sensor-map path in container and disabled-publisher-construction findings
metadata:
  type: project
---

## BUG A (sensor-map path breaks in container) — fixed 2026-06-17

**Root cause**: `_build_wunderground` and `_build_windy` used `Path(__file__).parents[3]` to
find `config/sensor_maps/`. In the dev editable install `parents[3]` from
`src/weatherlink_bridge/publishers/wunderground.py` lands at the project root. In the Docker
wheel install (`site-packages/weatherlink_bridge/publishers/wunderground.py`) it lands inside
the venv, not at `/app`, so `path.read_text()` raises `FileNotFoundError` and the daemon
crashes on startup.

**Fix**: Added `config_dir: Path = Path("config")` (env `CONFIG_DIR`) to `AppSettings`.
Both builders now use `settings.config_dir / "sensor_maps" / "<name>.yaml"`.

**Default resolution**:
- Dev: cwd = project root → `./config` resolves to project `config/`
- Docker: WORKDIR `/app`, `config/` copied to `/app/config/` → relative `config/` resolves

**Removed unused imports**: `from pathlib import Path` was deleted from both publisher modules
(Path no longer needed there; it's only in settings.py now).

**Integration test fix**: `test_daemon_end_to_end.py` must explicitly set
`config_dir=Path(__file__).parents[2] / "config"` so the factory resolves sensor maps from the
real project config/ regardless of the pytest cwd.

**Unit test pattern for builders**: tests that call `_build_wunderground` / `_build_windy`
directly must set `mock_settings.config_dir` to a real path containing `sensor_maps/*.yaml`.
For the BUG A regression test, write a minimal valid YAML into `tmp_path/sensor_maps/` and set
`mock_settings.config_dir = tmp_path` — if the builder ever reverts to `__file__` arithmetic it
will NOT find this temp YAML and the test fails.

## BUG B (disabled publishers still being built) — investigated

**Finding**: `PublisherFactory.create_all` in `factory.py` already correctly checks
`settings.wunderground.enabled` and `settings.windy.enabled` and only builds enabled publishers.
The code was NOT broken.

**Actual cause of the container crash**: the `.env` file had `WUNDERGROUND__ENABLED=true` and
`WINDY__ENABLED=true`. Both publishers were built → `_build_wunderground` hit BUG A
(FileNotFoundError on the sensor map). So the observed symptom (crash on startup even with
"disabled" publishers) was BUG A triggered via BUG B's apparent description.

**What we changed**: `.env` now has both publishers defaulting to `false` so the basic
`docker run --env-file .env` scenario uses zero publishers (BUG A regression test). WU can be
re-enabled with `-e WUNDERGROUND__ENABLED=true`.

**Were disabled publishers being built before?** No — `create_all` filtered correctly. The publishers
were NOT disabled in the `.env`; they were enabled (true) so they WERE built, which triggered BUG A.

**BUG B regression tests added** (even though code was correct): `test_create_all_both_disabled_builds_zero_publishers`,
`test_create_all_only_wunderground_enabled_builds_exactly_one`,
`test_create_all_only_windy_enabled_builds_exactly_one` — all use tracking builders that record
whether they were called. Guards against any future regression.

## Docker build note

`# syntax=docker/dockerfile:1` in the Dockerfile header causes `docker build` to attempt a
`docker.io/docker/dockerfile` pull that can fail if Docker Hub is unavailable. Workaround:
`grep -v "# syntax=" Dockerfile > /tmp/Dockerfile.nosyntax` then build with `-f /tmp/Dockerfile.nosyntax`.

**Why:** The syntax directive is a BuildKit extension for experimental Dockerfile features. It's
not needed for standard Dockerfiles. Consider removing it or making it a comment.

## Settings `_clear_all_app_vars` helper

Always include `"CONFIG_DIR"` in the list of vars cleared so tests that set `CONFIG_DIR=` in
the environment don't leak into other tests.
