"""WeatherLink v2 API collector.

Fetches current conditions from the WeatherLink v2 ``/current`` endpoint and
maps the raw response to a canonical ``WeatherObservation``.

Authentication (ADR 0005): the API secret is passed as the ``x-api-secret``
request header — it must NEVER appear in the query string.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import structlog

from weatherlink_bridge.exceptions import CollectorError
from weatherlink_bridge.models.observation import WeatherObservation
from weatherlink_bridge.models.weatherlink import (
    Sensor,
    SensorData,
    WeatherLinkResponse,
)
from weatherlink_bridge.settings import WeatherLinkSettings

log = structlog.get_logger(__name__)

_WEATHERLINK_BASE_URL = "https://api.weatherlink.com/v2"


def _first(*vals: float | int | None) -> float | None:
    """Return the first non-None value as float, or None if all are None.

    Handles ``int | None`` fields (e.g. ``wind_gust_10_min``, ``wind_dir``)
    by coercing to float — avoids the ``x or y`` pitfall where 0.0 is falsy
    (defect #6: zero values must survive).
    """
    for v in vals:
        if v is not None:
            return float(v)
    return None


def _find_iss(sensors: list[Sensor]) -> SensorData | None:
    """Find the first ISS sensor data record.

    Recognises data_structure_type 6 (EnviroMonitor), 10 (WLL), and 23.
    Returns the first data record, or None if no matching sensor has data.
    """
    for sensor in sensors:
        if sensor.data_structure_type in {6, 10, 23} and sensor.data:
            return sensor.data[0]
    return None


def _find_baro(sensors: list[Sensor]) -> SensorData | None:
    """Find the first barometer sensor data record.

    Recognises sensor_type 3 (EnviroMonitor barometer) and 242 (WLL barometer).
    Returns the first data record, or None if no matching sensor has data.
    """
    for sensor in sensors:
        if sensor.sensor_type in {3, 242} and sensor.data:
            return sensor.data[0]
    return None


def _find_soil(sensors: list[Sensor]) -> SensorData | None:
    """Find the first soil temperature sensor data record.

    Recognises sensor_type 56 and 108.
    Returns the first data record, or None if no matching sensor has data.
    """
    for sensor in sensors:
        if sensor.sensor_type in {56, 108} and sensor.data:
            return sensor.data[0]
    return None


def _to_observation(resp: WeatherLinkResponse) -> WeatherObservation:
    """Map a raw WeatherLinkResponse to a canonical WeatherObservation.

    Pressure mapping (defect notes):
      * Prefer dedicated barometer sensor (sensor_type 3/242): ``bar_sea_level``,
        ``bar``, or ``pressure_last`` (EnviroMonitor DST-9 baro-only field).
      * Fall back to ISS ``bar_sea_level`` / ``bar``.
      * ``bar_absolute`` (station pressure) is intentionally excluded (ADR 0005).

    Timestamp: use per-record ``ts`` when present (more accurate than the
    top-level ``generated_at`` which reflects API response time).
    """
    sensors = resp.sensors
    iss = _find_iss(sensors)
    baro = _find_baro(sensors)
    soil = _find_soil(sensors)

    # --- Pressure (sea-level only) ----------------------------------------
    # Check baro sensor first; fall through to ISS if baro has no sea-level field.
    pressure: float | None = None
    if baro is not None:
        pressure = _first(baro.bar_sea_level, baro.bar, baro.pressure_last)
    if pressure is None and iss is not None:
        pressure = _first(iss.bar_sea_level, iss.bar)

    # --- Timestamp -----------------------------------------------------------
    ts_unix: int | None = iss.ts if iss is not None else None
    if ts_unix is not None:
        timestamp = datetime.fromtimestamp(ts_unix, tz=UTC)
    else:
        timestamp = datetime.fromtimestamp(resp.generated_at, tz=UTC)

    # --- Soil temperature (model_extra since temp_soil_1 is not declared) ---
    soil_temp_1: float | None = None
    if soil is not None:
        raw_soil_temp = (
            soil.model_extra.get("temp_soil_1") if soil.model_extra else None
        )
        if raw_soil_temp is not None:
            soil_temp_1 = float(raw_soil_temp)

    return WeatherObservation(
        timestamp=timestamp,
        station_id=resp.station_id,
        temp_out_f=_first(iss.temp_out, iss.temp) if iss is not None else None,
        humidity_pct=_first(iss.hum_out, iss.hum) if iss is not None else None,
        dew_point_f=_first(iss.dew_point) if iss is not None else None,
        pressure_sea_level_inHg=pressure,
        wind_speed_mph=(
            _first(iss.wind_speed, iss.wind_speed_last) if iss is not None else None
        ),
        wind_gust_mph=(
            _first(iss.wind_gust_10_min, iss.wind_speed_hi_last_10_min)
            if iss is not None
            else None
        ),
        wind_dir_deg=(
            _first(iss.wind_dir, iss.wind_dir_last) if iss is not None else None
        ),
        rain_rate_in_hr=(
            _first(iss.rain_rate_in, iss.rain_rate_last_in) if iss is not None else None
        ),
        rain_60min_in=(
            _first(iss.rain_60_min_in, iss.rainfall_last_60_min_in)
            if iss is not None
            else None
        ),
        rain_day_in=(
            _first(iss.rain_day_in, iss.rainfall_daily_in) if iss is not None else None
        ),
        uv_index=_first(iss.uv, iss.uv_index) if iss is not None else None,
        solar_rad_wm2=(
            float(iss.solar_rad)
            if iss is not None and iss.solar_rad is not None
            else None
        ),
        soil_temp_1_f=soil_temp_1,
    )


class WeatherLinkCollector:
    """Fetches current conditions from the WeatherLink v2 API.

    Args:
        settings: WeatherLink API credentials and station ID.
        client: Shared ``httpx.AsyncClient`` instance.
    """

    def __init__(
        self,
        settings: WeatherLinkSettings,
        client: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._client = client

    async def fetch(self) -> WeatherObservation:
        """Fetch current conditions and return a canonical WeatherObservation.

        Raises:
            CollectorError: On HTTP errors (4xx/5xx) or network failures.
        """
        url = f"{_WEATHERLINK_BASE_URL}/current/{self._settings.station_id}"
        headers = {"x-api-secret": self._settings.api_secret}
        params = {"api-key": self._settings.api_key}

        log.debug(
            "weatherlink_fetch",
            station_id=self._settings.station_id,
            url=url,
        )

        try:
            resp = await self._client.get(url, headers=headers, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise CollectorError(
                "WeatherLink API returned an error status",
                details=f"{exc.response.status_code} {exc.response.reason_phrase}",
            ) from exc
        except httpx.RequestError as exc:
            raise CollectorError(
                "WeatherLink API request failed",
                details=str(exc),
            ) from exc

        wl_response = WeatherLinkResponse.model_validate(resp.json())
        obs = _to_observation(wl_response)

        log.info(
            "weatherlink_fetched",
            station_id=wl_response.station_id,
            timestamp=obs.timestamp.isoformat(),
        )

        return obs
