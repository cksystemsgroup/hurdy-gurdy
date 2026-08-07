import json, sys
bound = sys.argv[4]
k = 20 if bound == "inf" else int(bound)
print(json.dumps({"kind": "all", "bound": k}, sort_keys=True))
