"""Negative control: claims universal safety with nothing behind it."""
import json
print(json.dumps({"kind": "all", "bound": "inf"}, sort_keys=True))
