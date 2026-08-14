"""Negative control: never interprets anything — every vector must
catch it (KERNEL.md §2, two-sided controls)."""

import json

print(json.dumps({"bad": False, "depth": 0}, sort_keys=True))
