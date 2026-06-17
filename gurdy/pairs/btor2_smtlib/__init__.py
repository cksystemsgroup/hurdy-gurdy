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
from .inventory import ALL_PROBES
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
        # Construct-coverage inventory: BTOR2's operator/sort/directive set.
        probes=ALL_PROBES,
    )
)

__all__ = ["translate", "lift", "decode_witness", "reach", "native_vs_bridged"]


def native_vs_bridged(system: Any, k: int) -> dict[str, Any]:
    """The native-vs-bridged cross-check (SOLVERS.md §7): decide the same BTOR2
    reachability question with the native checker (pono/btormc) and with the
    SMT bridge (z3), and confirm the verdicts agree. Raises ``NativeUnavailable``
    if the native checker is absent (gated on the dev image)."""
    from ...solvers.native_btor2 import NativeBtor2Checker

    native = NativeBtor2Checker().decide(system, k)
    bridged = reach(system, k)["verdict"]
    return {"native": native, "bridged": bridged, "agree": native == bridged}


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
        # Independent SMT-level witness check: confirm the solver's model
        # actually satisfies the emitted script via the shared SMT-LIB
        # evaluator, *before* the BTOR2 replay believes it (SOLVERS.md §4-5).
        # Best-effort: an unusual model shape leaves it unchecked (``None``),
        # never breaking the authoritative BTOR2 replay below.
        from ...core.errors import Unsupported
        from ...languages.smtlib.eval import evaluate as smt_evaluate

        try:
            info["smt_model_ok"] = smt_evaluate(artifact, result.model)
        except (Unsupported, KeyError, ValueError, AttributeError):
            info["smt_model_ok"] = None
        sys = system if hasattr(system, "states") else from_text(
            system.decode("utf-8") if isinstance(system, (bytes, bytearray)) else str(system)
        )
        behavior = lift({"system": sys, "k": k, "model": result.model})
        info["behavior"] = behavior
        info["witness_ok"] = any(
            v == 1 for row in behavior for key, v in row.items() if key.startswith("bad")
        )
    return info
