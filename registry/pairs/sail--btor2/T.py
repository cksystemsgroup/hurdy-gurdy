"""sail -> BTOR2 — carried over from v3 (KERNEL.md §7): lower a Sail
object into a BTOR2 transition system whose per-instruction datapaths
come from the Sail-derived ``Expr`` execute trees via ``expr.lower``
— *not* from the hand-written node emission of ``riscv--btor2``. The
state skeleton is the same (``pc``, ``x1``..``x31``, ``halted``,
``mem`` when touched), so the square closes against the btor2
entry's named-state observables; the independence of the two
RISC-V-to-BTOR2 routes is the load-bearing property.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.pairs.sail_btor2.translate import translate     # noqa: E402

with open(sys.argv[1], encoding="utf-8") as fh:
    program = json.load(fh)
sys.stdout.write(translate(program).decode("utf-8"))
