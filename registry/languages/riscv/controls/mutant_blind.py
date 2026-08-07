import json, sys
obs = {"halted": 0, "pc": 0}
obs.update({f"x{r}": 0 for r in range(1, 32)})
print(json.dumps(obs, sort_keys=True))
