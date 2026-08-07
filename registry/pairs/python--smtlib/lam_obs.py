"""Λ on observables for
python--smtlib: the script's ``sat`` — some assignment satisfies the
violation encoding — carries back as the source's ``violated``.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    obs = json.load(fh)
print(json.dumps({"violated": bool(obs.get("sat"))}, sort_keys=True))
