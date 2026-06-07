"""hurdy-gurdy ``wasm-btor2`` pair: WebAssembly to BTOR2 translation.

Importing this module registers the pair with the framework's
``register_pair`` registry, so the translator-layer tool surface
(``describe``, ``compile``, ``dispatch``, ``lift``, ``introspect``)
routes ``pair="wasm-btor2"`` requests through this package's ``Pair``.

Registered without interpreters (``interpreter_version=""``, the
framework's supported interpreter-free path): the source and reasoning
interpreters in this package exist and are tested directly, but do not
yet conform to the framework ``SourceInterpreter`` / ``ReasoningInterpreter``
protocols (``WasmSourceInterpreter.run`` takes ``entry_name`` /
``entry_func_idx`` rather than the protocol's ``spec`` keyword), and no
projection / witness-replayer / predicate evaluator is built yet. So the
interpreter-layer tools (``simulate``, ``evaluate``, ``cross_check``,
``replay``, ``check``) are deliberately not wired here. Conforming the
interpreters and adding the projection is the remaining PAIRING.md
§11/§14 work for this pair.
"""

from __future__ import annotations

from pathlib import Path

from gurdy.core.language import Language, register_language
from gurdy.core.pair import LayerSpec, Pair, Preservation, Tier, register_pair
from gurdy.pairs.wasm_btor2.lift.lifter import lift_witness as _lift_witness
from gurdy.pairs.wasm_btor2.solvers.z3bmc import Z3BMCSolver
from gurdy.pairs.wasm_btor2.source import load_wasm_source
from gurdy.pairs.wasm_btor2.spec import (
    PAIR_ID,
    WasmBtor2Spec,
    validate_wasm_btor2_spec,
)
from gurdy.pairs.wasm_btor2.translation.translate import (
    SCHEMA_VERSION as _SCHEMA_VERSION,
    Translator,
)


class _WasmLifter:
    """Adapt ``lift_witness`` to the framework ``Lifter`` protocol.

    The lift tool calls ``pair.lifter.lift(artifact, raw)``; the wasm
    lifter is a function over ``(flattened_btor2, witness_text)``. The
    witness text is carried in ``Z3BMCSolver``'s ``reachable`` payload
    under ``witness_text`` (absent/defaulted when not reachable).
    """

    def lift(self, artifact, raw):
        payload = raw.payload if isinstance(raw.payload, dict) else {}
        return _lift_witness(artifact.flattened, payload.get("witness_text", ""))


# Layer declarations match translation/layers.LAYER_NAMES and SCHEMA.md.
WASM_BTOR2_LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec(
        name="header",
        stability="universal",
        description="sort declarations",
    ),
    LayerSpec(
        name="machine",
        stability="per-module",
        depends_on=("header",),
        description="state-variable declarations: locals, globals, linear memory, value stack, pc, trapped",
    ),
    LayerSpec(
        name="library",
        stability="per-module",
        depends_on=("header", "machine"),
        description="per-instruction lowering for the WebAssembly instruction set",
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
)


PAIR = Pair(
    identifier=PAIR_ID,
    in_lang="wasm",
    out_lang="btor2",
    tier=Tier.transparent,
    preservation=Preservation(
        keeps=("locals", "globals", "memory", "value-stack", "pc", "trapped"),
        discards=("block/function structure", "validation types"),
        note=(
            "faithful word-level transition encoding of the WebAssembly "
            "operational semantics over the module's defined state."
        ),
    ),
    schema_version=_SCHEMA_VERSION,
    source_loader=load_wasm_source,
    spec_class=WasmBtor2Spec,
    spec_validator=validate_wasm_btor2_spec,
    layer_specs=WASM_BTOR2_LAYERS,
    translator=Translator(),
    lifter=_WasmLifter(),
    solvers={"z3-bmc": Z3BMCSolver},
    schema_path=Path(__file__).parent / "SCHEMA.md",
)


register_pair(PAIR)

# Supplementary language metadata for the source language; routing reads
# in_lang/out_lang off the pair directly. The "btor2" reasoning language is
# registered by the riscv-btor2 pair (registering it here too would conflict
# on the descriptor's reasons_via set).
register_language(
    Language(
        id="wasm",
        kind="representation",
        semantics="WebAssembly module binary",
    )
)


__all__ = ["PAIR", "PAIR_ID", "WASM_BTOR2_LAYERS"]
