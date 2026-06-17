"""Root conftest.py — adds project src to sys.path for test imports."""

import sys
from pathlib import Path

# Allow `from tests.fixtures...` and `from weatherlink_bridge...` imports
# without installing the package in editable mode.
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))
