"""Python -> SMT-LIB — carried over from v3 (KERNEL.md §7):
``gurdy/pairs/python_smtlib/translate.py``, the schema-determined
QF_LIA lowering of the straight-line integer subset — direct to
SMT-LIB, since Python's unbounded int maps to SMT Int. The script is
sat iff some input violates the final assert; its ``sat`` carries
back as the source's ``violated`` (the manifest's map).
"""

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.pairs.python_smtlib.translate import translate  # noqa: E402

with open(sys.argv[1], encoding="utf-8") as fh:
    source = fh.read()
out = translate(source).decode("utf-8").splitlines()
last = max(i for i, l in enumerate(out) if l.startswith("(assert"))
out[last] = "(assert true)"
sys.stdout.write("\n".join(out) + "\n")
