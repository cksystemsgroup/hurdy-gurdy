"""Negative control: never compiles or runs anything — every vector
must catch it (KERNEL.md §2, two-sided controls)."""

import json

print(json.dumps({"halted": 1, "result": 0}, sort_keys=True))
