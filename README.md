# WeatherLink Bridge

A Python service that polls the **Davis WeatherLink v2 API** and forwards personal weather station observations to **Weather Underground** and **Windy**. It is a clean rewrite of the original Node.js app, adding robust configuration management, Prometheus metrics, and a production-ready container image.

---

## Architecture

```
WeatherLink API
      |
      v
WeatherLinkCollector  (httpx, X-Api-Secret header)
      |
      v
WeatherObservation    (canonical imperial fields, Pydantic v2)
      |
      +----> FieldMapper(wunderground.yaml) --> WundergroundPublisher --> WU HTTPS API
      |
      +----> FieldMapper(windy.yaml)        --> WindyPublisher        --> Windy v2 API
                  (unit transforms: °F→°C, mph→m/s, inHg→Pa, in→mm)

Prometheus /metrics on METRICS_PORT (default 8080)
  - wl_fetch_total, publish_total, collection_run_total
  - observation_value (per-field gauge)
  - last_successful_cycle_timestamp  <-- liveness signal
```

Publishers are registered via `PublisherFactory` — adding a new destination (CWOP, PWSWeather, …) requires only a new YAML sensor map and a publisher class.

---

## Quickstart

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/).

```bash
# Clone and install
git clone https://github.com/rodenj1/weatherlink-bridge.git
cd weatherlink-bridge

# Copy the example env file and fill in your credentials
cp .env.example .env
$EDITOR .env

# Run directly (reads .env automatically)
uv run weatherlink-bridge

# Or install into a venv and run the console script
uv sync
weatherlink-bridge --version
weatherlink-bridge
```

---

## Configuration Reference

All configuration is via environment variables (or a `.env` file in the working directory). Nested settings use the `__` delimiter.

| Variable | Required | Default | Description |
|---|---|---|---|
| `WEATHERLINK__API_KEY` | Yes | — | WeatherLink v2 API key |
| `WEATHERLINK__API_SECRET` | Yes | — | WeatherLink v2 API secret |
| `WEATHERLINK__STATION_ID` | Yes | — | WeatherLink station ID |
| `WUNDERGROUND__ENABLED` | No | `false` | Enable Weather Underground publishing |
| `WUNDERGROUND__STATION_ID` | No | `""` | WU PWS station ID (e.g. `KCASANDI123`) |
| `WUNDERGROUND__PASSWORD` | No | `""` | WU station key / password |
| `WINDY__ENABLED` | No | `false` | Enable Windy publishing |
| `WINDY__STATION_ID` | No | `""` | Windy station ID (numeric) |
| `WINDY__PASSWORD` | No | `""` | Windy station password (see note below) |
| `UPDATE_INTERVAL_MINS` | No | `5` | Poll interval in minutes (minimum 5) |
| `METRICS_PORT` | No | `8080` | TCP port for Prometheus `/metrics` |
| `LOG_LEVEL` | No | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Windy credentials note

