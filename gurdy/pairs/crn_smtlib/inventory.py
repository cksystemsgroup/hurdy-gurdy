"""Construct-coverage inventory for crn-smtlib (BENCHMARKS.md §2, §5).

The denominator is CRN's spec-enumerable construct set — the reaction *classes*
of the discrete (Petri-net) semantics, the inventory the agent does **not**
choose (``languages/crn`` brief). A construct is *covered* iff a minimal network
exercising it bridges to SMT-LIB without an ``Unsupported`` abort.

This is the **minimal vertical slice** (PAIRING.md §1): exactly one construct —
the unimolecular reaction ``A -> B`` — is covered; every other reaction class
hard-aborts ``unsupported: crn:<construct>`` and is itemized in the histogram.
The honest result is ``partial`` (1/N), not a false ``built``.
"""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from .translate import translate

_TARGET = {"B": 1}  # a trivial reachability target so every probe is translatable past parsing


def _probe(*lines: str, target: dict | None = None) -> dict:
    return {"crn": "\n".join(lines) + "\n", "k": 1, "target": target or _TARGET}


ALL_PROBES: dict[str, dict] = {
    # IN SCOPE — the one covered construct: a single unimolecular reaction A -> B.
    "unimolecular": _probe("species A B", "init A 1 B 0", "rxn A -> B"),
    # OUT OF SCOPE — each hard-aborts a distinct typed unsupported construct.
    "bimolecular-hetero": _probe(  # A + B -> C
        "species A B C", "init A 1 B 1 C 0", "rxn A + B -> C", target={"C": 1}),
    "bimolecular-homo": _probe(    # 2 A -> B (dimerization)
        "species A B", "init A 2 B 0", "rxn 2 A -> B"),
    "catalysis": _probe(           # A -> 2 B (non-unit product / amplification)
        "species A B", "init A 1 B 0", "rxn A -> 2 B"),
    "catalyst-pair": _probe(       # A -> B + C (two products)
        "species A B C", "init A 1 B 0 C 0", "rxn A -> B + C"),
    "synthesis": _probe(           # 0 -> A (no reactant)
        "species A B", "init A 0 B 0", "rxn 0 -> A", target={"A": 1}),
    "degradation": _probe(         # A -> 0 (no product)
        "species A B", "init A 1 B 0", "rxn A -> 0", target={"A": 0}),
    "self-loop": _probe(           # A -> A (reactant == product)
        "species A B", "init A 1 B 0", "rxn A -> A", target={"A": 1}),
    "multiple-reactions": _probe(  # two reactions
        "species A B C", "init A 1 B 0 C 0", "rxn A -> B", "rxn B -> C", target={"C": 1}),
    "empty-network": _probe(       # no reactions at all
        "species A B", "init A 1 B 0"),
}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
