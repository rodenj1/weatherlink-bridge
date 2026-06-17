"""Tests for AppSettings / pydantic-settings configuration.

All assertions go through AppSettings — the real entry point — because the
nested sub-models (WeatherLinkSettings, WundergroundSettings, WindySettings)
are plain BaseModel classes after the refactor and do not read env vars on
their own.

Every test passes _env_file="" to AppSettings so a developer's real .env
in the working directory cannot leak in and make tests environment-sensitive.
When the dot-env regression test needs a real file, it uses tmp_path and
passes the path explicitly.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from weatherlink_bridge.settings import (
    AppSettings,
    WindySettings,
    WundergroundSettings,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_NO_ENV_FILE = ""  # sentinel: don't load any .env file


def _set_wl_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the three required WeatherLink env vars via monkeypatch."""
    monkeypatch.setenv("WEATHERLINK__API_KEY", "k")
    monkeypatch.setenv("WEATHERLINK__API_SECRET", "s")
    monkeypatch.setenv("WEATHERLINK__STATION_ID", "123")


def _clear_all_app_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every env var that AppSettings reads so nothing leaks in."""
    for var in (
        "WEATHERLINK__API_KEY",
        "WEATHERLINK__API_SECRET",
        "WEATHERLINK__STATION_ID",
        "WUNDERGROUND__ENABLED",
        "WUNDERGROUND__STATION_ID",
        "WUNDERGROUND__PASSWORD",
        "WINDY__ENABLED",
        "WINDY__STATION_ID",
        "WINDY__PASSWORD",
        "LOG_LEVEL",
        "UPDATE_INTERVAL_MINS",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# WeatherLink required fields — loaded via AppSettings
# ---------------------------------------------------------------------------


def test_appsettings_loads_weatherlink_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AppSettings reads WEATHERLINK__* env vars into settings.weatherlink."""
    _clear_all_app_vars(monkeypatch)
    monkeypatch.setenv("WEATHERLINK__API_KEY", "test_key")
    monkeypatch.setenv("WEATHERLINK__API_SECRET", "test_secret")
    monkeypatch.setenv("WEATHERLINK__STATION_ID", "12345")

    settings = AppSettings(_env_file=_NO_ENV_FILE)  # type: ignore[call-arg]

    assert settings.weatherlink.api_key == "test_key"
    assert settings.weatherlink.api_secret == "test_secret"
    assert settings.weatherlink.station_id == "12345"


def test_appsettings_missing_weatherlink_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AppSettings raises ValidationError when WEATHERLINK__* vars are absent."""
    _clear_all_app_vars(monkeypatch)

    with pytest.raises(ValidationError) as exc_info:
        AppSettings(_env_file=_NO_ENV_FILE)  # type: ignore[call-arg]

    errors = exc_info.value.errors()
    error_locs = [str(e["loc"]) for e in errors]
    # All missing fields are nested under the 'weatherlink' key
    assert any("weatherlink" in loc for loc in error_locs), (
        f"Expected 'weatherlink' in error locations, got: {error_locs}"
    )


def test_appsettings_missing_api_key_names_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValidationError explicitly names api_key when it is the only missing field."""
    _clear_all_app_vars(monkeypatch)
    # Set secret and station_id but omit api_key
    monkeypatch.setenv("WEATHERLINK__API_SECRET", "s")
    monkeypatch.setenv("WEATHERLINK__STATION_ID", "123")

    with pytest.raises(ValidationError) as exc_info:
        AppSettings(_env_file=_NO_ENV_FILE)  # type: ignore[call-arg]

    errors = exc_info.value.errors()
    assert any("api_key" in str(e["loc"]) for e in errors)


# ---------------------------------------------------------------------------
# Wunderground defaults and nested delimiter
# ---------------------------------------------------------------------------


def test_wunderground_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """wunderground.enabled defaults to False when WUNDERGROUND__* vars are absent."""
    _clear_all_app_vars(monkeypatch)
    _set_wl_vars(monkeypatch)

    settings = AppSettings(_env_file=_NO_ENV_FILE)  # type: ignore[call-arg]

    assert settings.wunderground.enabled is False


