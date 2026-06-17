"""The z3 ``SolverBackend`` adapter (SOLVERS.md §3; the MVP-1 solver).

A thin wrapper: parse an SMT-LIB artifact, check satisfiability, and normalize
the outcome into a framework ``Result``. On ``sat`` it returns the model as an
observable->value binding (integers where the value is a bit-vector/int
numeral). z3 is pinned to the dev-image version (DOCKER.md).
"""

from __future__ import annotations

from typing import Any

from ..core.solver import Result, Verdict


def _model_value(z3, value: Any) -> Any:
    """Normalize a z3 model value: a bit-vector becomes an int; an array becomes
    its explicit ``{index: value}`` entries (walking the ``store`` chain) so an
    array-valued initial state can be replayed; otherwise its string form."""
    try:
        return value.as_long()
    except (AttributeError, z3.Z3Exception):
        pass
    try:
        if value.sort_kind() == z3.Z3_ARRAY_SORT:
            entries: dict[Any, int] = {}
            cur = value
            while z3.is_app(cur) and cur.decl().kind() == z3.Z3_OP_STORE:
                idx, val = cur.arg(1), cur.arg(2)
                try:
                    entries.setdefault(idx.as_long(), val.as_long())
                except (AttributeError, z3.Z3Exception):
                    pass
                cur = cur.arg(0)
            if z3.is_app(cur) and cur.decl().kind() == z3.Z3_OP_CONST_ARRAY:
                try:
                    entries["default"] = cur.arg(0).as_long()
                except (AttributeError, z3.Z3Exception):
                    pass
            return entries
    except (AttributeError, z3.Z3Exception):
        pass
    return str(value)


class Z3SmtBackend:
    id = "z3"

    def __init__(self) -> None:
        try:
            import z3  # noqa: F401
        except ImportError as exc:  # pragma: no cover - env guard
            raise RuntimeError(
                "z3 not available; install the 'solvers' extra "
                "(z3-solver) or use the dev image (DOCKER.md)"
            ) from exc

    def decide(self, artifact: bytes, directive: dict[str, Any] | None = None) -> Result:
        import z3

        solver = z3.Solver()
        if directive and "timeout_ms" in directive:
            solver.set("timeout", int(directive["timeout_ms"]))
        solver.from_string(artifact.decode("utf-8"))
        prov: dict[str, Any] = {
            "solver": self.id,
            "version": z3.get_version_string(),
            "directive": dict(directive or {}),
        }
        result = solver.check()
        if result == z3.sat:
            z3_model = solver.model()
            model: dict[str, Any] = {}
            for decl in z3_model.decls():
                model[decl.name()] = _model_value(z3, z3_model[decl])
            return Result(Verdict.REACHABLE, model=model, provenance=prov)
        if result == z3.unsat:
            return Result(Verdict.UNREACHABLE, provenance=prov)
        return Result(Verdict.UNKNOWN, provenance=prov)
