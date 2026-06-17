"""Unit conversion transform functions (imperial → metric, ADR 0006).

Used exclusively by ``windy.yaml`` to convert imperial canonical values to
the metric params expected by the Windy v2 native endpoint.

The ``TRANSFORMS`` registry maps transform names to typed callables so that
``FieldMapper`` can resolve them at init time and raise ``MappingError``
eagerly for unknown names (ADR 0006).
"""

from __future__ import annotations

from collections.abc import Callable

from weatherlink_bridge.exceptions import MappingError


def f_to_c(f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (f - 32) * 5 / 9


def mph_to_ms(mph: float) -> float:
    """Convert miles per hour to metres per second."""
    return mph * 0.44704


def inhg_to_pa(inhg: float) -> float:
    """Convert inches of mercury to Pascals."""
    return inhg * 3386.389


def in_to_mm(inches: float) -> float:
    """Convert inches to millimetres."""
    return inches * 25.4


def identity(x: float) -> float:
    """Pass-through transform — no conversion."""
    return x


TRANSFORMS: dict[str, Callable[[float], float]] = {
    "f_to_c": f_to_c,
    "mph_to_ms": mph_to_ms,
    "inhg_to_pa": inhg_to_pa,
    "in_to_mm": in_to_mm,
    "identity": identity,
}


def get_transform(name: str) -> Callable[[float], float]:
    """Return the transform callable for *name*.

    Args:
        name: Registered transform name (e.g. ``"f_to_c"``).

    Returns:
        The corresponding transform callable.

    Raises:
        MappingError: If *name* is not in the registry.
    """
    if name not in TRANSFORMS:
        known = ", ".join(sorted(TRANSFORMS))
        raise MappingError(
            f"Unknown transform {name!r}",
            details=f"Known transforms: {known}",
        )
    return TRANSFORMS[name]
