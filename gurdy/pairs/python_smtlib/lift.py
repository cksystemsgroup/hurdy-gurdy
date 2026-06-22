"""Target-to-source interpreter ``L`` for python-smtlib: decode a ``sat`` SMT
model — the satisfying **input assignment** — and **re-run it through CPython**
to exhibit the property (the assert that fires) at the source level
(pairs/python-smtlib brief; ARCHITECTURE.md §5).

The solver only *proposes* the violating input (SOLVERS.md §4); the
deterministic source interpreter ``I_s`` (pinned CPython) then **regrows** the
whole run, so the behavior ``L`` returns is the interpreter's, not the solver's.
``decode_inputs`` reads each parameter's ``<p>__in`` binding from the model
(matching ``translate``'s symbol names); ``lift`` feeds that binding to the
shared Python executor and returns the post-step trace, whose final state
carries ``__violated__ = True`` for a genuine counterexample.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from ...languages.python.eval import run
from ...languages.python.subset import Program, load


def _as_int(val: Any) -> int:
    """A model entry for an ``Int``: the z3 backend stringifies it to a decimal
    (possibly negative); accept int / str shapes, default an omitted
    don't-care input to 0."""
    if isinstance(val, bool):  # guard: bool is an int subclass
        return int(val)
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        return int(val.strip())
    return 0


def decode_inputs(prog: Program, model: dict[str, Any]) -> dict[str, int]:
    """The satisfying input assignment ``{param: int}`` read out of the model's
    ``<p>__in`` bindings (declaration order; a parameter the solver left as a
    don't-care defaults to 0)."""
    return {p: _as_int(model.get(f"{p}__in")) for p in prog.params}


def lift(witness: dict[str, Any]) -> Trace:
    """``witness`` bundles the source ``python`` program and the SMT ``model``;
    returns the CPython-replayed trace for the decoded violating input."""
    prog: Program = load(witness["python"])
    binding = decode_inputs(prog, witness.get("model") or {})
    return run(prog, binding)
