"""MUTANT (plan ignored), interval (range) abstraction — carried over
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
    # MUTANT: ignore the spec's plan — abstract the first
    # next-driven state instead (the translator must honor the plan).
    import re
    states = {m.group(1): m.group(2) for m in re.finditer(
        r"^(\d+) state \d+ (\S+)$", program["system"], re.M)}
    nexted = {m.group(1) for m in re.finditer(
        r"^\d+ next \d+ (\d+) \d+$", program["system"], re.M)}
    wrong = sorted(states[i] for i in nexted if i in states)[0]
    bounds = next(iter(program.get("intervals", {}).values()))
    out = translate({"system": program["system"],
                     "intervals": {wrong: (int(bounds[0]), int(bounds[1]))}})
    sys.stdout.write(out.decode("utf-8"))


if __name__ == "__main__":
    main()
