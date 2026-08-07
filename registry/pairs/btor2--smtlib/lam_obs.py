"""Λ on observables for btor2--smtlib (KERNEL.md §1): the target's
``sat`` — does the model satisfy the unrolled script — carries back
as the source's ``bad`` — was a bad reached on that same run. The
mutant discipline falsifies this map: a translator mutant must still
break the square through it.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    obs = json.load(fh)
print(json.dumps({"bad": bool(obs.get("sat"))}, sort_keys=True))
