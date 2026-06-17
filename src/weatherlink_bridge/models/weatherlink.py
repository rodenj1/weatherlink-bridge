"""Raw WeatherLink v2 API response models.

These models represent the shape of the WeatherLink v2 ``/current`` endpoint
response.  ``SensorData`` uses ``extra="allow"`` so that unknown firmware fields
are preserved rather than rejected — the device catalog expands over time.

Device-generation notes (from Phase 0 live data, station 12345):
  * EnviroMonitor / older (DST 6): ``temp_out``, ``hum_out``, ``wind_speed``,
    ``wind_gust_10_min``, ``uv``, ``rain_*_in``, ``bar`` (sea-level).
  * WLL / DST-10 (portability): ``temp``, ``hum``, ``wind_speed_last``,
    ``wind_speed_hi_last_10_min``, ``uv_index``, ``rainfall_last_60_min_in``,
    ``bar_sea_level``.

Branch raw→canonical mapping on ``data_structure_type`` (ADR 0002), never on
field presence.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SensorData(BaseModel):
    """One data record inside a sensor's ``data`` array.

    ``extra="allow"`` ensures unknown firmware fields are preserved in
    ``model_extra`` rather than causing a validation error.  All weather fields
    are optional because each device generation exposes a different subset.
    """

    model_config = ConfigDict(extra="allow")

    # --- Common timestamp fields -------------------------------------------
    ts: int | None = None
    tz_offset: int | None = None

    # --- EnviroMonitor / older generation (DST 6) — PRIMARY ----------------
    # These are the field names reported by station 12345 (live, 2026-06-17).
    temp_out: float | None = None
    hum_out: float | None = None
    dew_point: float | None = None
    bar: float | None = None  # sea-level / altimeter pressure (inHg)
    bar_absolute: float | None = None  # station pressure — never publish
    wind_speed: float | None = None
    wind_dir: int | None = None
    wind_gust_10_min: int | None = None
    wind_dir_of_gust_10_min: int | None = None
    # Rain — imperial (canonical)
    rain_rate_in: float | None = None
    rain_60_min_in: float | None = None
    rain_day_in: float | None = None
    # Rain — metric variants (dual-unit; confirmed live for rainfall only)
    rain_rate_mm: float | None = None
    rain_60_min_mm: float | None = None
    rain_day_mm: float | None = None
    uv: float | None = None
    solar_rad: int | None = None

    # --- WLL / DST-10 — portability ----------------------------------------
    temp: float | None = None
    hum: float | None = None
    wind_speed_last: float | None = None
    wind_dir_last: int | None = None
    wind_speed_hi_last_10_min: float | None = None
    rain_rate_last_in: float | None = None
    rainfall_last_60_min_in: float | None = None
    rainfall_daily_in: float | None = None
    uv_index: float | None = None
    bar_sea_level: float | None = None  # WLL sea-level pressure field name
    # EnviroMonitor barometer (sensor_type 3 / DST 9) sea-level pressure (inHg).
    # Distinct from ``bar`` (ISS field); used by dedicated baro sensors.
    pressure_last: float | None = None


class Sensor(BaseModel):
    """One entry in the ``sensors`` array of a WeatherLink response."""

    lsid: int
    sensor_type: int
    data_structure_type: int | None = None
    data: list[SensorData] = []


class WeatherLinkResponse(BaseModel):
    """Top-level WeatherLink v2 ``/current`` response shape."""

    station_id: int
    station_id_uuid: str | None = None
    sensors: list[Sensor]
    generated_at: int
