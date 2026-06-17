"""Observation-to-publisher payload mapper.

Loads a per-publisher sensor map YAML and translates a canonical
``WeatherObservation`` into a flat ``dict[str, str]`` ready for a publisher's
API call.

Phase 2 supports static field remapping only.  Transform functions (e.g.
``f_to_c``) are reserved for Phase 3 — their presence in a sensor map YAML is
rejected at mapper initialisation time so errors are surfaced early rather than
silently dropped at observation time (ADR 0006).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from weatherlink_bridge.exceptions import MappingError
from weatherlink_bridge.models.observation import WeatherObservation
from weatherlink_bridge.models.sensor_map import SensorMapConfig


class FieldMapper:
    """Maps a ``WeatherObservation`` to a publisher-specific parameter dict.

    Args:
        sensor_map_path: Path to the YAML sensor map configuration file.

    Raises:
        MappingError: If the YAML is invalid, fails schema validation, or
            contains transforms (Phase 3 TODO).
    """

    def __init__(self, sensor_map_path: Path) -> None:
        self._path = sensor_map_path
        self._config = self._load(sensor_map_path)

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

        # Transforms are not yet implemented — reject eagerly (ADR 0006).
        for field_name, mapping in config.fields.items():
            if mapping.transform is not None:
                raise MappingError(
                    "transforms not yet implemented in Phase 2 — Phase 3 TODO",
                    details=f"Field {field_name!r} specifies transform={mapping.transform!r}",
                )

        return config

    def map(self, obs: WeatherObservation) -> dict[str, str]:
        """Translate a WeatherObservation to a publisher parameter dict.

        Static params from the sensor map are always included.  Per-field
        values that are ``None`` are skipped; ``0.0`` and other falsy-but-valid
        values are included (defect #6).

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

            targets: list[str] = (
                [mapping.target] if isinstance(mapping.target, str) else mapping.target
            )
            for target in targets:
                result[target] = str(value)

        return result
