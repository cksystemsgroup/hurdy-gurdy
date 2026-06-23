"""Construct-coverage inventory for crn-smtlib (BENCHMARKS.md §2, §5).

The denominator is CRN's spec-enumerable construct set — the reaction *classes*
of the discrete (Petri-net) semantics, the inventory the agent does **not**
choose (``languages/crn`` brief). A construct is *covered* iff a minimal network
exercising it bridges to SMT-LIB without an ``Unsupported`` abort.

This is a widened vertical slice (PAIRING.md §1 "start thin, then widen"): the
**unimolecular** reaction ``A -> B``, both **bimolecular** shapes
(``A + B -> C`` and ``2 A -> B``), both **catalysis / multi-product** shapes
(``A -> 2 B`` and ``A -> B + C``), and now **synthesis** (``0 -> A``) and
**degradation** (``A -> 0``) are covered — 7/10 probes; every other reaction
class still hard-aborts ``unsupported: crn:<construct>`` and is itemized in the
histogram. The honest result is ``partial`` (7/10), not a false ``built``. The
coverage ratchet (BENCHMARKS.md §5) only grows: nothing covered before is
dropped.
"""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from .translate import translate

_TARGET = {"B": 1}  # a trivial reachability target so every probe is translatable past parsing


def _probe(*lines: str, target: dict | None = None) -> dict:
    return {"crn": "\n".join(lines) + "\n", "k": 1, "target": target or _TARGET}


ALL_PROBES: dict[str, dict] = {
    # IN SCOPE — covered constructs.
    # Unimolecular: a single reaction A -> B.
    "unimolecular": _probe("species A B", "init A 1 B 0", "rxn A -> B"),
    # Bimolecular (hetero): A + B -> C — two distinct unit reactants.
    "bimolecular-hetero": _probe(
        "species A B C", "init A 1 B 1 C 0", "rxn A + B -> C", target={"C": 1}),
    # Bimolecular (homo): 2 A -> B — one doubled reactant (dimerization).
    "bimolecular-homo": _probe(
        "species A B", "init A 2 B 0", "rxn 2 A -> B"),
    # Catalysis / amplification: A -> 2 B — one unit reactant, one doubled product.
    "catalysis": _probe(
        "species A B", "init A 1 B 0", "rxn A -> 2 B", target={"B": 2}),
    # Multi-product: A -> B + C — one unit reactant, two distinct unit products.
    "catalyst-pair": _probe(
        "species A B C", "init A 1 B 0 C 0", "rxn A -> B + C", target={"B": 1, "C": 1}),
    # Synthesis: 0 -> A — an empty reactant side (always enabled), net A: +1.
    "synthesis": _probe(           # 0 -> A (no reactant)
        "species A B", "init A 0 B 0", "rxn 0 -> A", target={"A": 1}),
    # Degradation: A -> 0 — an empty product side, net A: -1.
    "degradation": _probe(         # A -> 0 (no product)
        "species A B", "init A 1 B 0", "rxn A -> 0", target={"A": 0}),
    # OUT OF SCOPE — each hard-aborts a distinct typed unsupported construct.
    "self-loop": _probe(           # A -> A (reactant == product)
        "species A B", "init A 1 B 0", "rxn A -> A", target={"A": 1}),
    "multiple-reactions": _probe(  # two reactions
        "species A B C", "init A 1 B 0 C 0", "rxn A -> B", "rxn B -> C", target={"C": 1}),
    "empty-network": _probe(       # no reactions at all
        "species A B", "init A 1 B 0"),
}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
