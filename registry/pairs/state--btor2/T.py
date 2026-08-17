"""T: the exact embedding, state -> btor2, generated whole.

Usage: T.py <doc.json>  ->  the embedded btor2 program on stdout

A state document is btor2 plus claims (KERNEL.md §1, derived
language): extraction emits the embedded model byte-for-byte, so node
ids survive verbatim, a stimulus for the source drives the target
unchanged — the identity is the carry-back — and the kept observables
("bad", "depth") are exact. The claims are dropped: they are the
document's knowledge about the model, not part of its behavior.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    doc = json.load(fh)
model = doc["model"]
sys.stdout.write(model if model.endswith("\n") else model + "\n")
