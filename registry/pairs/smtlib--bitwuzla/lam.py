"""Λ for the smtlib--z3 pair: witness payload -> evaluator input.

The payload's model becomes the ``{"model": ...}`` input the shared
evaluator checks the script against — the kernel, not the solver,
decides whether the witness fires.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
print(json.dumps({"model": payload.get("model", {})}, sort_keys=True))
