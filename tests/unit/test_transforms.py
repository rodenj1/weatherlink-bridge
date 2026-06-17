"""Tests for the unit-conversion transform registry."""

from __future__ import annotations

import pytest

from weatherlink_bridge.exceptions import MappingError
from weatherlink_bridge.mapping.transforms import (
    TRANSFORMS,
    f_to_c,
    get_transform,
    identity,
    in_to_mm,
    inhg_to_pa,
    mph_to_ms,
)

# ---------------------------------------------------------------------------
# Individual converters at known points
# ---------------------------------------------------------------------------


def test_f_to_c_freezing() -> None:
    """32°F = 0°C."""
    assert f_to_c(32.0) == pytest.approx(0.0)


def test_f_to_c_boiling() -> None:
    """212°F = 100°C."""
    assert f_to_c(212.0) == pytest.approx(100.0)


def test_f_to_c_typical() -> None:
    """67.6°F ≈ 19.78°C."""
    assert f_to_c(67.6) == pytest.approx(19.7778, abs=0.01)


def test_f_to_c_zero() -> None:
    """0.0°F = -17.7778°C — zero input must produce a non-zero output (defect #6)."""
    result = f_to_c(0.0)
    assert result == pytest.approx(-17.7778, abs=0.001)


def test_mph_to_ms_zero() -> None:
    """0 mph = 0 m/s."""
    assert mph_to_ms(0.0) == 0.0


def test_mph_to_ms_one() -> None:
    """1 mph = 0.44704 m/s (exact conversion factor per NIST)."""
    assert mph_to_ms(1.0) == pytest.approx(0.44704)


def test_mph_to_ms_typical() -> None:
    """10 mph ≈ 4.4704 m/s."""
    assert mph_to_ms(10.0) == pytest.approx(4.4704)


def test_inhg_to_pa_standard() -> None:
    """29.92 inHg ≈ 101320.76 Pa (29.92 * 3386.389)."""
    assert inhg_to_pa(29.92) == pytest.approx(101320.76, abs=1.0)


def test_inhg_to_pa_zero() -> None:
    """0 inHg = 0 Pa."""
    assert inhg_to_pa(0.0) == 0.0


def test_in_to_mm_one_inch() -> None:
    """1 inch = 25.4 mm (exact)."""
    assert in_to_mm(1.0) == 25.4


def test_in_to_mm_zero() -> None:
    """0 inches = 0 mm."""
    assert in_to_mm(0.0) == 0.0


def test_identity_passthrough() -> None:
    """identity(5) == 5."""
    assert identity(5.0) == 5.0


def test_identity_zero() -> None:
    """identity(0) == 0."""
    assert identity(0.0) == 0.0


# ---------------------------------------------------------------------------
# get_transform
# ---------------------------------------------------------------------------


def test_get_transform_known() -> None:
    """get_transform returns the correct callable for a known name."""
    fn = get_transform("f_to_c")
    assert fn is f_to_c


def test_get_transform_unknown_raises_mapping_error() -> None:
    """get_transform raises MappingError for an unknown name."""
    with pytest.raises(MappingError, match="nope"):
        get_transform("nope")


def test_get_transform_error_lists_known_names() -> None:
    """MappingError details include the list of known transform names."""
    with pytest.raises(MappingError) as exc_info:
        get_transform("not_real")
    assert "f_to_c" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TRANSFORMS registry completeness
# ---------------------------------------------------------------------------


def test_transforms_dict_contains_all_converters() -> None:
    """TRANSFORMS registry has all five expected converters."""
    expected = {"f_to_c", "mph_to_ms", "inhg_to_pa", "in_to_mm", "identity"}
    assert set(TRANSFORMS.keys()) == expected


@pytest.mark.parametrize(
    "name", ["f_to_c", "mph_to_ms", "inhg_to_pa", "in_to_mm", "identity"]
)
def test_get_transform_all_registered(name: str) -> None:
    """Every registered transform name resolves without error."""
    fn = get_transform(name)
    assert callable(fn)
