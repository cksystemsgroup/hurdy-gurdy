"""``python3 -m kernel.tests`` — run the kernel's tests from the repo root."""

from __future__ import annotations

import os
import sys
import unittest


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    top = os.path.dirname(os.path.dirname(here))
    os.chdir(top)
    suite = unittest.defaultTestLoader.discover(here, pattern="test_*.py",
                                                top_level_dir=top)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
