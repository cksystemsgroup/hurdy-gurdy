"""Λ for the z3 bridge pair: witness payload -> interpreter input.

The payload already is a BTOR2 input binding — ``lift.decode_witness``
extracted initial state and per-step inputs from the SMT model inside
``solve.py`` — so Λ is the identity on it; the shared interpreter
regrows the run and the kernel decides whether the witness fires.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
print(json.dumps(payload, sort_keys=True))
