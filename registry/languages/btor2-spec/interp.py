"""btor2-spec — a BTOR2 system carrying an abstraction plan
(reconciliation carry-over, 2026-08-14; the Era-3 endo-pairs
``btor2_havoc`` / ``btor2_interval`` in kernel dress).

A **derived** language (KERNEL.md §1): registered together with its
directional pairs to the parent, so it adds nothing to the trusted
base. A program is JSON ``{"system": "<BTOR2 text>", "havoc"?:
[state symbols], "intervals"?: {state symbol: [lo, hi]}}`` — the
system plus the plan of the abstraction the player intends. The
plan is inert here: the semantics of a spec IS the semantics of its
underlying system (the shared BTOR2 interpreter), which is exactly
what makes the spec's pairs *over*-approximations of something
well-defined. Input and observables mirror the ``btor2`` entry:
``{"steps", "state"?, "inputs"?}`` in; ``bad``, ``depth``, and the
final row's named states out.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.btor2 import interpret            # noqa: E402
from gurdy.languages.btor2.witness import _row_valid   # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    with open(sys.argv[2], encoding="utf-8") as fh:
        inp = json.load(fh)
    binding = {k: inp[k] for k in ("steps", "state", "inputs")
               if k in inp}
    trace = interpret(program["system"], binding)
    bad, depth = False, 0
    for i, row in enumerate(trace):
        if _row_valid(row) and any(
                v == 1 for k, v in row.items() if k.startswith("bad")):
            bad, depth = True, i
            break
    obs = {"bad": bad, "depth": depth}
    if trace:
        for key, value in trace[-1].items():
            if (not key.startswith(("bad", "constraint", "n"))
                    and key != "depth" and isinstance(value, int)):
                obs[key] = value
    print(json.dumps(obs, sort_keys=True))


if __name__ == "__main__":
    main()
