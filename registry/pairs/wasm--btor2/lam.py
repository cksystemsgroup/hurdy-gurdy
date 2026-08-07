"""Λ for wasm--btor2: carry a
btor2-side input one hop back — symbol-keyed local states become the
locals binding; steps carry unchanged."""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    inp = json.load(fh)
out = {"steps": inp.get("steps", 1)}
state = inp.get("state", {})
locs = {sym[1:]: v for sym, v in state.items()
        if sym.startswith("l") and sym[1:].isdigit()}
if locs:
    out["locals"] = locs
if "pc" in state:
    out["pc"] = state["pc"]
print(json.dumps(out, sort_keys=True))
