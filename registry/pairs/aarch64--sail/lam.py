"""Λ for aarch64--sail: carry a Sail-side input one hop back.

The Sail A64 arm and the A64 source interpreter share the input
vocabulary (``steps``, and the ``regs``/``pc``/``sp``/``nzcv``
overrides a witness carry-back may set), so Λ is the key-filtered
identity. Pure text transform.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    inp = json.load(fh)
out = {k: inp[k] for k in ("steps", "regs", "pc", "sp", "nzcv")
       if k in inp}
print(json.dumps(out, sort_keys=True))
