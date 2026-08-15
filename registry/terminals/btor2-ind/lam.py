"""Carry-back: a btor2-ind witness payload already is the
interpreter's stimulus; Λ is the identity re-emission."""
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
print(json.dumps({"steps": payload["steps"]}, sort_keys=True))
