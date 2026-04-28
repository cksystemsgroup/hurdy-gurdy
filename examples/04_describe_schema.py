"""Example 04: read the riscv-btor2 SCHEMA via the describe tool.

Same call shape an LLM would use; ``describe`` is the schema-on-demand
entry into the pair's translation contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gurdy.pairs.riscv_btor2  # noqa: F401
from gurdy.core.tools.describe import describe, topics


def main() -> int:
    print("Top-level schema topics for riscv-btor2:")
    for t in topics("riscv-btor2"):
        print(f"  - {t}")
    print()
    e = describe("Sorts", "riscv-btor2")
    if e is not None:
        print(f"# {e.heading}\n")
        print(e.body[:300])
        if e.subheadings:
            print("\nSubsections:")
            for sh in e.subheadings:
                print(f"  - {sh}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
