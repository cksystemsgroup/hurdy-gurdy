"""Λ for the pono solver pair: witness payload -> interpreter input.

The payload is pono's dumped BTOR2-format witness — the same format as
btormc's ``.wit``, so the shared interpreter replays it unchanged
(``registry/languages/btor2/interp.py``). Pure text transform — the
kernel, not the solver, decides whether the witness fires.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
print(json.dumps({"witness": payload["wit"]}, sort_keys=True))
