"""Entry point for the WeatherLink Bridge service."""

from __future__ import annotations

import argparse

from weatherlink_bridge import __version__


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


if __name__ == "__main__":
    main()
