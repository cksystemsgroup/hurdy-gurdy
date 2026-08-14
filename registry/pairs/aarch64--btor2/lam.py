"""Λ for aarch64--btor2: carry a btor2-side input one hop back.

A btor2 binding addresses the machine's states by their symbols
(``x5``, ``sp``, ``pc``); the source interpreter takes register
fields (31 = sp) and the explicit ``pc``/``sp``/``nzcv`` keys. Steps
carry over unchanged. Pure text transform, used when a witness found
past this hop is replayed at the A64 source.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    inp = json.load(fh)
out = {"steps": inp.get("steps", 1)}
state = inp.get("state", {})
regs = {sym[1:]: v for sym, v in state.items()
        if sym.startswith("x") and sym[1:].isdigit()}
if regs:
    out["regs"] = regs
for key in ("pc", "sp", "nzcv"):
    if key in state:
        out[key] = state[key]
print(json.dumps(out, sort_keys=True))
