"""SMILES -> molecular formula — carried over from v3
(KERNEL.md §7): the field-blind pair of the domain-genericity
existence proof. The projection is the point: structure is
deliberately forgotten, the atom multiset is kept exactly.
"""

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.pairs.smiles_formula.translate import translate  # noqa: E402

with open(sys.argv[1], encoding="utf-8") as fh:
    source = fh.read().strip()
sys.stdout.write(translate(source + "C").decode("utf-8"))
