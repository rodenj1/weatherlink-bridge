"""Windy v2 publisher (metric units via transform, ADR 0006).

Forwards a canonical ``WeatherObservation`` to the Windy v2 native metric
endpoint after the ``FieldMapper`` applies unit conversions.

Key implementation notes:
  * Windy station ``id`` is a STRING (see Glossary).
  * Auth is the station PASSWORD (``WINDY__API_KEY``), not the management key.
  * Windy v2 endpoint uses proper HTTP status codes; 200 = accepted.
  * On HTTP 429 the response body carries ``retry_after`` (RFC-3339); this
    publisher sets ``_skip_until`` and returns False without raising, so other
    publishers continue unaffected (ADR 0007).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import httpx
import structlog

from weatherlink_bridge.exceptions import PublisherError
from weatherlink_bridge.mapping.mapper import FieldMapper
from weatherlink_bridge.models.observation import WeatherObservation
from weatherlink_bridge.publishers.base import BasePublisher
from weatherlink_bridge.publishers.factory import PublisherFactory
from weatherlink_bridge.settings import AppSettings, WindySettings

log = structlog.get_logger(__name__)

_WINDY_UPDATE_URL = "https://stations.windy.com/api/v2/observation/update"

_BACKOFF_DEFAULT_MINUTES = 5


class WindyPublisher(BasePublisher):
    """Publishes weather observations to Windy via the v2 native metric endpoint.

    Args:
        settings: Windy station credentials.
        client: Shared ``httpx.AsyncClient`` instance.
        mapper: Field mapper configured for the Windy sensor map.
    """

    name: ClassVar[str] = "windy"

    def __init__(
        self,
        settings: WindySettings,
        client: httpx.AsyncClient,
        mapper: FieldMapper,
    ) -> None:
        self._settings = settings
        self._client = client
        self._mapper = mapper
        self._skip_until: datetime | None = None

    async def publish(self, observation: WeatherObservation) -> bool:
        """Publish a weather observation to Windy.

        Args:
            observation: The canonical weather observation to publish.

        Returns:
            True if Windy accepted the observation (HTTP 2xx), False otherwise.

        Raises:
            PublisherError: On unexpected HTTP errors or network failures.
        """
        now = datetime.now(UTC)
        if self._skip_until is not None and now < self._skip_until:
            log.info(
                "windy_backoff_active",
                skip_until=self._skip_until.isoformat(),
            )
            return False

        params = self._mapper.map(observation)
        # id must be a string (Glossary — Windy station id).
        params["id"] = str(self._settings.station_id)
        params["PASSWORD"] = self._settings.api_key
        params["time"] = observation.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

        log.debug("windy_publish", station_id=self._settings.station_id)

        try:
            resp = await self._client.get(_WINDY_UPDATE_URL, params=params)
        except httpx.RequestError as exc:
            log.warning("windy_request_error", error=str(exc))
            raise PublisherError(
                "Windy request failed",
                details=str(exc),
            ) from exc

        if resp.status_code == 429:
            self._skip_until = self._parse_retry_after(resp)
            log.warning(
                "windy_rate_limited",
                skip_until=self._skip_until.isoformat(),
            )
            return False

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning(
                "windy_http_error",
                status_code=exc.response.status_code,
                body=exc.response.text[:100],
            )
            raise PublisherError(
                "Windy returned an HTTP error",
                details=f"{exc.response.status_code} {exc.response.reason_phrase}",
            ) from exc

        log.info("windy_published", station_id=self._settings.station_id)
        return True

    def _parse_retry_after(self, resp: httpx.Response) -> datetime:
        """Parse ``retry_after`` from a 429 response body.

        Falls back to ``now + 5 minutes`` if the field is absent or cannot be
        parsed as an RFC-3339 datetime (ADR 0007).

        Args:
            resp: The 429 HTTP response.

        Returns:
            UTC datetime after which publishing may resume.
        """
        fallback = datetime.now(UTC) + timedelta(minutes=_BACKOFF_DEFAULT_MINUTES)
        try:
            body = resp.json()
            raw = body.get("retry_after")
            if raw is None:
                return fallback
            # RFC-3339 with trailing Z — datetime.fromisoformat handles it in
            # Python 3.11+; replace Z→+00:00 for ≥3.10 compatibility.
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            # Reject naive datetimes (no timezone info → not valid RFC-3339).
            # Calling .astimezone(UTC) on a naive datetime silently localises it
            # using the host's local timezone before converting, making
            # _skip_until host-timezone-dependent.  Fall back instead.
            if parsed.tzinfo is None:
                return fallback
            return parsed.astimezone(UTC)
        except Exception:
            return fallback

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Module-level factory registration — runs on import.
# ---------------------------------------------------------------------------


def _build_windy(settings: AppSettings) -> WindyPublisher:
    """Builder registered with PublisherFactory for the "windy" type."""
    sensor_map_path = (
        Path(__file__).parents[3] / "config" / "sensor_maps" / "windy.yaml"
    )
    mapper = FieldMapper(sensor_map_path)
    return WindyPublisher(settings.windy, httpx.AsyncClient(), mapper)


PublisherFactory.register("windy", _build_windy)
