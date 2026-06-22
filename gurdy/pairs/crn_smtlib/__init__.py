"""The ``crn-smtlib`` pair — a non-CS reasoning bridge (CRN -> SMT-LIB) so a
chemical-reaction-network reachability question can be decided through an SMT
solver. The evidence the architecture is field-blind: the source is chemistry,
not code (pairs/crn-smtlib brief; ARCHITECTURE.md §1).

**Status: partial — minimal vertical slice (PAIRING.md §1).** Exactly one
in-scope reaction class — the unimolecular reaction ``A -> B`` — is translated
end-to-end through the commuting square; every other CRN construct hard-aborts
``unsupported: crn:<construct>`` (BENCHMARKS.md §3).

Registers the pair (reusing the shared CRN interpreter as source ``I_s`` and the
shared SMT-LIB evaluator as target ``I_t``) and provides ``reach()``: translate
to ``QF_LIA``, decide with z3, and on ``sat`` replay the firing-flag witness
through the CRN interpreter to confirm the target marking is actually reached
within ``k`` (the witness verification of SOLVERS.md §4-5).

Soundness story (pairs/crn-smtlib brief; PAIRING.md §6): byte-prediction
(``predicted`` fidelity) + model validation — a ``sat`` model is replayed
through the CRN interpreter under ``π`` to confirm it reaches the target.
"""

from __future__ import annotations

from typing import Any

from ...core import registry
from ...core.oracle import align
from ...core.registry import Pair, Status
from ...core.solver import Verdict
from ...core.types import Projection

# Importing the languages registers what the pair reuses.
from ...languages import crn as _crn  # noqa: F401
from ...languages import smtlib as _smtlib  # noqa: F401
from ...languages.crn.eval import step as crn_step
from ...languages.crn.model import as_network
from .inventory import ALL_PROBES
from .lift import decode_schedule, lift
from .translate import translate

registry.register_pair(
    Pair(
        id="crn-smtlib",
        source="crn",
        target="smtlib",
        translator=translate,
        target_to_source=lift,
        # Per-network species are the observables; the cross-check builds the
        # concrete projection from the network (see ``projection_for``). The
        # registered projection is empty because the soundness story is
        # byte-prediction + witness replay, like btor2-smtlib.
        projection=Projection(()),
        fidelity="predicted",
        translator_version="0.1",
        status=Status.PARTIAL,
        # Path-runner glue: wrap a predecessor's CRN output + the bound/target.
        compose_input=lambda prev, params: {
            "crn": prev,
            "k": int(params["k"]),
            "target": params["target"],
        },
        # Construct-coverage inventory: CRN's reaction-class set.
        probes=ALL_PROBES,
    )
)

__all__ = [
    "translate",
    "lift",
    "decode_schedule",
    "reach",
    "projection_for",
    "cross_check",
]


def projection_for(crn: Any) -> Projection:
    """The projection ``π`` for a given network: its species populations per
    step, in network declaration order (ARCHITECTURE.md §3)."""
    return Projection(tuple(as_network(crn).species))


def reach(crn: Any, k: int, target: dict[str, int]) -> dict[str, Any]:
    """Decide "is the ``target`` marking reachable within ``k`` steps?" for a
    CRN.

    Returns a dict with the ``verdict``; on ``reachable`` also the decoded
    ``behavior`` (the per-step populations from the CRN interpreter replay),
    the firing ``schedule``, ``witness_ok`` (does the replay actually reach the
    target marking?), and ``model_matches_replay`` (do the solver's proposed
    per-step populations agree with the deterministic interpreter replay — the
    check that the QF_LIA arithmetic faithfully encodes the Petri-net step).

    Note on the SMT-level check: the shared SMT-LIB evaluator is the ``QF_ABV``
    fragment (``languages/smtlib``), so it cannot evaluate this pair's
    ``QF_LIA`` script — extending it is a versioned shared-interpreter change
    out of this pair's scope (AGENTS.md §3). The authoritative witness check is
    therefore the CRN-interpreter replay (``witness_ok`` /
    ``model_matches_replay``), which *is* the commuting square's replay-and-
    project check (SOLVERS.md §4); ``smt_model_ok`` stays best-effort (``None``
    when the shared evaluator declines the fragment).
    """
    from ...languages.smtlib.eval import evaluate as smt_evaluate
    from ...solvers.z3_smt import Z3SmtBackend

    net = as_network(crn)
    artifact = translate({"crn": crn, "k": k, "target": target})
    result = Z3SmtBackend().decide(artifact)
    info: dict[str, Any] = {"verdict": result.verdict, "model": result.model}
    if result.verdict is Verdict.REACHABLE:
        # Best-effort SMT-level check via the shared evaluator; the QF_LIA
        # fragment is outside its QF_ABV scope, so this is expected to decline.
        from ...core.errors import Unsupported

        try:
            info["smt_model_ok"] = smt_evaluate(artifact, result.model)
        except (Unsupported, KeyError, ValueError, AttributeError):
            info["smt_model_ok"] = None
        info["schedule"] = decode_schedule(k, result.model)
        behavior = lift({"crn": crn, "k": k, "model": result.model})
        info["behavior"] = behavior
        # The replay reaches the target iff some post-step marking matches it.
        info["witness_ok"] = any(
            all(row.get(s) == c for s, c in target.items()) for row in behavior
        )
        # The solver's claimed populations must match what the interpreter
        # regrows from the same firing schedule (catches an arithmetic-vs-
        # semantics divergence in the schema). A population the solver left as a
        # don't-care (absent from the model) is skipped.
        model = result.model or {}
        info["model_matches_replay"] = all(
            int(model[f"x{s}_{t + 1}"]) == row[s]
            for t, row in enumerate(behavior)
            for s in net.species
            if f"x{s}_{t + 1}" in model
        )
    return info


def cross_check(crn: Any, k: int, target: dict[str, int]):
    """The commuting-square check (PAIRING.md §7): run the source interpreter
    directly and compare it, under ``π``, with translate -> decide -> carry-back.

    Returns ``(verdict, AlignResult)``. The right-hand side
    ``L(I_t(T(p)))`` is the witness replay; the left-hand side ``I_s(p)`` re-runs
    the *same firing schedule* the witness proposed, so a faithful pair makes the
    two traces identical under ``π`` (the species populations per step). On an
    ``unreachable`` verdict there is no model to align, so the alignment is the
    trivially-true empty trace agreement.
    """
    info = reach(crn, k, target)
    pi = projection_for(crn)
    if info["verdict"] is not Verdict.REACHABLE:
        return info["verdict"], align([], [], pi)
    # I_s(p): the source interpreter on the witness's schedule (the inputs held
    # in correspondence — ARCHITECTURE.md §3).
    left = crn_step(as_network(crn), {"steps": k, "schedule": info["schedule"]})
    right = info["behavior"]
    return info["verdict"], align(left, right, pi)