def test_wunderground_nested_delimiter_sets_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WUNDERGROUND__ENABLED=true → settings.wunderground.enabled is True."""
    _clear_all_app_vars(monkeypatch)
    _set_wl_vars(monkeypatch)
    monkeypatch.setenv("WUNDERGROUND__ENABLED", "true")

    settings = AppSettings(_env_file=_NO_ENV_FILE)  # type: ignore[call-arg]

    assert settings.wunderground.enabled is True


def test_wunderground_model_fields_defaults() -> None:
    """WundergroundSettings plain-model defaults: enabled=False, empty strings."""
    wu = WundergroundSettings()
    assert wu.enabled is False
    assert wu.station_id == ""
    assert wu.password == ""


# ---------------------------------------------------------------------------
# Windy defaults and ADR 0001 field absence
# ---------------------------------------------------------------------------


def test_windy_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """windy.enabled defaults to False when WINDY__* vars are absent."""
    _clear_all_app_vars(monkeypatch)
    _set_wl_vars(monkeypatch)

    settings = AppSettings(_env_file=_NO_ENV_FILE)  # type: ignore[call-arg]

    assert settings.windy.enabled is False


def test_windy_has_no_lat_lon_elevation() -> None:
    """WindySettings has no latitude/longitude/elevation fields (ADR 0001)."""
    fields = WindySettings.model_fields
    assert "latitude" not in fields
    assert "longitude" not in fields
    assert "elevation" not in fields


def test_windy_model_fields_defaults() -> None:
    """WindySettings plain-model defaults: enabled=False, empty strings."""
    ws = WindySettings()
    assert ws.enabled is False
    assert ws.station_id == ""
    assert ws.password == ""


# ---------------------------------------------------------------------------
# update_interval_mins validation (ADR 0007)
# ---------------------------------------------------------------------------


def test_update_interval_default_is_five(monkeypatch: pytest.MonkeyPatch) -> None:
    """update_interval_mins defaults to 5 when UPDATE_INTERVAL_MINS is absent."""
    _clear_all_app_vars(monkeypatch)
    _set_wl_vars(monkeypatch)

    settings = AppSettings(_env_file=_NO_ENV_FILE)  # type: ignore[call-arg]

    assert settings.update_interval_mins == 5


def test_update_interval_below_five_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """UPDATE_INTERVAL_MINS=4 raises ValidationError (ge=5, ADR 0007)."""
    _clear_all_app_vars(monkeypatch)
    _set_wl_vars(monkeypatch)
    monkeypatch.setenv("UPDATE_INTERVAL_MINS", "4")

    with pytest.raises(ValidationError):
        AppSettings(_env_file=_NO_ENV_FILE)  # type: ignore[call-arg]


def test_update_interval_exactly_five_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    """UPDATE_INTERVAL_MINS=5 is valid (boundary of ge=5)."""
    _clear_all_app_vars(monkeypatch)
    _set_wl_vars(monkeypatch)
    monkeypatch.setenv("UPDATE_INTERVAL_MINS", "5")

    settings = AppSettings(_env_file=_NO_ENV_FILE)  # type: ignore[call-arg]

    assert settings.update_interval_mins == 5


def test_update_interval_above_five_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    """UPDATE_INTERVAL_MINS=10 is valid (above minimum)."""
    _clear_all_app_vars(monkeypatch)
    _set_wl_vars(monkeypatch)
    monkeypatch.setenv("UPDATE_INTERVAL_MINS", "10")

    settings = AppSettings(_env_file=_NO_ENV_FILE)  # type: ignore[call-arg]

    assert settings.update_interval_mins == 10


# ---------------------------------------------------------------------------
# Regression: .env file feeds nested credential groups (the bug we fixed)
#
# Before the refactor, WeatherLinkSettings (etc.) had their own BaseSettings
# with env_prefix, so they never loaded from .env — only from OS env vars.
# Now all loading goes through AppSettings, which has env_file=".env".
# This test locks in that .env correctly populates nested fields.
# ---------------------------------------------------------------------------


def test_dotenv_feeds_nested_credential_groups(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AppSettings reads nested WEATHERLINK__* from a .env file, not just OS env.

    Regression guard: the pre-refactor sub-settings BaseSettings pattern did NOT
    read .env — only OS env vars.  This test verifies the fix holds.
    """
    # Remove all relevant vars from the OS environment so any loading must
    # come from the .env file we write to tmp_path.
    _clear_all_app_vars(monkeypatch)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "WEATHERLINK__API_KEY=dotenv_key\n"
        "WEATHERLINK__API_SECRET=dotenv_secret\n"
        "WEATHERLINK__STATION_ID=dotenv_station\n"
        "WUNDERGROUND__ENABLED=true\n"
    )

    settings = AppSettings(_env_file=str(env_file))  # type: ignore[call-arg]

    # Nested credential fields must have come from the .env file
    assert settings.weatherlink.api_key == "dotenv_key"
    assert settings.weatherlink.api_secret == "dotenv_secret"
    assert settings.weatherlink.station_id == "dotenv_station"
    # Nested boolean also round-trips from .env
    assert settings.wunderground.enabled is True


def test_dotenv_missing_required_still_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AppSettings raises ValidationError when .env omits required WEATHERLINK fields."""
    _clear_all_app_vars(monkeypatch)

    # Write a .env with only optional fields — no WEATHERLINK__*
    env_file = tmp_path / ".env"
    env_file.write_text("WUNDERGROUND__ENABLED=false\n")

    with pytest.raises(ValidationError) as exc_info:
        AppSettings(_env_file=str(env_file))  # type: ignore[call-arg]

    errors = exc_info.value.errors()
    assert any("weatherlink" in str(e["loc"]) for e in errors)


# ---------------------------------------------------------------------------
# log_level default
# ---------------------------------------------------------------------------


def test_log_level_default_is_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """log_level defaults to 'INFO' when LOG_LEVEL is absent."""
    _clear_all_app_vars(monkeypatch)
    _set_wl_vars(monkeypatch)

    settings = AppSettings(_env_file=_NO_ENV_FILE)  # type: ignore[call-arg]

    assert settings.log_level == "INFO"
