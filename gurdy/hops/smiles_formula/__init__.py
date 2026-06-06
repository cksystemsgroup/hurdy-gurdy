"""``smiles-formula``: SMILES (aliphatic organic subset) -> Hill molecular formula.

A **transparent compile pair** (``DESIGN_pair_taxonomy.md``) and the project's
field-blindness witness (``PAIRING.md`` §15): a non-CS, non-programming input
language — SMILES, a chemistry line notation whose formal semantics is a
molecular graph — translated by a schema-predictable, deterministic rule. It is
the second registered pair, so it is also the second data point that unlocks the
deferred ``preservation`` contract (this hop keeps the atom multiset and
discards connectivity; see ``SCHEMA.md`` §5).

Importing this module registers the hop and its two languages, so it appears as
the ``smiles -> molecular-formula`` edge of the language graph.
"""

from pathlib import Path

from gurdy.core.hop import CompileHop, Tier, register_hop
from gurdy.core.language import Language, register_language
from gurdy.hops.smiles_formula.compile import SmilesError, smiles_to_formula

SMILES_FORMULA = CompileHop(
    identifier="smiles-formula",
    in_lang="smiles",
    out_lang="molecular-formula",
    tier=Tier.transparent,
    compile=smiles_to_formula,
    contract_path=Path(__file__).parent / "SCHEMA.md",
)

# Language descriptors (exported so tests can re-register them idempotently
# after a registry-clearing test, mirroring how the route tests re-register
# the riscv-btor2 pair).
SMILES_LANG = Language(
    id="smiles",
    kind="input",
    semantics="SMILES line notation (aliphatic organic subset) -> molecular graph",
)
MOLECULAR_FORMULA_LANG = Language(
    id="molecular-formula",
    kind="representation",
    semantics="Hill-notation molecular formula (atom multiset)",
)

register_hop(SMILES_FORMULA)
register_language(SMILES_LANG)
register_language(MOLECULAR_FORMULA_LANG)


__all__ = [
    "SMILES_FORMULA",
    "SMILES_LANG",
    "MOLECULAR_FORMULA_LANG",
    "SmilesError",
    "smiles_to_formula",
]
