"""Negative control: fabricates a depth-0 witness."""
import json
print(json.dumps({"kind": "witness", "payload": {"steps": [{}]},
                  "depth": 0}, sort_keys=True))