Windy uses a **per-station password** for uploads, not the management API key.
Find it at [stations.windy.com](https://stations.windy.com/) under
**My Stations → Station settings → Key/Password**. Set this value in
`WINDY__PASSWORD`.

### Weather Underground credentials note

WU needs the **station ID** (`WUNDERGROUND__STATION_ID`, e.g. `KCASANDI123`)
and the **station key / password** (`WUNDERGROUND__PASSWORD`). Both are found
in the WU device management dashboard.

---

## Running with Docker

### Single container

```bash
# Pull the latest image
docker pull ghcr.io/rodenj1/weatherlink-bridge:latest

# Run with a .env file
docker run --rm --env-file .env -p 8080:8080 ghcr.io/rodenj1/weatherlink-bridge:latest
```

### docker-compose

```bash
cp .env.example .env
$EDITOR .env          # fill in real credentials
docker compose up -d
# metrics available at http://localhost:8080/metrics
```

The image is published to `ghcr.io/rodenj1/weatherlink-bridge` for both
`linux/amd64` and `linux/arm64` (suitable for Raspberry Pi / ARM homelab).

---

## Running on Kubernetes

Manifests are under `deploy/k8s/`.

```bash
# 1. Create the namespace
kubectl create namespace weather

# 2. Copy the secret example, fill in real values, apply
cp deploy/k8s/secret.example.yaml deploy/k8s/secret.yaml
$EDITOR deploy/k8s/secret.yaml   # add real credentials
kubectl apply -f deploy/k8s/secret.yaml

# 3. Apply the rest
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml

# Verify
kubectl -n weather get pods
kubectl -n weather logs -f deployment/weatherlink-bridge
```

> **Do not commit `secret.yaml` with real values.** Use
> [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) or a
> secrets manager to encrypt before committing.

The Deployment is intentionally `replicas: 1` — two replicas would
**double-upload** every observation to WU and Windy.

### Liveness and readiness probes

Both probes hit `GET /metrics` on port 8080. The liveness probe also lets you
monitor `last_successful_cycle_timestamp` in Prometheus — if that gauge is
older than `2 * update_interval_seconds`, the service may be stalled.

---

## Metrics

The service exposes Prometheus metrics at `http://<host>:8080/metrics`.

| Metric | Type | Description |
|---|---|---|
| `wl_fetch_total` | Counter | WeatherLink fetch attempts (`status=success\|error`) |
| `wl_fetch_duration_seconds` | Histogram | WeatherLink API latency |
| `publish_total` | Counter | Publisher attempts (`publisher=wu\|windy`, `status=success\|failure\|skipped`) |
| `publish_duration_seconds` | Histogram | Publisher call latency |
| `collection_run_total` | Counter | Full cycle outcomes (`status=success\|partial\|error`) |
| `collection_run_duration_seconds` | Histogram | Full cycle duration |
| `observation_value` | Gauge | Latest numeric field value per field + station |
| `last_successful_cycle_timestamp` | Gauge | Unix timestamp of last successful fetch (liveness signal) |
| `update_interval_seconds` | Gauge | Configured poll interval |
| `weatherlink_bridge_info` | Info | App version |

### Liveness vs freshness

- **Liveness** (`last_successful_cycle_timestamp`): advances after every
  successful WeatherLink fetch, regardless of publisher outcomes. Alert if
  `time() - last_successful_cycle_timestamp > 2 * update_interval_seconds`.
- **Publisher health**: monitor `publish_total{status="failure"}` separately.
  Publisher failures do not gate liveness — a rate-limited or temporarily
  unavailable WU/Windy should not restart the pod.

---

## Migration from the Node.js version

| Old environment variable | New environment variable | Notes |
|---|---|---|
| `WEATHERLINK_API_KEY` | `WEATHERLINK__API_KEY` | Delimiter changed (`_` → `__`) |
| `WEATHERLINK_API_SECRECT` | `WEATHERLINK__API_SECRET` | **Typo fixed** (`SECRECT` → `SECRET`) |
| `WEATHERLINK_STATION_ID` | `WEATHERLINK__STATION_ID` | Delimiter changed |
| `WUNDERGROUND_ID` | `WUNDERGROUND__STATION_ID` | Renamed for clarity |
| `WUNDERGROUND_KEY` | `WUNDERGROUND__PASSWORD` | Renamed; this is the station password |
| `UPDATE_INTERVAL_MINS` | `UPDATE_INTERVAL_MINS` | Unchanged |
| `PORT` | `METRICS_PORT` | Renamed; default is now 8080 |

**Sensor map:** `sensor_map.json` is replaced by YAML files in
`config/sensor_maps/` (`wunderground.yaml`, `windy.yaml`). The YAML format
supports field transforms (unit conversions) and is checked into version
control.

---

## Development

```bash
# Install all deps including dev tools
uv sync

# Run tests with coverage
uv run pytest

# Lint + format check
uv run ruff check src tests
uv run ruff format --check src tests

# Type-check
uv run pyright src
uv run mypy src

# Pre-commit hooks (runs on every commit)
uv run pre-commit install
uv run pre-commit run --all-files
```

---

## License

MIT — see [LICENSE](LICENSE).
