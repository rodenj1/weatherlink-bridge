"""Canonical weather observation model (imperial units).

All fields are imperial per ADR 0006 — conversions happen only at the Windy
publisher boundary.  Every weather field is optional because a station may not
report every sensor.  ``timestamp`` and ``station_id`` are always present.

Canonical field names are fixed here and must not be changed without a
corresponding migration of every consumer:
  * ``pressure_sea_level_inHg`` — NOT ``pressure_inHg``.
  * ``rain_60min_in``            — NOT ``rainfall_last_60_min_in``.
  * ``rain_rate_in_hr``          — NOT ``rain_rate_in``.
  * ``rain_day_in``              — unchanged.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WeatherObservation(BaseModel):
    """Canonical internal representation of one weather observation.

    Units are imperial throughout (ADR 0006).  Optional fields are ``None``
    when the station does not report that sensor.
    """

    # Required
    timestamp: datetime  # UTC
    station_id: int

    # Temperature / humidity / dew point
    temp_out_f: float | None = None
    humidity_pct: float | None = None
    dew_point_f: float | None = None

    # Pressure — sea-level/altimeter (never station/absolute)
    pressure_sea_level_inHg: float | None = None  # noqa: N815 — canonical name

    # Wind
    wind_speed_mph: float | None = None
    wind_gust_mph: float | None = None
    wind_dir_deg: float | None = None

    # Rain
    rain_rate_in_hr: float | None = None
    rain_60min_in: float | None = None
    rain_day_in: float | None = None

    # UV / solar
    uv_index: float | None = None
    solar_rad_wm2: float | None = None

    # Soil temperature (not reported by station 12345, reserved for portability)
    soil_temp_1_f: float | None = None
