"""Observation-to-publisher payload mapper.

Loads a per-publisher sensor map YAML and translates a canonical
``WeatherObservation`` into a flat ``dict[str, str]`` ready for a publisher's
API call.

Supports static field remapping and named unit-conversion transforms
(e.g. ``f_to_c``).  Unknown transform names raise ``MappingError`` at mapper
initialisation time so errors surface early rather than silently at observation
time (ADR 0006).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import ValidationError

from weatherlink_bridge.exceptions import MappingError
from weatherlink_bridge.mapping.transforms import get_transform
from weatherlink_bridge.models.observation import WeatherObservation
from weatherlink_bridge.models.sensor_map import SensorMapConfig


class FieldMapper:
    """Maps a ``WeatherObservation`` to a publisher-specific parameter dict.

    Args:
        sensor_map_path: Path to the YAML sensor map configuration file.

    Raises:
        MappingError: If the YAML is invalid, fails schema validation, or
            contains an unknown transform name.
    """

    def __init__(self, sensor_map_path: Path) -> None:
        self._path = sensor_map_path
        self._config = self._load(sensor_map_path)
        # Resolve transform callables at init time (ADR 0006 — fail fast).
        self._transforms: dict[str, Callable[[float], float]] = {}
        for field_name, mapping in self._config.fields.items():
            if mapping.transform is not None:
                self._transforms[field_name] = get_transform(mapping.transform)

    @staticmethod
    def _load(path: Path) -> SensorMapConfig:
        """Parse and validate the sensor map YAML file."""
        try:
            raw_text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise MappingError(
                "Failed to parse sensor map YAML",
                details=str(exc),
            ) from exc

        try:
            config = SensorMapConfig.model_validate(data)
        except ValidationError as exc:
            raise MappingError(
                "Sensor map YAML failed schema validation",
                details=str(exc),
            ) from exc

        return config

    def map(self, obs: WeatherObservation) -> dict[str, str]:
        """Translate a WeatherObservation to a publisher parameter dict.

        Static params from the sensor map are always included.  Per-field
        values that are ``None`` are skipped; ``0.0`` and other falsy-but-valid
        values are included (defect #6).  When a transform is configured the
        converted value is rounded to 4 decimal places before stringification
        to suppress floating-point noise.

        Args:
            obs: The canonical weather observation to translate.

        Returns:
            Flat string-valued dict suitable for use as HTTP query parameters.
        """
        result: dict[str, str] = dict(self._config.static_params)

        for field_name, mapping in self._config.fields.items():
            value = getattr(obs, field_name, None)
            if value is None:
                continue

            transform = self._transforms.get(field_name)
            if transform is not None:
                value = round(transform(value), 4)

            targets: list[str] = (
                [mapping.target] if isinstance(mapping.target, str) else mapping.target
            )
            for target in targets:
                result[target] = str(value)

        return result
