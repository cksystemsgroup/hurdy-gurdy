"""aarch64-btor2 pair: AArch64 (ARMv8-A base integer ISA) to BTOR2 translation.

Importing this module registers the pair with the framework's
``register_pair`` registry.

P4 state:
- SCHEMA.md frozen at 1.0.0.
- spec.py, source_interp: implemented.
- translation/: builder + library + layers + translate + exprs implemented.
- source_loader: uses load_aarch64_binary from P2.
- lift/: witness, invariant, replayer, lift implemented (P4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gurdy.core.pair import LayerSpec, Pair, register_pair
from gurdy.pairs.aarch64_btor2.reasoning_interp.interpreter import (
    Btor2ReasoningInterpreter,
)
from gurdy.pairs.aarch64_btor2.solvers.bitwuzla import BitwuzlaSolver
from gurdy.pairs.aarch64_btor2.solvers.cvc5 import Cvc5Solver
from gurdy.pairs.aarch64_btor2.solvers.pono import PonoSolver
from gurdy.pairs.aarch64_btor2.solvers.z3bmc import Z3BMCSolver
from gurdy.pairs.aarch64_btor2.solvers.z3spacer import Z3SpacerSolver
from gurdy.pairs.aarch64_btor2.spec import Aarch64Btor2Spec, validate_aarch64_btor2_spec


PAIR_ID = "aarch64-btor2"
SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Stub callables (replaced in subsequent phases)
# ---------------------------------------------------------------------------


from gurdy.pairs.aarch64_btor2.lift.lift import Lifter as _Lifter
from gurdy.pairs.aarch64_btor2.source.loader import load_aarch64_binary
from gurdy.pairs.aarch64_btor2.translation.translate import translate as _translate

_lifter_instance = _Lifter()


def _source_loader_stub(payload: Any) -> Any:
    return load_aarch64_binary(payload)


def _translator_stub(spec: Any, source: Any, annotation_emitter: Any) -> Any:
    return _translate.translate(spec, source, annotation_emitter)


def _lifter_stub(artifact: Any, raw: Any) -> Any:
    return _lifter_instance.lift(artifact, raw)


# ---------------------------------------------------------------------------
# Layer declarations — mirror SCHEMA.md layer set
# ---------------------------------------------------------------------------

AARCH64_BTOR2_LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec(
        name="header",
        stability="universal",
        description="sort declarations",
    ),
    LayerSpec(
        name="machine",
        stability="per-isa-and-core-count",
        depends_on=("header",),
        description="state-variable declarations: x0–x30, sp, pc, nzcv, halted, nondet",
    ),
    LayerSpec(
        name="library",
        stability="per-isa",
        depends_on=("header", "machine"),
        description="per-instruction lowering for AArch64 A64 base integer ISA",
    ),
    LayerSpec(
        name="dispatch",
        stability="per-analyzed-function-set",
        depends_on=("header", "machine", "library"),
        description="PC-keyed ITE selecting which library lowering applies",
    ),
    LayerSpec(
        name="init",
        stability="per-question",
        depends_on=("header", "machine"),
        description="initial-state clauses",
    ),
    LayerSpec(
        name="constraint",
        stability="per-question",
        depends_on=("header", "machine"),
        description="invariants and assumptions; carries provenance",
    ),
    LayerSpec(
        name="bad",
        stability="per-question",
        depends_on=("header", "machine"),
        description="property under investigation",
    ),
    LayerSpec(
        name="binding",
        stability="per-question",
        depends_on=("header", "machine", "library", "dispatch"),
        description="next clauses wiring states to dispatch",
    ),
    LayerSpec(
        name="havoc",
        stability="per-question",
        depends_on=("header", "machine", "binding"),
        description="optional overlay replacing register/sp transitions with fresh inputs",
    ),
)


# ---------------------------------------------------------------------------
# Pair registration
# ---------------------------------------------------------------------------

PAIR = Pair(
    identifier=PAIR_ID,
    schema_version=SCHEMA_VERSION,
    source_loader=_source_loader_stub,
    spec_class=Aarch64Btor2Spec,
    spec_validator=validate_aarch64_btor2_spec,
    layer_specs=AARCH64_BTOR2_LAYERS,
    translator=_translator_stub,
    lifter=_lifter_stub,
    solvers={
        "z3-bmc": Z3BMCSolver,
        "z3-spacer": Z3SpacerSolver,
        "bitwuzla": BitwuzlaSolver,
        "cvc5": Cvc5Solver,
        "pono": PonoSolver,
    },
    schema_path=Path(__file__).parent / "SCHEMA.md",
    reasoning_interpreter=Btor2ReasoningInterpreter(),
    # source_interpreter, projection, witness_replayer, predicate_evaluator:
    # deferred to P2 (source interpreter) and P4 (translator / lifter).
    interpreter_version="",
)

register_pair(PAIR)


__all__ = ["PAIR", "PAIR_ID", "SCHEMA_VERSION", "AARCH64_BTOR2_LAYERS"]
