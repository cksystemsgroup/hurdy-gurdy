"""The enumerative reference procedure as a solver pair — carried
over from v3 (KERNEL.md §7): exhaust every complete per-cycle input
assignment within the bound through the shared BTOR2 interpreter.
Deliberately naive; its value is its TCB — the shared interpreter is
the semantics, so deciding and replaying coincide, and its lineage
(the platform's own interpreter, no external engine) corroborates
with every adapter. Sound and complete within the declared path
budget; beyond it, a partial that says so.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.core.solver import Verdict                      # noqa: E402
from gurdy.solvers.enum_btor2 import EnumBtor2Solver       # noqa: E402

INF_CAP_K = 20
MAX_PATHS = 4096


def emit(obj) -> None:
    print(json.dumps(obj, sort_keys=True))
    sys.exit(0)


def main() -> None:
    program_path, _mode, _observable, bound, _wall_s = sys.argv[1:6]
    k = INF_CAP_K if bound == "inf" else min(int(bound), 10**6)
    with open(program_path, encoding="utf-8") as fh:
        text = fh.read()
    verdict, assignment = EnumBtor2Solver(
        max_paths=MAX_PATHS).decide_witness(text, k)
    if verdict is Verdict.REACHABLE:
        emit({"kind": "witness",
              "payload": {"steps": k + 1, "inputs": assignment or {}}})
    if verdict is Verdict.UNREACHABLE:
        emit({"kind": "all", "bound": k})
    emit({"kind": "partial",
          "progress": {"note": "path budget exhausted",
                       "max_paths": MAX_PATHS, "k": k}})


if __name__ == "__main__":
    main()
