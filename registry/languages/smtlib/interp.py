"""SMT-LIB shared interpreter — carried over from v3 (KERNEL.md §7).

A thin CLI shim over ``gurdy.languages.smtlib``: the deterministic
model evaluator (``eval.py``) that is the language's own executor —
it runs *one* model through a script and reports whether it satisfies
it. The solver that searches over all models is a separate, gated
artifact (a solver pair); the language itself only ever checks.
Input: ``{"model": {name: value}}``. Observable: ``sat``.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.smtlib.interp import interpret    # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        script = fh.read()
    with open(sys.argv[2], encoding="utf-8") as fh:
        inp = json.load(fh)
    trace = interpret(script, {"model": inp.get("model", {})})
    print(json.dumps({"sat": bool(trace[0]["sat"])}, sort_keys=True))


if __name__ == "__main__":
    main()
