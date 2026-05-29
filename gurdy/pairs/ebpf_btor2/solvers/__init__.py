"""ebpf-btor2 solver dispatch — P6.

``check(spec, bytecode)`` is the single entry point: translate → solve → result.
The BMC bound defaults to ``spec.scope.max_insns`` when not overridden by
``spec.analysis.bound``.
"""
from __future__ import annotations

import dataclasses

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.pairs.ebpf_btor2.spec import EbpfBtor2Spec
from gurdy.pairs.ebpf_btor2.translation import translate
from gurdy.pairs.ebpf_btor2.solvers.z3bmc import Z3BMCSolver


def check(spec: EbpfBtor2Spec, bytecode: bytes) -> RawSolverResult:
    """Translate *bytecode* under *spec* and run the z3-bmc engine.

    Returns a ``RawSolverResult`` with ``verdict`` in
    ``{reachable, unreachable, unknown, error}``.
    """
    artifact = translate(spec, bytecode)
    bound = spec.analysis.bound if spec.analysis.bound is not None else spec.scope.max_insns
    directive = dataclasses.replace(spec.analysis, bound=bound)
    return Z3BMCSolver().dispatch(artifact.flattened, directive)


__all__ = ["check", "Z3BMCSolver"]
