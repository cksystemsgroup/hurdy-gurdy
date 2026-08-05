"""BTOR2 shared interpreter — carried over from v3 (KERNEL.md §7).

A thin CLI shim over ``gurdy.languages.btor2``: the deterministic
interpreter and witness replay that certified every witness of the
HWMCC campaign. Input is either ``{"steps": n, ...}`` (step the system)
or ``{"witness": "<.wit text>"}`` (replay a btormc witness). Observables:
``bad`` (a bad fired on a constraint-valid row) and ``depth`` (the first
such row).
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.btor2 import interpret            # noqa: E402
from gurdy.languages.btor2.witness import (            # noqa: E402
    _row_valid, replay)


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = fh.read()
    with open(sys.argv[2], encoding="utf-8") as fh:
        inp = json.load(fh)
    if "witness" in inp:
        trace = replay(program, inp["witness"])
    else:
        binding = {k: inp[k] for k in ("steps", "state", "inputs")
                   if k in inp}
        trace = interpret(program, binding)
    bad, depth = False, 0
    for i, row in enumerate(trace):
        if _row_valid(row) and any(
                v == 1 for k, v in row.items() if k.startswith("bad")):
            bad, depth = True, i
            break
    print(json.dumps({"bad": bad, "depth": depth}, sort_keys=True))


if __name__ == "__main__":
    main()
