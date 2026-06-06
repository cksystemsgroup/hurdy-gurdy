"""The first chain: ``C -> RV64 ELF -> BTOR2``.

Composes the ``c-riscv`` compile hop (``gurdy.hops.c_riscv``) with the
``riscv-btor2`` pair. The composer *translates only* — it does no
reasoning. Concretely it:

1. compiles C to RV64 ELF reproducibly (hop 1),
2. resolves the trap symbol's PC in-process from the compiled ELF,
3. synthesizes the corpus-convention "is ``trap`` reachable?" spec, and
4. translates ``(spec, ELF bytes) -> BTOR2`` via the pair (hop 2),

threading per-hop provenance and keeping the source so the transitive
source map ``BTOR2 nid -> pc -> C file:line`` can be realized at lift
time. Choosing *whether/how* to dispatch and what to conclude stays
with the caller (the LLM / an oracle); see ``DESIGN_c_to_btor2_chain.md``.

The spec synthesis encodes the bare-metal "embedded trap" convention
(the same one ``bench/riscv-btor2/corpus/_compile_c.py`` uses): the
property is ``eq(pc, const(<trap pc>))``. All non-address choices are
explicit parameters with corpus-convention defaults, so the caller
keeps control of the question.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.chain import Chain, ChainStep, StepOutcome
from gurdy.core.hop import Tier, get_hop, weakest_tier
from gurdy.core.interp.chain_align import (
    ChainAlignmentReport,
    SkippedHop,
    align_chain,
    segment_from_joined,
)
from gurdy.core.pair import CompiledArtifact, get_pair
from gurdy.core.tools.compile import compile_spec
from gurdy.hops.c_riscv import (
    CCompileResult,
    Provenance,
    ToolchainPin,
    cbmc_verify,
    classify_differential,
    compile_c,
    default_pin,
)
from gurdy.hops.c_riscv.dwarf import extract_line_map
from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers the pair)
from gurdy.pairs.riscv_btor2.lift.lift import LiftedResult
from gurdy.pairs.riscv_btor2.source.dwarf import DWARFLineTable, SourceLocation
from gurdy.pairs.riscv_btor2.source.loader import RISCVSource, load_riscv_binary
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec

_PAIR_ID = "riscv-btor2"


class SymbolNotFound(RuntimeError):
    """The requested symbol is absent from the compiled ELF."""


@dataclass(frozen=True)
class VerificationReport:
    """Result of the independent CBMC differential on the C source — a second
    path ``C -> verdict`` (``gurdy/hops/c_riscv/verify.py``) — and the chain
    trust it re-establishes.

    ``classification`` is from ``classify_differential``: ``agree`` /
    ``expected-divergence`` / ``fault`` / ``inconclusive``. When it is
    ``agree`` the opaque ``c-riscv`` compile hop is independently corroborated
    for this question, so its effective tier rises ``reproducible -> checked``
    and ``effective_trust`` is the re-established chain trust (vs the statically
    declared ``declared_trust``). This realizes the "verifier hop re-establishes
    trust" rule (``DESIGN_generalized_pairs.md`` §4) as a per-run capability,
    not a routing edge — CBMC is a second path C->verdict, not an
    ``L_in -> L_out`` translation."""

    chain_verdict: str
    cbmc_verdict: str
    classification: str
    verified: bool
    declared_trust: Tier
    effective_trust: Tier
    verified_hops: tuple[str, ...]
    cbmc_provenance: dict[str, Any]
    note: str = ""

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "chain_verdict": self.chain_verdict,
            "cbmc_verdict": self.cbmc_verdict,
            "classification": self.classification,
            "verified": self.verified,
            "declared_trust": self.declared_trust.value,
            "effective_trust": self.effective_trust.value,
            "verified_hops": list(self.verified_hops),
            "cbmc_provenance": self.cbmc_provenance,
            "note": self.note,
        }


@dataclass(frozen=True)
class ChainResult:
    """The output of the ``C -> RV64 ELF -> BTOR2`` chain.

    Carries the hop-2 reasoning artifact plus everything needed to
    dispatch it, ground its results in C, and re-derive it: the
    synthesized ``spec``, the hop-1 ``elf_bytes`` and ``source``, the
    compile ``provenance``, and the resolved ``trap_pc``.
    """

    artifact: CompiledArtifact
    spec: RiscvBtor2Spec
    elf_bytes: bytes
    source: RISCVSource
    compile_provenance: Provenance
    trap_pc: int
    c_source: bytes  # the hop-1 input, retained for the CBMC differential (verify)

    @property
    def provenance(self) -> list[dict[str, Any]]:
        """Per-hop provenance: ``[c-riscv hop, riscv-btor2 hop]``."""
        return [
            {"hop": "c-riscv", **self.compile_provenance.to_jsonable()},
            {
                "hop": _PAIR_ID,
                "schema_version": self.artifact.schema_version,
                "spec_hash": self.artifact.spec_hash,
            },
        ]

    def lift(self, raw: RawSolverResult) -> LiftedResult:
        """Lift a raw verdict to source-grounded facts, plumbing the
        chain's own source so the transitive ``pc -> C file:line`` map
        is populated. (The standalone ``lift`` tool returns a degraded
        trace because the annotation doesn't carry the binary; the chain
        retains it.)"""
        return get_pair(_PAIR_ID).lifter.lift(self.artifact, raw, source=self.source)

    def align(self, raw: RawSolverResult) -> ChainAlignmentReport:
        """Chain-level alignment of a solver witness — the paste lemma made
        executable. Replays the witness through the reasoning hop's
        interpreters and walks its commuting square, localizing any divergence
        to a hop / step / label. The compile hop (``c-riscv``) is opaque
        (reproducible tier) with no interpreters, so it is recorded as
        *skipped* — its faithfulness rests on the toolchain pin and the CBMC
        differential, not on trace alignment. Intended for witness-bearing
        (reachable) verdicts."""
        pair = get_pair(_PAIR_ID)
        joined = pair.witness_replayer(self.artifact, raw, source=self.source)
        projection = pair.projection(self.artifact)
        segment = segment_from_joined(_PAIR_ID, joined, projection)
        skipped = (
            SkippedHop(
                hop="c-riscv",
                reason=(
                    "compile hop (reproducible tier): no interpreters; "
                    "faithfulness rests on the toolchain pin and the CBMC "
                    "differential, not trace alignment"
                ),
            ),
        )
        return align_chain([segment], skipped=skipped)

    def verify(
        self,
        raw: RawSolverResult,
        *,
        lowering_sensitive: bool = False,
        pin: ToolchainPin | None = None,
    ) -> VerificationReport:
        """Independently re-check the chain's verdict by running CBMC on the C
        source (the second path ``C -> verdict``), and report the chain trust it
        re-establishes.

        On agreement the opaque ``c-riscv`` hop is corroborated for this
        question, lifting its effective tier ``reproducible -> checked`` and the
        chain's effective trust with it. Pass ``lowering_sensitive=True`` for a
        task whose C-level UB and RV64-defined behaviour legitimately differ, so
        a disagreement is classified ``expected-divergence`` rather than a
        ``fault``. Needs the pinned image (raises ``ToolchainUnavailable`` if
        absent)."""
        cbmc = cbmc_verify(
            self.c_source, bound=self.spec.analysis.bound, pin=pin or default_pin()
        )
        classification = classify_differential(
            raw.verdict, cbmc.verdict, lowering_sensitive=lowering_sensitive
        )
        verified = classification == "agree"

        hop_ids = ("c-riscv", _PAIR_ID)
        declared = weakest_tier([get_hop(h).tier for h in hop_ids])
        if verified:
            effective = weakest_tier(
                [Tier.checked if h == "c-riscv" else get_hop(h).tier for h in hop_ids]
            )
            verified_hops: tuple[str, ...] = ("c-riscv",)
            note = (
                "CBMC on the C source independently corroborates the chain "
                "verdict; c-riscv lifted reproducible -> checked."
            )
        else:
            effective = declared
            verified_hops = ()
            note = {
                "fault": (
                    "CBMC disagrees on a non-lowering-sensitive task: a suspected "
                    "C->ELF translation/analysis fault (hop c-riscv)."
                ),
                "expected-divergence": (
                    "CBMC disagrees as expected on a lowering-sensitive task "
                    "(C UB vs RV64-defined); not a fault, trust not lifted."
                ),
                "inconclusive": (
                    "one side is not a definite reachable/unreachable verdict; "
                    "nothing corroborated."
                ),
            }.get(classification, "")

        return VerificationReport(
            chain_verdict=raw.verdict,
            cbmc_verdict=cbmc.verdict,
            classification=classification,
            verified=verified,
            declared_trust=declared,
            effective_trust=effective,
            verified_hops=verified_hops,
            cbmc_provenance=cbmc.provenance.to_jsonable(),
            note=note,
        )


@dataclass(frozen=True)
class _TranslateOutput:
    """Output of the reasoning hop (``rv64-elf -> btor2``): the BTOR2 artifact
    plus the chain-specific context built alongside it — the synthesized spec,
    the DWARF-populated source, and the resolved trap PC."""

    artifact: CompiledArtifact
    spec: RiscvBtor2Spec
    source: RISCVSource
    trap_pc: int


def _load_source_with_lines(
    elf_bytes: bytes, pin: ToolchainPin
) -> RISCVSource:
    """Load the ELF and populate its DWARF line table from the pinned
    objdump, so witness lift can recover C ``file:line`` (the source
    loader's own ``from_elf`` returns an empty table for byte input)."""
    source = load_riscv_binary(elf_bytes)
    entries, end_pc = extract_line_map(elf_bytes, pin=pin)
    table = DWARFLineTable()
    table.end_pc = end_pc
    for e in entries:
        table.add(e.pc, SourceLocation(file=e.file, line=e.line))
    source.line_table = table
    return source


def _resolve_symbol_pc(source: RISCVSource, name: str) -> int:
    fn = source.function(name)
    if fn is None:
        raise SymbolNotFound(f"symbol {name!r} not found in compiled ELF")
    return fn.start


def _build_spec(
    trap_pc: int,
    *,
    entry_function: str,
    included_callees: Sequence[str],
    engine: str,
    bound: int,
    timeout: int,
    source_name: str,
) -> RiscvBtor2Spec:
    return RiscvBtor2Spec.from_jsonable(
        {
            "pair": _PAIR_ID,
            "fields": {
                # The binary is generated by hop 1 and passed to the pair
                # as bytes; this is a logical reference, never dereferenced.
                "binary": {"path": source_name},
                "scope": {
                    "entry_function": entry_function,
                    "included_callees": list(included_callees),
                },
                "entry": {"excluded_pc_ranges": []},
                "observables": [],
                "assumptions": [],
                "learned": [],
                "property": {
                    "expression": f"eq(pc, const(0x{trap_pc:x}))",
                    "negate": False,
                },
                "analysis": {
                    "engine": engine,
                    "bound": bound,
                    "timeout": timeout,
                    "havoc_registers": ["__set__"],
                    "extra_options": {},
                },
            },
        }
    )


def compile_c_to_btor2(
    c_source: bytes | str,
    *,
    trap_function: str = "trap",
    entry_function: str = "_start",
    included_callees: Sequence[str] | None = None,
    engine: str = "z3-bmc",
    bound: int = 20,
    timeout: int = 60,
    opt_level: str = "0",
    source_name: str = "module.c",
    pin: ToolchainPin | None = None,
) -> ChainResult:
    """Run the ``C -> RV64 ELF -> BTOR2`` chain end-to-end (translate only).

    Thin wrapper over the generic chain runner (:mod:`gurdy.core.chain`): it
    binds the two registered hops (``c-riscv`` then ``riscv-btor2``) to their
    calls and drives them with :meth:`Chain.run`. The chain-specific work — the
    question synthesis (resolving the trap PC and building the spec from the
    compiled ELF) and the DWARF source map — lives in the hop closures, not in
    the runner.

    Returns a :class:`ChainResult`. Raises ``ToolchainUnavailable`` if the
    pinned compiler is absent (hop 1), ``CompileError`` on a compile failure,
    or :class:`SymbolNotFound` if ``trap_function`` is missing from the
    compiled ELF.
    """
    pin = pin or default_pin()
    callees = list(included_callees) if included_callees is not None else [trap_function]
    c_bytes = c_source.encode() if isinstance(c_source, str) else bytes(c_source)

    def _hop_compile(source_in: bytes | str) -> StepOutcome:
        res = compile_c(source_in, pin=pin, opt_level=opt_level, source_name=source_name)
        return StepOutcome(
            output=res,
            provenance={"hop": "c-riscv", **res.provenance.to_jsonable()},
        )

    def _hop_translate(res: CCompileResult) -> StepOutcome:
        # The reasoning hop synthesizes its own question from the compiled ELF
        # (the trap PC is an ELF address), so the spec is built here, not passed
        # in. This stays inside the hop; the runner sees only bytes-in/result-out.
        source = _load_source_with_lines(res.elf_bytes, pin)
        trap_pc = _resolve_symbol_pc(source, trap_function)
        spec = _build_spec(
            trap_pc,
            entry_function=entry_function,
            included_callees=callees,
            engine=engine,
            bound=bound,
            timeout=timeout,
            source_name=source_name,
        )
        artifact = compile_spec(spec, res.elf_bytes)
        return StepOutcome(
            output=_TranslateOutput(
                artifact=artifact, spec=spec, source=source, trap_pc=trap_pc
            ),
            provenance={
                "hop": _PAIR_ID,
                "schema_version": artifact.schema_version,
                "spec_hash": artifact.spec_hash,
            },
        )

    chain = Chain(
        [
            ChainStep(hop="c-riscv", in_lang="c", out_lang="rv64-elf", run=_hop_compile),
            ChainStep(
                hop=_PAIR_ID, in_lang="rv64-elf", out_lang="btor2", run=_hop_translate
            ),
        ]
    )
    execution = chain.run(c_bytes)
    compiled: CCompileResult = execution.outputs[0]
    translated: _TranslateOutput = execution.outputs[1]
    return ChainResult(
        artifact=translated.artifact,
        spec=translated.spec,
        elf_bytes=compiled.elf_bytes,
        source=translated.source,
        compile_provenance=compiled.provenance,
        trap_pc=translated.trap_pc,
        c_source=c_bytes,
    )


__all__ = ["ChainResult", "SymbolNotFound", "compile_c_to_btor2"]
