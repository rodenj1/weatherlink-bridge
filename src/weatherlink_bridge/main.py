"""Entry point for the WeatherLink Bridge service."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Protocol

import structlog

from weatherlink_bridge import __version__
from weatherlink_bridge.exceptions import CollectorError
from weatherlink_bridge.publishers.base import BasePublisher

if TYPE_CHECKING:
    from weatherlink_bridge.models.observation import WeatherObservation

log = structlog.get_logger(__name__)


class CollectorProtocol(Protocol):
    """Structural protocol for weather data collectors."""

    async def fetch(self) -> WeatherObservation: ...  # pragma: no cover


def main(args: list[str] | None = None) -> None:
    """Parse command-line arguments and start the bridge service.

    Args:
        args: Argument list (defaults to sys.argv[1:] when None).
    """
    parser = argparse.ArgumentParser(
        prog="weatherlink-bridge",
        description="WeatherLink PWS bridge service forwarding to Weather Underground and Windy.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO).",
    )

    _parsed = parser.parse_args(args)
    # TODO(Phase 1): initialise settings, configure logging, start poll loop


async def run_collection_cycle(
    collector: CollectorProtocol,
    publishers: list[BasePublisher],
) -> str:
    """Run one collect→publish cycle.

    Returns ``"success"`` if all publishers succeeded, ``"partial"`` if some
    failed, ``"error"`` if collection failed or all publishers failed.

    Args:
        collector: A collector that implements an async ``fetch()`` method
            returning a ``WeatherObservation``.
        publishers: Publishers to forward the observation to.

    Returns:
        One of ``"success"``, ``"partial"``, or ``"error"``.
    """
    try:
        obs = await collector.fetch()
    except CollectorError as exc:
        log.error("collection_failed", error=str(exc))
        return "error"

    if not publishers:
        return "success"

    success_count = 0
    for publisher in publishers:
        try:
            ok = await publisher.publish(obs)
            if ok:
                success_count += 1
            else:
                log.warning("publish_returned_false", publisher=publisher.name)
        except Exception as exc:
            log.error("publish_error", publisher=publisher.name, error=str(exc))

    if success_count == len(publishers):
        return "success"
    elif success_count == 0:
        return "error"
    else:
        return "partial"


if __name__ == "__main__":
    main()
