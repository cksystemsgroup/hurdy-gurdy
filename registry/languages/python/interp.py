"""Python-subset shared interpreter — carried over from v3
(KERNEL.md §7). A thin CLI shim over ``gurdy.languages.python``: the
straight-line integer subset executed through CPython itself (each
RHS compiled and eval'd in a restricted namespace), ending in one
``assert``. Programs are the subset source text; input
``{"params": {name: int}}``. Observable: ``violated`` — did the
final assert fail on this run.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.python.eval import interpret          # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        source = fh.read()
    with open(sys.argv[2], encoding="utf-8") as fh:
        inp = json.load(fh)
    trace = interpret(source, {k: int(v)
                               for k, v in inp.get("params", {}).items()})
    row = trace[-1] if trace else {}
    print(json.dumps({"violated": bool(row.get("__violated__"))},
                     sort_keys=True))


if __name__ == "__main__":
    main()
