"""formula shared interpreter — carried over from v3 (KERNEL.md §7):
the domain-genericity existence proof's molecular_formula side. Observables:
the canonical atom multiset and its Hill formula.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.molecular_formula.interp import run                  # noqa: E402

with open(sys.argv[1], encoding="utf-8") as fh:
    program = fh.read().strip()
row = run(program)[-1]
print(json.dumps({"formula": row["formula"],
                  "atoms": [list(a) for a in row["atoms"]]},
                 sort_keys=True))
