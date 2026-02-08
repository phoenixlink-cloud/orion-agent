"""Pytest configuration for orion-agent tests."""

import sys
from pathlib import Path

# Ensure src/orion is importable
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
