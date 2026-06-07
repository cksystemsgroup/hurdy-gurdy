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

from gurdy.core.pair import LayerSpec, Pair, Preservation, Tier, register_pair
from gurdy.core.language import Language, register_language
from gurdy.pairs.aarch64_btor2.lift.replayer import replay_witness as _replay_witness
from gurdy.pairs.aarch64_btor2.reasoning_interp.interpreter import (
    Btor2ReasoningInterpreter,
)
from gurdy.pairs.aarch64_btor2.source_interp.interpreter import (
    AArch64SourceInterpreter,
    INTERPRETER_VERSION as _INTERPRETER_VERSION,
)
from gurdy.pairs.aarch64_btor2.source_interp.projection import make_projection
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

from gurdy.core.btor2.parser import from_text as _btor2_from_text


def _projection_factory_for_artifact(artifact):
    """Walk the flattened BTOR2 once for the state symbol -> nid table, then
    close over it to produce the projection the alignment oracle uses (mirrors
    riscv-btor2)."""
    parsed = _btor2_from_text(artifact.flattened.decode("utf-8", errors="replace"))
    sym_to_nid = {
        n.symbol: n.nid for n in parsed.model.nodes() if n.op == "state" and n.symbol
    }
    return make_projection(sym_to_nid)

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
        name="volatile",
        stability="per-question",
        depends_on=("header", "machine", "library", "dispatch", "constraint"),
        description="branch pins and dual-role companion bad clauses; per-question churn isolated from constraint",
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
    in_lang="aarch64-elf",
    out_lang="btor2",
    tier=Tier.transparent,
    preservation=Preservation(
        keeps=("pc", "registers", "sp", "nzcv", "memory", "halted"),
        discards=("instruction-timing", "microarchitectural-state"),
        note=(
            "faithful bit-level transition encoding; the projection's observable "
            "set (pc, x0..x30, sp, nzcv, memory, halted) is preserved."
        ),
    ),
    schema_version=SCHEMA_VERSION,
    source_loader=_source_loader_stub,
    spec_class=Aarch64Btor2Spec,
    spec_validator=validate_aarch64_btor2_spec,
    layer_specs=AARCH64_BTOR2_LAYERS,
    translator=_translate,
    lifter=_lifter_stub,
    solvers={
        "z3-bmc": Z3BMCSolver,
        "z3-spacer": Z3SpacerSolver,
        "bitwuzla": BitwuzlaSolver,
        "cvc5": Cvc5Solver,
        "pono": PonoSolver,
    },
    schema_path=Path(__file__).parent / "SCHEMA.md",
    source_interpreter=AArch64SourceInterpreter(),
    reasoning_interpreter=Btor2ReasoningInterpreter(),
    witness_replayer=_replay_witness,
    projection=_projection_factory_for_artifact,  # step-level alignment oracle
    # predicate_evaluator (the `check` tool) is the remaining aarch64 parity item;
    # source_interp/predicates.py is not yet written.
    interpreter_version=_INTERPRETER_VERSION,
)

register_pair(PAIR)


# Register the pair's input language. The output language ``btor2`` is a shared
# reasoning language already registered by the first BTOR2 pair (riscv-btor2);
# pairs reference it via ``out_lang`` and do not re-register it (the descriptor's
# ``reasons_via`` is pair-specific — a cross-pair union is a later refinement).
register_language(
    Language(
        id="aarch64-elf",
        kind="representation",
        semantics="AArch64 (ARMv8-A base integer) ELF executable image",
    )
)


__all__ = ["PAIR", "PAIR_ID", "SCHEMA_VERSION", "AARCH64_BTOR2_LAYERS"]
