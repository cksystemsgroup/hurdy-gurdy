"""``crn-smtlib``: chemical reaction network -> SMT-LIB bounded reachability.

The project's **second reasoning pair** and second reasoning hub (SMT-LIB),
after ``riscv-btor2`` (BTOR2). It is a *transparent* reasoning pair: a CRN under
discrete population (Petri-net) semantics, plus a bounded reachability question,
compiled by a schema-predictable rule to SMT-LIB (QF_LIA) and decided by z3.

Significance:

- A **non-program, non-CS input language reaching a real solver** — completing
  the field-blindness arc that ``smiles-formula`` (Stage 6) opened: there a
  chemistry input reached only a *representation* (a formula); here a chemistry
  question is actually *decided*.
- It validates that the ``Pair`` protocol (PAIRING.md "irreducible six")
  generalizes to a genuinely different reasoning language, and adds the SMT-LIB
  hub the future ``BTOR2 <-> SMT-LIB`` bridge would connect to.

Importing this module registers the pair and the ``crn`` / ``smtlib`` languages.
It is a reasoning pair without interpreters (``interpreter_version`` empty), so
it exposes the translator-layer tools (describe/compile/dispatch/lift) and not
the interpreter-layer ones (simulate/cross_check/replay/check).
"""

from pathlib import Path

from gurdy.core.language import Language, register_language
from gurdy.core.pair import LayerSpec, Pair, Preservation, Tier, register_pair
from gurdy.pairs.crn_smtlib.backend import CrnLifter, Z3SmtSolver
from gurdy.pairs.crn_smtlib.model import parse_crn
from gurdy.pairs.crn_smtlib.spec import PAIR_ID, CrnSpec, validate_crn_spec
from gurdy.pairs.crn_smtlib.translate import SCHEMA_VERSION, translate as _translate

PAIR = Pair(
    identifier=PAIR_ID,
    in_lang="crn",
    out_lang="smtlib",
    tier=Tier.transparent,
    preservation=Preservation(
        keeps=("species-counts", "reaction-stoichiometry", "reachability"),
        discards=("reaction-rates", "kinetics", "continuous-dynamics", "real-time"),
        note=(
            "discrete population (Petri-net) reachability encoding: keeps integer "
            "counts and stoichiometry, discards rates / kinetics / continuous time."
        ),
    ),
    schema_version=SCHEMA_VERSION,
    source_loader=parse_crn,
    spec_class=CrnSpec,
    spec_validator=validate_crn_spec,
    layer_specs=(
        LayerSpec(
            name="smtlib",
            stability="per-question",
            description="QF_LIA bounded-reachability encoding",
        ),
    ),
    translator=_translate,
    lifter=CrnLifter(),
    solvers={"z3-smt": Z3SmtSolver},
    schema_path=Path(__file__).parent / "SCHEMA.md",
)

register_pair(PAIR)

CRN_LANG = Language(
    id="crn",
    kind="input",
    semantics="chemical reaction network; discrete population (Petri-net) semantics",
)
SMTLIB_LANG = Language(
    id="smtlib",
    kind="reasoning",
    semantics="SMT-LIB (QF_LIA bounded reachability)",
    reasons_via=("z3-smt",),
)
register_language(CRN_LANG)
register_language(SMTLIB_LANG)


__all__ = ["PAIR", "PAIR_ID", "CRN_LANG", "SMTLIB_LANG"]
