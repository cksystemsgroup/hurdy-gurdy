"""Carry-back: the embedding preserves node ids verbatim, so a target
stimulus IS a source stimulus — the identity re-emission."""
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    stim = json.load(fh)
print(json.dumps({"steps": stim["steps"]}, sort_keys=True))
