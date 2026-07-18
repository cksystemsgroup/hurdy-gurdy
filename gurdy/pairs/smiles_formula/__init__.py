"""The ``smiles-formula`` pair (thin slice) — SMILES -> molecular formula.

A **compile pair** (ARCHITECTURE.md §5), not a reasoning pair: the target is a
representation no solver consumes, so it carries no solver, no witness checker,
and no ``proved`` tier — only a faithful, deterministic re-representation. It is
the platform's field-blindness witness: the same pair machinery and commuting-
square contract carry an entirely non-computational translation unchanged.

It reuses the shared SMILES interpreter (source ``I_s``), the shared
molecular-formula interpreter (target ``I_t``), the framework's commuting-square
oracle, and the coverage harness — contributing only the translator ``T``, the
target-to-source interpreter ``L``, and the projection ``π`` (the atom
multiset; connectivity is discarded, an explicit honest loss).

``square()`` runs the commuting check ``I_s(p) ≡_π L(I_t(T(p)))`` through the
framework oracle — no solver step needed.
"""

from __future__ import annotations


from ...core import oracle, registry
from ...core.registry import Pair, Status
from ...core.types import AlignResult, Projection

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import molecular_formula as _formula  # noqa: F401
from ...languages import smiles as _smiles  # noqa: F401
from .inventory import ALL_PROBES
from .lift import lift
from .translate import translate

# π: the atom multiset and the Hill string that denotes it. Connectivity (bonds,
# rings, stereo) is *not* in π — discarded by construction (an honest loss,
# pairs/smiles-formula brief; ROUTES.md §3).
PROJECTION = Projection(("atoms", "formula"))

registry.register_pair(
    Pair(
        id="smiles-formula",
        source="smiles",
        target="molecular-formula",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="predicted",
        # 0.6: widened to bracket atoms ``[...]`` (any element, explicit H, no
        # implicit hydrogen or valence check; isotope/charge/chirality/class do
        # not change the atom multiset) — tracking the smiles interpreter's 0.6
        # bump. 0.5 had widened to ring-closure bonds; 0.4 to double/triple/
        # explicit-single bonds; 0.3 to branches ``(...)``; 0.2 from carbon-only
        # to the full organic subset. A version bump invalidates the
        # content-addressed cache.
        translator_version="0.6",
        status=Status.PARTIAL,
        probes=ALL_PROBES,
    )
)

__all__ = ["translate", "lift", "square", "PROJECTION"]


def square(smiles: str) -> AlignResult:
    """Check the commuting square for a SMILES string (no solver needed):

        I_s(smiles)  ≡_π  L( I_t( T(smiles) ) )

    Run the SMILES interpreter directly (left), and translate -> interpret the
    formula -> carry back (right), then align under ``π`` via the framework
    oracle. A divergence is localized to a (step, observable).
    """
    pair = registry.get_pair("smiles-formula")
    left = pair.source_interpreter(smiles)            # I_s(p)
    artifact = translate(smiles)                       # T(p)  -> formula bytes
    target_trace = pair.target_interpreter(artifact.decode("utf-8"))  # I_t(T(p))
    right = lift(target_trace)                          # L(I_t(T(p)))
    return oracle.align(left, right, pair.projection)


# Wire the square oracle onto the registered pair (Definition 4.6 conjunction).
registry.attach_square("smiles-formula", square)
