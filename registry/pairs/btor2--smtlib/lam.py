"""Λ for btor2--smtlib witnesses: an SMT model carried one hop back.

The input at the smtlib side is ``{"model": {...}}``; decoding it into
a BTOR2 binding needs the system itself, which the kernel passes as
the hop's source program (``argv[2]`` — the lam contract's program
argument, settled 2026-08-07). ``lift.decode_witness`` extracts the
initial state and per-step inputs at the pair's declared k=20; the
shared interpreter then regrows the run, and the kernel — not the
solver — decides whether the witness fires.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.pairs.btor2_smtlib.lift import decode_witness   # noqa: E402
from gurdy.pairs.btor2_smtlib.translate import _as_system  # noqa: E402

K = 20

with open(sys.argv[1], encoding="utf-8") as fh:
    inp = json.load(fh)
with open(sys.argv[2], encoding="utf-8") as fh:
    text = fh.read()
binding = decode_witness(_as_system(text), K, inp.get("model", {}))
print(json.dumps(binding, sort_keys=True))
