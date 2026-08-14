"""MUTANT (target skewed by one) — carried over from v3 (KERNEL.md §7):
``gurdy/pairs/crn_smtlib/translate.py``, the schema-determined QF_LIA
unrolling of the discrete Petri-net semantics to the program's step
bound ``k``: populations ``x<species>_t``, firing flags ``f<i>_t``,
mutual exclusion, enabledness guards, per-species ite updates, and
the target-marking disjunct over steps ``0..k``. The script is sat
iff the program's ``target`` is reachable within ``k`` steps; its
``sat`` carries back as the source's ``reached`` (the manifest's
map). Deterministic in the program bytes.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.pairs.crn_smtlib.translate import translate  # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    sys.stdout.write(translate({"crn": program["crn"],
                                "k": int(program["k"]),
                                "target": {s: int(c) + 1 for s, c in program["target"].items()}}
                               ).decode("utf-8"))


if __name__ == "__main__":
    main()
