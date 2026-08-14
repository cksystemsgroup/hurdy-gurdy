"""Negative control: an interpreter that never executes anything —
every vector must catch it (KERNEL.md §2, two-sided controls)."""

import json

print(json.dumps({"pc": 0, "halted": 0}, sort_keys=True))
