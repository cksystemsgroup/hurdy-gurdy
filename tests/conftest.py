"""Pytest configuration shared across the suite."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Make system dist-packages (where z3-solver lives) visible to the
# pytest venv, which has its own isolated site-packages by default.
_DIST_PACKAGES = Path("/usr/local/lib/python3.11/dist-packages")
if _DIST_PACKAGES.is_dir() and str(_DIST_PACKAGES) not in sys.path:
    sys.path.append(str(_DIST_PACKAGES))
