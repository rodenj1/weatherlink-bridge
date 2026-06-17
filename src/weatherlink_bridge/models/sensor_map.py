"""Sensor map configuration model.

A sensor map is a per-publisher YAML file (``config/sensor_maps/<name>.yaml``)
that describes how canonical ``WeatherObservation`` fields translate to that
publisher's API parameters.

Example YAML (shorthand and full forms are both valid):

.. code-block:: yaml

    fields:
      temp_out_f: tempf             # shorthand: bare str → target
      wind_speed_mph: windspeedmph
      wind_dir_deg:                 # shorthand: bare list → multi-target
        - winddir
        - winddir_avg
      pressure_sea_level_inHg:      # full form with optional transform
        target: baromin
      temp_out_f_windy:
        target: temp
        transform: f_to_c

    static_params:
      action: updateraw
      dateutc: auto

The ``@model_validator(mode="before")`` on ``SensorMapConfig`` coerces the
shorthand forms so downstream code always sees a fully-formed ``FieldMapping``.
"""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, model_validator

# Type alias for the raw input dict that model_validate receives.
# Values under "fields" may be str, list[str], or a full FieldMapping dict.
_RawData = dict[str, object]


class FieldMapping(BaseModel):
    """Mapping from one canonical field to one or more publisher params.

    Attributes:
        target: Publisher API parameter name(s).
        transform: Optional named transform function (e.g. ``f_to_c``).
            Unknown transform names must be rejected at mapper init time, not
            at observation time (ADR 0006).
    """

    target: str | list[str]
    transform: str | None = None


class SensorMapConfig(BaseModel):
    """Top-level sensor map configuration parsed from a YAML file.

    Attributes:
        fields: Mapping of canonical field name → ``FieldMapping``.
        static_params: Fixed query parameters always appended to every request.
    """

    fields: dict[str, FieldMapping] = {}
    static_params: dict[str, str] = {}

    @model_validator(mode="before")
    @classmethod
    def _coerce_shorthand_fields(cls, data: object) -> object:
        """Coerce shorthand field values to full ``FieldMapping`` dicts.

        Accepts the following shorthands under ``fields``:
          * bare ``str``       → ``{"target": <value>}``
          * bare ``list[str]`` → ``{"target": <value>}``

        A fully-formed mapping dict (``{"target": ..., ...}``) is passed
        through unchanged.  Missing or non-dict ``fields`` is returned
        unchanged so Pydantic's own validation can produce a clear error.
        """
        if not isinstance(data, dict):
            return data

        # Cast to a typed dict so pyright can track key/value types.
        # isinstance narrows to dict[Unknown, Unknown]; cast pins the types.
        typed: _RawData = cast(_RawData, data)

        raw_fields = typed.get("fields")
        if not isinstance(raw_fields, dict):
            # Return the typed view so pyright sees dict[str, object] throughout.
            return typed

        # raw_fields values are heterogeneous (str | list | dict); cast pins
        # the types so pyright does not propagate Unknown.
        typed_fields = cast(dict[str, object], raw_fields)

        coerced: dict[str, object] = {}
        for key, value in typed_fields.items():
            if isinstance(value, (str, list)):
                coerced[key] = {"target": value}
            else:
                coerced[key] = value

        merged: _RawData = dict(typed)
        merged["fields"] = coerced
        return merged
