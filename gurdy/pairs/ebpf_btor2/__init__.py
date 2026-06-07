"""hurdy-gurdy ``ebpf-btor2`` pair: eBPF bytecode to BTOR2 translation.

Importing this module registers the pair with the framework's
``register_pair`` registry, so the translator-layer tool surface
(``describe``, ``compile``, ``dispatch``, ``lift``, ``introspect``)
routes ``pair="ebpf-btor2"`` requests through this package's ``Pair``.

Registered without interpreters (``interpreter_version=""``, the
framework's supported interpreter-free path): the source interpreter in
``source_interp`` runs directly via ``run(binding)`` rather than the
framework ``SourceInterpreter.run(source, binding, max_steps, *, spec)``
protocol, and no projection / witness-replayer / predicate evaluator is
built yet. So the interpreter-layer tools (``simulate``, ``evaluate``,
``cross_check``, ``replay``, ``check``) are deliberately not wired here.
Conforming the interpreter and adding the projection is the remaining
PAIRING.md §11/§14 work for this pair.
"""

from __future__ import annotations

from pathlib import Path

from gurdy.core.language import Language, register_language
from gurdy.core.pair import LayerSpec, Pair, Preservation, Tier, register_pair
from gurdy.pairs.ebpf_btor2.lift.lifter import lift_witness as _lift_witness
from gurdy.pairs.ebpf_btor2.solvers.z3bmc import Z3BMCSolver
from gurdy.pairs.ebpf_btor2.source import load_ebpf_source
from gurdy.pairs.ebpf_btor2.spec import (
    PAIR_ID,
    EbpfBtor2Spec,
    validate_ebpf_btor2_spec,
)
from gurdy.pairs.ebpf_btor2.translation import (
    SCHEMA_VERSION as _SCHEMA_VERSION,
    Translator,
)

SCHEMA_VERSION = _SCHEMA_VERSION


class _EbpfLifter:
    """Adapt ``lift_witness`` to the framework ``Lifter`` protocol.

    The lift tool calls ``pair.lifter.lift(artifact, raw)``; the ebpf
    lifter is a function over ``(flattened_btor2, witness_text,
    reachable)``. ``Z3BMCSolver`` carries the witness in its
    ``reachable`` payload under ``witness_text``.
    """

    def lift(self, artifact, raw):
        payload = raw.payload if isinstance(raw.payload, dict) else {}
        reachable = getattr(raw, "verdict", None) == "reachable"
        return _lift_witness(
            artifact.flattened, payload.get("witness_text", ""), reachable
        )


# Layer declarations match translation.LAYER_NAMES and SCHEMA.md.
EBPF_BTOR2_LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec(
        name="header",
        stability="universal",
        description="sort declarations",
    ),
    LayerSpec(
        name="machine",
        stability="per-program",
        depends_on=("header",),
        description="state-variable declarations: r0–r9, insn_idx, halted",
    ),
    LayerSpec(
        name="library",
        stability="per-program",
        depends_on=("header", "machine"),
        description="per-instruction update expressions for the eBPF subset",
    ),
    LayerSpec(
        name="dispatch",
        stability="per-program",
        depends_on=("header", "machine", "library"),
        description="insn_idx-keyed ITE selecting which instruction lowering applies",
    ),
    LayerSpec(
        name="init",
        stability="per-question",
        depends_on=("header", "machine"),
        description="entry-state constraints",
    ),
    LayerSpec(
        name="constraint",
        stability="per-question",
        depends_on=("header", "machine"),
        description="cycle assumptions from the spec; carries provenance",
    ),
    LayerSpec(
        name="bad",
        stability="per-question",
        depends_on=("header", "machine"),
        description="property violation expression",
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
    in_lang="ebpf",
    out_lang="btor2",
    tier=Tier.transparent,
    preservation=Preservation(
        keeps=("r0-r9", "insn_idx", "halted"),
        discards=("maps", "relocations", "BTF debug info", "r10 stack pointer"),
        note=(
            "faithful word-level transition encoding of the eBPF operational "
            "semantics over the program's register/pc state (P1 subset)."
        ),
    ),
    schema_version=_SCHEMA_VERSION,
    source_loader=load_ebpf_source,
    spec_class=EbpfBtor2Spec,
    spec_validator=validate_ebpf_btor2_spec,
    layer_specs=EBPF_BTOR2_LAYERS,
    translator=Translator(),
    lifter=_EbpfLifter(),
    solvers={"z3-bmc": Z3BMCSolver},
    schema_path=Path(__file__).parent / "SCHEMA.md",
)


register_pair(PAIR)

# Supplementary language metadata for the source language; routing reads
# in_lang/out_lang off the pair directly. The "btor2" reasoning language is
# registered by the riscv-btor2 pair.
register_language(
    Language(
        id="ebpf",
        kind="representation",
        semantics="eBPF bytecode (flat bpf_insn records)",
    )
)


__all__ = ["PAIR", "PAIR_ID", "SCHEMA_VERSION", "EBPF_BTOR2_LAYERS"]
