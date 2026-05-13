"""riscv-btor2 pair: RISC-V (RV64I+M+C) to BTOR2 translation.

Importing this module registers the pair with the framework's
``register_pair`` registry. Once registered, the LLM-facing tool
surface (``describe``, ``compile``, ``dispatch``, ``lift``,
``introspect``) routes ``pair="riscv-btor2"`` requests through this
package's ``Pair`` record.
"""

from __future__ import annotations

from pathlib import Path

from gurdy.core.pair import LayerSpec, Pair, register_pair
from gurdy.pairs.riscv_btor2.lift.lift import lift as _lift
from gurdy.pairs.riscv_btor2.lift.replayer import replay_witness as _replay_witness
from gurdy.pairs.riscv_btor2.reasoning_interp.interpreter import (
    INTERPRETER_VERSION as _INTERPRETER_VERSION,
    Btor2ReasoningInterpreter,
)
from gurdy.pairs.riscv_btor2.solvers.bitwuzla import BitwuzlaSolver
from gurdy.pairs.riscv_btor2.solvers.cvc5 import Cvc5Solver
from gurdy.pairs.riscv_btor2.solvers.pono import PonoSolver
from gurdy.pairs.riscv_btor2.solvers.z3bmc import Z3BMCSolver
from gurdy.pairs.riscv_btor2.solvers.z3spacer import Z3SpacerSolver
from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
from gurdy.pairs.riscv_btor2.source_interp.interpreter import RiscvSourceInterpreter
from gurdy.pairs.riscv_btor2.source_interp.predicates import evaluate_spec as _evaluate_spec
from gurdy.pairs.riscv_btor2.source_interp.projection import make_projection
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec, validate_riscv_btor2_spec
from gurdy.pairs.riscv_btor2.translation.translate import (
    SCHEMA_VERSION as _SCHEMA_VERSION,
    translate as _translate,
)


PAIR_ID = "riscv-btor2"


def _projection_factory_for_artifact(artifact):
    """Return a ``Projection`` for the given compiled artifact.

    Walks the flattened BTOR2 once to extract the state symbol →
    nid table, then closes over it to produce the projection callable
    cross-check uses to align traces.
    """
    from gurdy.pairs.riscv_btor2.btor2.parser import from_text

    text = artifact.flattened.decode("utf-8", errors="replace")
    parsed = from_text(text)
    sym_to_nid: dict[str, int] = {}
    for n in parsed.model.nodes():
        if n.op == "state" and n.symbol:
            sym_to_nid[n.symbol] = n.nid
    return make_projection(sym_to_nid)


# Layer declarations match SCHEMA.md and translation/layers.LAYER_NAMES.
RISCV_BTOR2_LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec(
        name="header",
        stability="universal",
        description="sort declarations",
    ),
    LayerSpec(
        name="machine",
        stability="per-isa-and-core-count",
        depends_on=("header",),
        description="state-variable declarations",
    ),
    LayerSpec(
        name="library",
        stability="per-isa",
        depends_on=("header", "machine"),
        description="per-instruction lowering definitions",
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
        description="branch pins, dual-role companion bad clauses, and synthesized memory pins; per-question churn isolated from constraint (SCHEMA.md §14.5)",
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
        description="optional overlay replacing register transitions with fresh inputs",
    ),
)


PAIR = Pair(
    identifier=PAIR_ID,
    schema_version=_SCHEMA_VERSION,
    source_loader=load_riscv_binary,
    spec_class=RiscvBtor2Spec,
    spec_validator=validate_riscv_btor2_spec,
    layer_specs=RISCV_BTOR2_LAYERS,
    translator=_translate,
    lifter=_lift,
    solvers={
        "z3-bmc": Z3BMCSolver,
        "z3-spacer": Z3SpacerSolver,
        "bitwuzla": BitwuzlaSolver,
        "cvc5": Cvc5Solver,
        "pono": PonoSolver,
    },
    schema_path=Path(__file__).parent / "SCHEMA.md",
    source_interpreter=RiscvSourceInterpreter(),
    reasoning_interpreter=Btor2ReasoningInterpreter(),
    projection=_projection_factory_for_artifact,
    witness_replayer=_replay_witness,
    predicate_evaluator=_evaluate_spec,
    interpreter_version=_INTERPRETER_VERSION,
)


register_pair(PAIR)


__all__ = ["PAIR", "PAIR_ID", "RISCV_BTOR2_LAYERS"]
