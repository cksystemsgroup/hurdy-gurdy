"""z3 as the SMT-LIB solver pair — carried over from v3
(KERNEL.md §7): the language's gated searcher, where the language
entry itself only ever checks one model. ``sat`` yields the model as
a witness payload — the kernel replays it through the shared
evaluator — and ``unsat`` yields ``all(inf)``: for a *script*, "no
model exists" is a complete fact. What that fact means for a question
that crossed a bound-eating hop is the route's business: the hop's
declared ``bound_cap`` caps the claim on the way back (the routing
contract, settled 2026-08-07).
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.solvers.z3_smt import _model_value              # noqa: E402


def emit(obj) -> None:
    print(json.dumps(obj, sort_keys=True))
    sys.exit(0)


def partial(note: str, **progress) -> None:
    emit({"kind": "partial", "progress": {"note": note, **progress}})


def main() -> None:
    program_path, _mode, _observable, _bound, wall_s = sys.argv[1:6]
    wall = float(wall_s)
    try:
        import z3
    except ImportError:
        partial("z3 python module not available")
    with open(program_path, encoding="utf-8") as fh:
        script = fh.read()
    solver = z3.Solver()
    solver.set("timeout", max(1000, int(wall * 1000) - 2000))
    solver.from_string(script)
    verdict = solver.check()
    if verdict == z3.sat:
        z3_model = solver.model()
        model = {decl.name(): _model_value(z3, z3_model[decl])
                 for decl in z3_model.decls()}
        emit({"kind": "witness", "payload": {"model": model}})
    if verdict == z3.unsat:
        emit({"kind": "all", "bound": "inf"})
    partial("z3 answered unknown", wall_s=wall)


if __name__ == "__main__":
    main()
