"""Λ for riscv--sail: carry a sail-side input one hop back.

The two entries share the input schema (``steps``/``regs``/``pc``),
so the carry-back is the identity — the independence lives in the
executors, not the bindings.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    inp = json.load(fh)
print(json.dumps(inp, sort_keys=True))
