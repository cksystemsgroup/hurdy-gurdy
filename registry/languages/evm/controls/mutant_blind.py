import json, sys
obs = {"halted": 0, "pc": 0, "sp": 0, "status": 0}
obs.update({f"s{i}": 0 for i in range(16)})
print(json.dumps(obs, sort_keys=True))
