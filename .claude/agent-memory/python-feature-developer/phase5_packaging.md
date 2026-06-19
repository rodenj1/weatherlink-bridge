---
name: phase5-packaging
description: Dockerfile, docker-compose, K8s manifests, CI workflow, and README for weatherlink-bridge Phase 5
metadata:
  type: project
---

## Key decisions made in Phase 5

### Dockerfile — uv editable install gotcha
The critical fix: `uv sync --frozen --no-dev` installs the project as editable (`.pth` file pointing to `/app/src`). When only `.venv` is copied to the runtime stage, the `.pth` reference breaks because `src/` is absent. Fix: use `--no-editable` on the final sync:

```
RUN uv sync --frozen --no-dev --no-editable
```

This installs a real wheel into `.venv/lib/.../site-packages/` so the runtime stage only needs `.venv` (no `src/` copy needed).

### docker-compose healthcheck
The slim runtime image has no `curl` or `wget`. Use Python's stdlib instead:
```yaml
test:
  - "CMD"
  - "python"
  - "-c"
  - "import urllib.request; urllib.request.urlopen('http://localhost:8080/metrics')"
```

### K8s — env var naming (current as of Phase 5)
Secret keys use the renamed vars:
- `WUNDERGROUND__PASSWORD` (not `__API_KEY`)
- `WINDY__PASSWORD` (not `__API_KEY`)

Non-secret env keys in Deployment plain `env`: `WUNDERGROUND__ENABLED`, `WINDY__ENABLED`, `UPDATE_INTERVAL_MINS`, `METRICS_PORT`, `LOG_LEVEL`.

### Liveness/readiness probes
Both probe `httpGet /metrics :8080`. Liveness is NOT a `/healthz` endpoint — it is derived from `last_successful_cycle_timestamp` gauge on `/metrics`.

### readOnlyRootFilesystem: true
Applied in the container securityContext — works because the service writes no files at runtime; all config is read-only from `/app/config` (copied at build time).

### Image size
Final image: ~130.7 MB (python:3.12-slim-bookworm + venv with 16 runtime deps).

### CI workflow
- `astral-sh/setup-uv@v6` with `enable-cache: true`
- `docker/metadata-action@v5` for tags (`:latest` on main, semver tags on `v*` pushes, sha prefix)
- `docker/build-push-action@v6` with `cache-from/to: type=gha`
- `permissions: packages: write` required for GHCR push

**Why:** [[phase4_patterns]]
