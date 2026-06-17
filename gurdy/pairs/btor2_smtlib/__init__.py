"""The ``btor2-smtlib`` pair — a reasoning-to-reasoning bridge (BTOR2 ->
SMT-LIB) so a BTOR2 reachability question can be decided through an SMT
solver.

Registers the pair (reusing the shared BTOR2 interpreter as source; SMT-LIB
as target) and provides ``reach()``: translate to SMT, decide with z3, and on
``sat`` replay the witness through the BTOR2 interpreter to confirm a ``bad``
is actually reached within ``k`` (the witness verification of SOLVERS.md
§4-5). Soundness is byte-prediction + native-vs-bridged agreement + this
witness check, not a trace align, so the projection is empty.
"""

from __future__ import annotations

from typing import Any

from ...core import registry
from ...core.registry import Pair, Status
from ...core.solver import Verdict
from ...core.types import Projection

# Importing the languages registers what the pair reuses.
from ...languages import btor2 as _btor2  # noqa: F401
from ...languages import smtlib as _smtlib  # noqa: F401
from .lift import decode_witness, lift
from .translate import translate

registry.register_pair(
    Pair(
        id="btor2-smtlib",
        source="btor2",
        target="smtlib",
        translator=translate,
        target_to_source=lift,
        projection=Projection(()),
        fidelity="predicted",
        translator_version="0.1",
        status=Status.PARTIAL,
        # Path-runner glue: wrap a predecessor's BTOR2 output + the bound k.
        compose_input=lambda prev, params: {"system": prev, "k": int(params["k"])},
    )
)

__all__ = ["translate", "lift", "decode_witness", "reach"]


def reach(system: Any, k: int) -> dict[str, Any]:
    """Decide "is a bad reachable within k steps?" for a BTOR2 ``system``.

    Returns a dict with the ``verdict``; on ``reachable`` also the decoded
    witness ``behavior`` and ``witness_ok`` (does replay actually hit a bad?).
    """
    from ...languages.btor2.model import from_text
    from ...solvers.z3_smt import Z3SmtBackend

    artifact = translate({"system": system, "k": k})
    result = Z3SmtBackend().decide(artifact)
    info: dict[str, Any] = {"verdict": result.verdict, "model": result.model}
    if result.verdict is Verdict.REACHABLE:
        sys = system if hasattr(system, "states") else from_text(
            system.decode("utf-8") if isinstance(system, (bytes, bytearray)) else str(system)
        )
        behavior = lift({"system": sys, "k": k, "model": result.model})
        info["behavior"] = behavior
        info["witness_ok"] = any(
            v == 1 for row in behavior for key, v in row.items() if key.startswith("bad")
        )
    return info
