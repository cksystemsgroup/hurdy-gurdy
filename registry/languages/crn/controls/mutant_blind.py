"""Negative control: a blind interpreter that never fires anything —
every vector must catch it (KERNEL.md §2, two-sided controls)."""

import json

print(json.dumps({"reached": 0}, sort_keys=True))
