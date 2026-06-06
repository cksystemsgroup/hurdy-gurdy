"""``btor2-smtlib``: the BTOR2 <-> SMT-LIB bridge.

A *transparent* translation between two **reasoning** languages: it symbolically
unrolls a BTOR2 transition system to a bound and emits SMT-LIB (QF_BV / QF_ABV)
that z3 decides — ``sat`` iff a ``bad`` is reachable within the bound. Every
BTOR2 operator maps to the standard SMT bit-vector / array operator a native
BTOR2 solver also uses, so the bridged verdict *agrees* with the native one.

Significance — this single edge is what the two-hub design was for
(``DESIGN_generalized_pairs.md`` §7): it connects everything bitvector-shaped
(``c -> rv64-elf -> btor2``) to the SMT-LIB hub, so

- ``routes("rv64-elf", "smtlib")`` now exists (``riscv-btor2`` then this bridge)
  — ``routes()`` finally has multi-hop paths to a reasoning language;
- the *same* BTOR2 question can be decided two ways — native (``z3-bmc`` on
  BTOR2) vs bridged (``z3`` on the SMT encoding) — a "many chains, one question"
  cross-check that detects translator bugs (``DESIGN_generalized_pairs.md`` §6).

Importing this module registers the pair. The ``btor2`` and ``smtlib`` languages
are owned by ``riscv-btor2`` and ``crn-smtlib`` respectively; the bridge reuses
the shared ``z3-smt`` SMT-LIB backend.
"""

from pathlib import Path

from gurdy.core.pair import LayerSpec, Pair, Preservation, Tier, register_pair
from gurdy.pairs.btor2_smtlib.backend import Btor2SmtLifter, Z3SmtSolver
from gurdy.pairs.btor2_smtlib.spec import PAIR_ID, Btor2SmtSpec, validate_btor2_smt_spec
from gurdy.pairs.btor2_smtlib.translate import (
    SCHEMA_VERSION,
    parse_btor2,
    translate as _translate,
)

PAIR = Pair(
    identifier=PAIR_ID,
    in_lang="btor2",
    out_lang="smtlib",
    tier=Tier.transparent,
    preservation=Preservation(
        keeps=("transition-relation", "bad-states", "bit-vector-semantics", "array-memory"),
        discards=("behaviour-beyond-bound",),
        note=(
            "faithful BTOR2 -> SMT bit-vector / array unrolling; preserves the "
            "transition relation and bad states, but only up to the BMC bound "
            "(deeper counterexamples are out of scope -- bounded model checking)."
        ),
    ),
    schema_version=SCHEMA_VERSION,
    source_loader=parse_btor2,
    spec_class=Btor2SmtSpec,
    spec_validator=validate_btor2_smt_spec,
    layer_specs=(
        LayerSpec(
            name="smtlib",
            stability="per-question",
            description="QF_(A)BV bounded-model-checking unrolling",
        ),
    ),
    translator=_translate,
    lifter=Btor2SmtLifter(),
    solvers={"z3-smt": Z3SmtSolver},
    schema_path=Path(__file__).parent / "SCHEMA.md",
)

register_pair(PAIR)


__all__ = ["PAIR", "PAIR_ID"]
