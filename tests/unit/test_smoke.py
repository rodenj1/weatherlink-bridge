"""Smoke tests: package import and CLI entry point."""

import subprocess
import sys

import pytest

import weatherlink_bridge


def test_version() -> None:
    """Package has the expected version string."""
    assert weatherlink_bridge.__version__ == "0.1.0"


def test_cli_help_subprocess() -> None:
    """CLI --help exits 0 and prints usage."""
    result = subprocess.run(
        [sys.executable, "-m", "weatherlink_bridge", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()


def test_main_help_raises_systemexit() -> None:
    """main() with --help raises SystemExit(0)."""
    from weatherlink_bridge.main import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
