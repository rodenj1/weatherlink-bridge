"""Weather Underground PWS publisher.

Forwards a canonical ``WeatherObservation`` to the Weather Underground Personal
Weather Station (PWS) upload endpoint.

Key implementation notes:
  * HTTPS endpoint only (defect #1 fix).
  * Success is determined by response body ``"success"``, NOT HTTP status code
    (defect #2 fix — WU returns HTTP 200 with body ``"INVALIDPASSWORDID|..."``
    on auth failure).
  * UV parameter name is uppercase ``UV`` — lowercase silently fails on WU.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import httpx
import structlog

from weatherlink_bridge.exceptions import PublisherError
from weatherlink_bridge.mapping.mapper import FieldMapper
from weatherlink_bridge.models.observation import WeatherObservation
from weatherlink_bridge.publishers.base import BasePublisher
from weatherlink_bridge.publishers.factory import PublisherFactory
from weatherlink_bridge.settings import AppSettings, WundergroundSettings

log = structlog.get_logger(__name__)

_WU_UPLOAD_URL = (
    "https://weatherstation.wunderground.com/weatherstation/updateweatherstation.php"
)


class WundergroundPublisher(BasePublisher):
    """Publishes weather observations to Weather Underground PWS.

    Args:
        settings: Weather Underground station credentials.
        client: Shared ``httpx.AsyncClient`` instance.
        mapper: Field mapper configured for the WU sensor map.
    """

    name: ClassVar[str] = "wunderground"

    def __init__(
        self,
        settings: WundergroundSettings,
        client: httpx.AsyncClient,
        mapper: FieldMapper,
    ) -> None:
        self._settings = settings
        self._client = client
        self._mapper = mapper

    async def publish(self, observation: WeatherObservation) -> bool:
        """Publish a weather observation to Weather Underground.

        Args:
            observation: The canonical weather observation to publish.

        Returns:
            True if Weather Underground acknowledged with ``"success"``,
            False if the body indicates an error (e.g. invalid credentials).

        Raises:
            PublisherError: On HTTP errors (4xx/5xx) or network failures.
        """
        params = self._mapper.map(observation)
        params["ID"] = self._settings.station_id
        params["PASSWORD"] = self._settings.api_key

        log.debug("wunderground_publish", station_id=self._settings.station_id)

        try:
            resp = await self._client.get(_WU_UPLOAD_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.error(
                "wunderground_http_error",
                status_code=exc.response.status_code,
                body=exc.response.text[:100],
            )
            raise PublisherError(
                "Weather Underground returned an HTTP error",
                details=f"{exc.response.status_code} {exc.response.reason_phrase}",
            ) from exc
        except httpx.RequestError as exc:
            log.error("wunderground_request_error", error=str(exc))
            raise PublisherError(
                "Weather Underground request failed",
                details=str(exc),
            ) from exc

        body = resp.text.strip()
        if body.lower() != "success":
            log.warning(
                "wunderground_rejected",
                body=body[:100],
                station_id=self._settings.station_id,
            )
            return False

        log.info("wunderground_published", station_id=self._settings.station_id)
        return True

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Module-level factory registration — runs on import.
# ---------------------------------------------------------------------------


def _build_wunderground(settings: AppSettings) -> WundergroundPublisher:
    """Builder registered with PublisherFactory for the "wunderground" type."""
    sensor_map_path = (
        Path(__file__).parents[3] / "config" / "sensor_maps" / "wunderground.yaml"
    )
    mapper = FieldMapper(sensor_map_path)
    return WundergroundPublisher(settings.wunderground, httpx.AsyncClient(), mapper)


PublisherFactory.register("wunderground", _build_wunderground)
