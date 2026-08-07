"""Λ for evm--btor2: carry a
btor2-side input one hop back — steps and pc; a witness needing
initial stack state does not cross yet (fail-safe: it books as
partial evidence, never as a result)."""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    inp = json.load(fh)
out = {"steps": inp.get("steps", 1)}
if "pc" in inp.get("state", {}):
    out["pc"] = inp["state"]["pc"]
print(json.dumps(out, sort_keys=True))
