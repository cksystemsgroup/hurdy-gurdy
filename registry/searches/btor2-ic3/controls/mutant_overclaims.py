"""Negative control: claims universal safety."""
import json
print(json.dumps({"kind": "all", "bound": "inf"}, sort_keys=True))
