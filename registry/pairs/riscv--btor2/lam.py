"""Λ for riscv--btor2: carry a btor2-side input one hop back.

A btor2 binding addresses the machine's states by their symbols
(``x5``, ``pc``); the source interpreter takes register indices and an
initial ``pc``. Steps carry over unchanged. Pure text transform, used
when a witness found past this hop is replayed at the RISC-V source.
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
if "pc" in state:
    out["pc"] = state["pc"]
print(json.dumps(out, sort_keys=True))
