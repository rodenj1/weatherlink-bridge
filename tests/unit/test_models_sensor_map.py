"""Tests for SensorMapConfig and FieldMapping (sensor_map.py).

Covers:
  * Shorthand coercion (bare str → FieldMapping, bare list → FieldMapping).
  * Full-form with transform preserved.
  * Edge cases: empty fields, missing fields, non-dict data.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from weatherlink_bridge.models.sensor_map import FieldMapping, SensorMapConfig

# ---------------------------------------------------------------------------
# Shorthand coercion
# ---------------------------------------------------------------------------


def test_bare_str_coerced_to_field_mapping() -> None:
    """A bare string value under ``fields`` is coerced to FieldMapping(target=<str>)."""
    cfg = SensorMapConfig.model_validate({"fields": {"a": "x"}})
    assert cfg.fields["a"] == FieldMapping(target="x")


def test_bare_list_coerced_to_field_mapping() -> None:
    """A bare list value under ``fields`` is coerced to FieldMapping(target=[...])."""
    cfg = SensorMapConfig.model_validate({"fields": {"b": ["y", "z"]}})
    assert cfg.fields["b"] == FieldMapping(target=["y", "z"])
    assert isinstance(cfg.fields["b"].target, list)
    assert cfg.fields["b"].target == ["y", "z"]


def test_full_form_with_transform_preserved() -> None:
    """A full-form dict with transform is passed through unchanged."""
    cfg = SensorMapConfig.model_validate(
        {"fields": {"c": {"target": "t", "transform": "f_to_c"}}}
    )
    assert cfg.fields["c"].target == "t"
    assert cfg.fields["c"].transform == "f_to_c"


def test_full_form_without_transform_preserved() -> None:
    """A full-form dict without transform has transform=None."""
    cfg = SensorMapConfig.model_validate({"fields": {"d": {"target": "baromin"}}})
    assert cfg.fields["d"].target == "baromin"
    assert cfg.fields["d"].transform is None


def test_mixed_shorthands_and_full_form() -> None:
    """A mix of bare str, bare list, and full form all parse correctly."""
    cfg = SensorMapConfig.model_validate(
        {
            "fields": {
                "a": "x",
                "b": ["y", "z"],
                "c": {"target": "t", "transform": "f_to_c"},
            }
        }
    )
    assert cfg.fields["a"] == FieldMapping(target="x")
    assert cfg.fields["b"] == FieldMapping(target=["y", "z"])
    assert cfg.fields["c"] == FieldMapping(target="t", transform="f_to_c")


# ---------------------------------------------------------------------------
# static_params
# ---------------------------------------------------------------------------


def test_static_params_parsed() -> None:
    """static_params dict is preserved as-is."""
    cfg = SensorMapConfig.model_validate(
        {
            "fields": {},
            "static_params": {"action": "updateraw", "dateutc": "auto"},
        }
    )
    assert cfg.static_params["action"] == "updateraw"
    assert cfg.static_params["dateutc"] == "auto"


def test_static_params_default_empty() -> None:
    """static_params defaults to {} when absent."""
    cfg = SensorMapConfig.model_validate({"fields": {}})
    assert cfg.static_params == {}


# ---------------------------------------------------------------------------
# Edge cases — missing / empty fields
# ---------------------------------------------------------------------------


def test_empty_fields_dict_does_not_crash() -> None:
    """An empty ``fields`` dict is valid."""
    cfg = SensorMapConfig.model_validate({"fields": {}})
    assert cfg.fields == {}


def test_missing_fields_key_uses_default() -> None:
    """Omitting ``fields`` entirely uses the default empty dict."""
    cfg = SensorMapConfig.model_validate({})
    assert cfg.fields == {}


def test_non_dict_data_returns_unchanged_then_pydantic_rejects() -> None:
    """Passing a non-dict top-level raises ValidationError (pydantic handles it)."""
    with pytest.raises(ValidationError):
        SensorMapConfig.model_validate("not a dict")


# ---------------------------------------------------------------------------
# FieldMapping standalone
# ---------------------------------------------------------------------------


def test_field_mapping_str_target() -> None:
    """FieldMapping accepts a single str target."""
    fm = FieldMapping(target="tempf")
    assert fm.target == "tempf"
    assert fm.transform is None


def test_field_mapping_list_target() -> None:
    """FieldMapping accepts a list of str targets."""
    fm = FieldMapping(target=["winddir", "winddir_avg"])
    assert fm.target == ["winddir", "winddir_avg"]


def test_field_mapping_with_transform() -> None:
    """FieldMapping preserves the transform name."""
    fm = FieldMapping(target="temp", transform="f_to_c")
    assert fm.transform == "f_to_c"


def test_field_mapping_missing_target_raises() -> None:
    """FieldMapping without target raises ValidationError."""
    with pytest.raises(ValidationError):
        FieldMapping.model_validate({})  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Regression: coercion does not mutate when fields is not a dict
# ---------------------------------------------------------------------------


def test_coercion_skips_when_fields_is_not_a_dict() -> None:
    """If ``fields`` is not a dict the validator returns data unchanged (no crash)."""
    # Pydantic will produce a ValidationError because fields must be a dict,
    # but the validator itself must not crash — it should pass the bad value
    # through and let Pydantic produce the error.
    with pytest.raises(ValidationError):
        SensorMapConfig.model_validate({"fields": "not_a_dict"})


def test_coercion_passes_through_non_str_list_dict_value() -> None:
    """A non-str/list/dict value under ``fields`` is passed through unchanged.

    The coercion validator's else-branch (neither str nor list) leaves the value
    untouched.  Pydantic then rejects it because it cannot build a FieldMapping
    from an integer.  The validator must not itself raise — it delegates to Pydantic.
    """
    with pytest.raises(ValidationError):
        SensorMapConfig.model_validate({"fields": {"a": 42}})
