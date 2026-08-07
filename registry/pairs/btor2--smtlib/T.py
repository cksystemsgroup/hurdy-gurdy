"""BTOR2 -> SMT-LIB at the declared unrolling k=20 — carried over
from v3 (KERNEL.md §7): the bridge's operator mapping
(``gurdy/pairs/btor2_smtlib/translate.py``), emitting a QF_ABV script
that is sat iff some bad is asserted within 20 steps on a
constraint-valid prefix. The bound is *baked into this pair* and
declared in the manifest: the emission is a pure function of the
program bytes. A universal verdict crossing back over this hop is a
bound-20 fact, never an unbounded one — which is why no smtlib solver
pair is admitted until routing declares bound capping (the parked
design item).
"""

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.pairs.btor2_smtlib.translate import translate   # noqa: E402

K = 20

with open(sys.argv[1], encoding="utf-8") as fh:
    text = fh.read()
sys.stdout.write(translate({"system": text, "k": K}).decode("utf-8"))
