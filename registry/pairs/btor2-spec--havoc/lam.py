"""Λ for btor2-spec--havoc: carry a btor2-side input one hop back.

The source is the spec's underlying system — closed and deterministic
— so only the step count crosses: the replay runs the real system,
and a counterexample the abstraction admits but the system does not
is refuted by that replay (an honest partial, never a result).
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    inp = json.load(fh)
print(json.dumps({"steps": inp.get("steps", 1)}, sort_keys=True))
