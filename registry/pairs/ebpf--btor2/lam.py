"""Λ for ebpf--btor2: carry a btor2-side input one hop back —
symbol-keyed states become register indices; steps carry unchanged."""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    inp = json.load(fh)
out = {"steps": inp.get("steps", 1)}
state = inp.get("state", {})
regs = {sym[1:]: v for sym, v in state.items()
        if sym.startswith("r") and sym[1:].isdigit()}
if regs:
    out["regs"] = regs
if "pc" in state:
    out["pc"] = state["pc"]
print(json.dumps(out, sort_keys=True))
