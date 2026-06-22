"""The ``smiles-formula`` target-to-source interpreter ``L`` (PAIRING.md §1).

``L`` carries a *target* molecular-formula behavior back to the *source*-level
observable. The pair's projection ``π`` is the **atom multiset** (connectivity
is discarded — an explicit, honest loss, pairs/smiles-formula brief), so the
carry-back is the trivial re-projection: the formula's atom multiset *is* the
source-level observable the square checks. There is no solver witness here (a
compile pair), so ``L`` re-expresses the target trace's ``atoms``/``formula``
observables unchanged.

It is the pair's, not a language's: the correspondence ("the formula's multiset
denotes the molecule's atoms") is this pair's claim.
"""

from __future__ import annotations

from ...core.types import Trace


def lift(target_trace: Trace) -> Trace:
    """``L``: a molecular-formula behavior -> the source-level atom-multiset
    behavior. Re-projects onto ``π = {atoms, formula}`` (already the source
    observables for a compile pair)."""
    return [
        {"atoms": state["atoms"], "formula": state["formula"]}
        for state in target_trace
    ]
