"""The v3 bridge as one engine — carried over as a solver pair
(KERNEL.md §7): unroll the BTOR2 system to the asked bound through
``gurdy/pairs/btor2_smtlib/translate.py`` (the operator mapping the
native-vs-bridged cross-check exercised all campaign), decide the
script with z3, and decode a ``sat`` model back into a BTOR2 input
binding (``gurdy/pairs/btor2_smtlib/lift.py``) that the kernel replays
through the shared interpreter.

The point of this pair is its lineage: **z3 alone** — no member of the
boolector family btormc and pono's stacks descend from — so its
agreement with theirs is what the corroborated flag means. Bounded
only: an ``inf`` ask is answered to the declared cap ``k = 20`` and
lands as a level-1 result; this engine cannot close an ``inf`` ask,
and says so.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.pairs.btor2_smtlib.lift import decode_witness  # noqa: E402
from gurdy.pairs.btor2_smtlib.translate import (          # noqa: E402
    _as_system, translate)
from gurdy.solvers.z3_smt import _model_value             # noqa: E402

INF_CAP_K = 20


def emit(obj) -> None:
    print(json.dumps(obj, sort_keys=True))
    sys.exit(0)


def partial(note: str, **progress) -> None:
    emit({"kind": "partial", "progress": {"note": note, **progress}})


def main() -> None:
    program_path, _mode, _observable, bound, wall_s = sys.argv[1:6]
    k = INF_CAP_K if bound == "inf" else min(int(bound), 10**6)
    wall = float(wall_s)
    try:
        import z3
    except ImportError:
        partial("z3 python module not available")
    with open(program_path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        script = translate({"system": text, "k": k})
    except Exception as exc:                       # fail-safe, recorded
        partial(f"bridge translation failed: {exc}")
    solver = z3.Solver()
    solver.set("timeout", max(1000, int(wall * 1000) - 2000))
    solver.from_string(script.decode("utf-8"))
    verdict = solver.check()
    if verdict == z3.sat:
        z3_model = solver.model()
        model = {decl.name(): _model_value(z3, z3_model[decl])
                 for decl in z3_model.decls()}
        binding = decode_witness(_as_system(text), k, model)
        emit({"kind": "witness", "payload": binding})
    if verdict == z3.unsat:
        emit({"kind": "all", "bound": k})
    partial("z3 answered unknown", k=k, wall_s=wall)


if __name__ == "__main__":
    main()
