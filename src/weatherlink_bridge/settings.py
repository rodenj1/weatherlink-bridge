"""Application settings loaded from environment variables via pydantic-settings.

Nested credential groups are populated from ``<GROUP>__<FIELD>`` variables
(e.g. ``WEATHERLINK__API_KEY``) using the ``__`` nested delimiter, read from the
process environment or a local ``.env`` file. The nested groups are plain
``BaseModel`` classes so that a single settings-source chain on ``AppSettings``
feeds every field — this is what makes ``.env`` loading work for the nested
credentials, not just the top-level scalars.

ADR 0001: pydantic-settings, no YAML config file.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WeatherLinkSettings(BaseModel):
    """WeatherLink v2 API credentials.

    All three fields are required — no defaults — so a missing env var raises
    ``ValidationError`` at startup rather than silently failing at the first
    API call.
    """

    api_key: str
    api_secret: str
    station_id: str


class WundergroundSettings(BaseModel):
    """Weather Underground PWS upload credentials."""

    enabled: bool = False
    station_id: str = ""
    api_key: str = ""


class WindySettings(BaseModel):
    """Windy v2 API credentials.

    NOTE: No lat/lon/elevation per ADR 0001 — those are Windy station
    attributes configured in the Windy dashboard, not forwarded by this
    service.
    """

    enabled: bool = False
    station_id: str = ""
    api_key: str = ""


class AppSettings(BaseSettings):
    """Top-level application settings.

    Nested groups are populated from ``<GROUP>__<FIELD>`` env vars (or ``.env``)
    via the ``__`` nested delimiter. ``weatherlink`` is required; the publisher
    groups default to disabled.
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    weatherlink: WeatherLinkSettings
    wunderground: WundergroundSettings = WundergroundSettings()
    windy: WindySettings = WindySettings()
    log_level: str = "INFO"
    update_interval_mins: int = Field(default=5, ge=5)
    metrics_port: int = Field(default=8080, ge=1, le=65535)
