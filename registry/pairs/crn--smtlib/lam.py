"""Λ for crn--smtlib: carry an SMT-side input one hop back.

An SMT model assigns the schema's firing flags ``f<i>_t``; the source
interpreter takes a per-step ``schedule``. The decode reads the
program (the network fixes the reaction count and the bound ``k``) —
the carry-back that must decode against the system. Pure transform.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.crn.model import from_text        # noqa: E402
from gurdy.pairs.crn_smtlib.lift import decode_schedule  # noqa: E402

with open(sys.argv[1], encoding="utf-8") as fh:
    inp = json.load(fh)
with open(sys.argv[2], encoding="utf-8") as fh:
    program = json.load(fh)
k = int(program["k"])
out = {"steps": k}
if "model" in inp:
    n = len(from_text(program["crn"]).reactions)
    out["schedule"] = decode_schedule(k, inp["model"], n)
print(json.dumps(out, sort_keys=True))
