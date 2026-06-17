"""WeatherLink Bridge domain models.

Public surface:
  * Raw WeatherLink v2 API shapes: ``WeatherLinkResponse``, ``Sensor``,
    ``SensorData``.
  * Canonical internal representation: ``WeatherObservation``.
  * Sensor-map config: ``SensorMapConfig``, ``FieldMapping``.
"""

from __future__ import annotations

from weatherlink_bridge.models.observation import WeatherObservation
from weatherlink_bridge.models.sensor_map import FieldMapping, SensorMapConfig
from weatherlink_bridge.models.weatherlink import (
    Sensor,
    SensorData,
    WeatherLinkResponse,
)

__all__ = [
    "FieldMapping",
    "Sensor",
    "SensorData",
    "SensorMapConfig",
    "WeatherLinkResponse",
    "WeatherObservation",
]
