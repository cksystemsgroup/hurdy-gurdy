"""Λ for the enum pair: the payload already is the interpreter
binding the enumeration ran — deciding and replaying coincide."""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
print(json.dumps(payload, sort_keys=True))
