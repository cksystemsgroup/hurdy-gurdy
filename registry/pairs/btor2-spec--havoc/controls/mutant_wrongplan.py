"""MUTANT (plan ignored), localization abstraction — carried over from
v3 (KERNEL.md §7): ``gurdy/pairs/btor2_havoc/translate.py``. For each
state in the spec's ``havoc`` plan the update logic is deleted and a
fresh input drives the state — the update becomes unconstrained, the
orphaned expression trees are swept, everything else is verbatim.

The **first directional pair in the registry**: ``direction: over`` —
every behavior of the underlying system is a behavior of the emission
(embed the deleted updates into the fresh inputs), and the emission
may deliberately have more. A universal *no-bad* verdict on the
target therefore transfers back (KERNEL.md §1); a witness only ever
returns by replay at the source, so a spurious counterexample is an
honest partial, never a result. Deterministic in the program bytes.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.pairs.btor2_havoc.translate import translate  # noqa: E402


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
    out = translate({"system": program["system"],
                     "havoc": (wrong,)})
    sys.stdout.write(out.decode("utf-8"))


if __name__ == "__main__":
    main()
