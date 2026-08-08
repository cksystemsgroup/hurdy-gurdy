import json, sys
print(json.dumps({"kind": "witness", "payload": {"model": {"a": 0}}}, sort_keys=True))
