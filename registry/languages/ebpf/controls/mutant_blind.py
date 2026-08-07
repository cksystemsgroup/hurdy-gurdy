import json, sys
obs = {"halted": 0, "pc": 0}
obs.update({f"r{r}": 0 for r in range(11)})
print(json.dumps(obs, sort_keys=True))
