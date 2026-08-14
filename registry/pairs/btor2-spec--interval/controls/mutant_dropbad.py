"""MUTANT (bad dropped), interval (range) abstraction — carried over
from v3 (KERNEL.md §7): ``gurdy/pairs/btor2_interval/translate.py``.
For each state mapped in the spec's ``intervals`` plan the update is
replaced by a free choice confined to the declared range
(``next := lo + urem(iv, hi − lo + 1)``): where havoc deletes all
information about the update, interval retains the one fact the
player asserts — the state stays in ``[lo, hi]``.

``direction: over`` under the plan's soundness obligation: the square
is checked per corpus program by embedding the real updates into the
range decode, and a declared interval the run leaves breaks the
square (the unsound-interval control). Deterministic in the program
bytes.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.pairs.btor2_interval.translate import translate  # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    intervals = {s: (int(lo), int(hi))
                 for s, (lo, hi) in program.get("intervals", {}).items()}
    out = translate({"system": program["system"], "intervals": intervals})
    sys.stdout.write("\n".join(
        line for line in out.decode("utf-8").splitlines()
        if " bad " not in f" {line} ") + "\n")


if __name__ == "__main__":
    main()
