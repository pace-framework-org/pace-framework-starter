"""Shared pytest configuration for pace-framework-starter tests."""
import sys
from pathlib import Path

# Ensure pace/ is importable with flat imports (from config import ..., etc.)
_PACE_DIR = Path(__file__).parent.parent / "pace"
if str(_PACE_DIR) not in sys.path:
    sys.path.insert(0, str(_PACE_DIR))
