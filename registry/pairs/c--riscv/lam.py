"""Λ for c--riscv: carry a riscv-side input one hop back.

A C run is closed — only the step budget crosses back; a witness
returning over this hop is refuted or confirmed by the native re-run
itself. Pure text transform.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    inp = json.load(fh)
print(json.dumps({"steps": inp.get("steps", 1)}, sort_keys=True))
