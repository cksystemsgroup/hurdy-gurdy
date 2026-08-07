"""Λ for python--smtlib witnesses: the
model's satisfying input assignment, re-run through CPython. The
kernel passes the hop's source program (argv[2]); ``decode_inputs``
reads each parameter's ``<p>__in`` binding from the model.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.python.subset import load             # noqa: E402
from gurdy.pairs.python_smtlib.lift import decode_inputs   # noqa: E402

with open(sys.argv[1], encoding="utf-8") as fh:
    inp = json.load(fh)
with open(sys.argv[2], encoding="utf-8") as fh:
    source = fh.read()
params = decode_inputs(load(source), inp.get("model", {}))
print(json.dumps({"params": params}, sort_keys=True))
