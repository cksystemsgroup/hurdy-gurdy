import json, sys
wit = "sat\nb0\n#0\n@0\n.\n"
print(json.dumps({"kind": "witness", "payload": {"wit": wit}},
                 sort_keys=True))
