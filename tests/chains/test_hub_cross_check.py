"""Stage 7.F — the first populated-hub payoff.

``btor2_smtlib.cross_check`` decides a BTOR2 model two independent ways — native
(BTOR2 → z3 via ``gurdy.core.btor2``) and bridged (BTOR2 → SMT-LIB → z3) — and
reports agreement. The encoders are independent, so agreement corroborates both
and a disagreement localizes a translator/encoder bug. This is the
"many paths, one question" detector of ``DESIGN_generalized_pairs.md`` §6, run
here against *real source-pair translator output* — and across two ISAs, the
first cross-language equivalence through the BTOR2 hub.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
from gurdy.pairs.btor2_smtlib.cross_check import CrossCheck, cross_check

try:
    import z3  # noqa: F401

    _HAS_Z3 = True
except ImportError:  # pragma: no cover
    _HAS_Z3 = False
_needs_z3 = pytest.mark.skipif(not _HAS_Z3, reason="z3 not installed")


# bad holds at the initial state — reachable at any bound.
_REACH0 = """
1 sort bitvec 2
2 sort bitvec 1
3 zero 1
4 state 1 c
5 init 1 4 3
6 eq 2 4 3
7 bad 6
"""

# 3-bit counter; bad when c == 7, unreachable within bound 3 (c only reaches 3).
_COUNTER3_UNREACH = """
1 sort bitvec 3
2 sort bitvec 1
3 zero 1
4 state 1 c
5 init 1 4 3
6 one 1
7 add 1 4 6
8 next 1 4 7
9 constd 1 7
10 eq 2 4 9
11 bad 10
"""


def _riscv_reg10_reaches_2_btor2() -> bytes:
    """Real riscv-btor2 translator output for: ``addi a0,x0,1; addi a0,a0,1; ret``
    (a0 := 2), asking ``eq(reg(10), 2)`` — reachable."""
    from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
    from gurdy.pairs.riscv_btor2.spec import (
        AnalysisDirective,
        AnalysisScope,
        BinaryRef,
        Property,
        RegisterAt,
        RiscvBtor2Spec,
    )
    from gurdy.pairs.riscv_btor2.translation.translate import Translator
    from tests.fixtures.elf_builder import FuncDef, build_elf

    tb = 0x10000
    code = bytes.fromhex("13050100" "13051500" "67800000")  # addi a0,x0,1; addi a0,a0,1; ret
    elf = pathlib.Path(tempfile.mkdtemp()) / "add2.elf"
    elf.write_bytes(build_elf(code, tb, [FuncDef(name="add2", addr=tb, size=len(code))]))
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(elf)),
        scope=AnalysisScope(entry_function="add2"),
        observables=(RegisterAt(register=10, pc=tb),),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    sc = AnnotationSidecar(schema_version="1.0.0", spec_hash=spec.spec_hash())
    return Translator().translate(spec, load_riscv_binary(elf), AnnotationEmitter(sc)).flattened


def _aarch64_reg0_reaches_2_btor2() -> bytes:
    """Real aarch64-btor2 translator output for: ``movz x0,#2; ret`` (x0 := 2),
    asking ``eq(reg(0), 2)`` — reachable. The A64 counterpart of the riscv case."""
    from gurdy.pairs.aarch64_btor2 import spec as A
    from gurdy.pairs.aarch64_btor2.source.loader import load_aarch64_binary
    from gurdy.pairs.aarch64_btor2.translation.translate import Translator
    from tests.fixtures.elf_builder_aarch64 import FuncDef, build_elf

    tb = 0x400000
    code = bytes.fromhex("400080d2" "c0035fd6")  # movz x0,#2 ; ret
    elf = pathlib.Path(tempfile.mkdtemp()) / "prog.elf"
    elf.write_bytes(build_elf(code, tb, [FuncDef(name="prog", addr=tb, size=len(code))], entry=tb))
    spec = A.Aarch64Btor2Spec(
        binary=A.BinaryRef(path=str(elf)),
        scope=A.AnalysisScope(entry_function="prog"),
        observables=(A.RegisterAt(register=0, pc=tb),),
        property=A.Property(expression="eq(reg(0), 2)"),
        analysis=A.AnalysisDirective(engine="z3-bmc", bound=10),
    )
    sc = AnnotationSidecar(schema_version="1.0.0", spec_hash=spec.spec_hash())
    return Translator().translate(spec, load_aarch64_binary(elf), AnnotationEmitter(sc)).flattened


def _ebpf_exit_reached_btor2() -> bytes:
    """Real ebpf-btor2 translator output for ``r0 += 1; EXIT`` asking
    ``exit_reached`` — reachable. The third source pair on the hub."""
    import struct

    from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
    from gurdy.pairs.ebpf_btor2.spec import (
        AnalysisDirective,
        EbpfBtor2Spec,
        EbpfProgramRef,
        EbpfScope,
        Property,
    )
    from gurdy.pairs.ebpf_btor2.translation import translate

    def _insn(op, dst=0, src=0, off=0, imm=0):
        return struct.pack("<BBhi", op, (src << 4) | dst, off, imm)

    bytecode = _insn(0x07, 0, 0, 0, 1) + _insn(0x95)  # r0 += 1 ; EXIT
    spec = EbpfBtor2Spec(
        program=EbpfProgramRef(path=""),
        scope=EbpfScope(max_insns=8),
        property=Property(expression="exit_reached"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=3),
    )
    sc = AnnotationSidecar(schema_version="1.0.0", spec_hash=spec.spec_hash())
    return translate(spec, bytecode, AnnotationEmitter(sc)).flattened


def _wasm_add_wrap_btor2() -> bytes:
    """Real wasm-btor2 translator output for the ``0001-i32-add-wrap`` seed,
    asking REACH_TRAP — unreachable at bound 8. The fourth source pair on the
    hub, and the first hub input carrying an array sort (linear memory)."""
    from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
    from gurdy.pairs.wasm_btor2.source import load_wasm_source
    from gurdy.pairs.wasm_btor2.spec import (
        AnalysisScope,
        PropertyKind,
        QuestionSpec,
        WasmBtor2Spec,
        WasmModuleRef,
    )
    from gurdy.pairs.wasm_btor2.translation import SCHEMA_VERSION, Translator

    seed = (
        pathlib.Path(__file__).resolve().parents[2]
        / "bench/wasm-btor2/corpus/seed/0001-i32-add-wrap/module.wasm"
    )
    source = load_wasm_source(seed.read_bytes())
    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="module.wasm"),
        scope=AnalysisScope(entry_function="main"),
        question=QuestionSpec(kind=PropertyKind.REACH_TRAP),
    )
    sc = AnnotationSidecar(schema_version=SCHEMA_VERSION, spec_hash="")
    return Translator().translate(spec, source, AnnotationEmitter(sc)).flattened


def _evm_btor2(hexcode: str, kind) -> bytes:
    """Real evm-btor2 translator output for ``hexcode`` asking reach-``kind``.

    evm-btor2 is not yet a registered Pair (its flat-string translator has no
    layered CompiledArtifact — see PLAN.md Stage 7.E), but the hub cross-check
    operates on raw BTOR2 bytes, so it still corroborates evm's translator
    against the independent SMT-LIB encoder. evm output is bv256 + arrays; the
    native path goes through ``core.btor2`` (which parses and solves it)."""
    from gurdy.pairs.evm_btor2.spec import BytecodeRef, EvmBtor2Spec, ReachProperty
    from gurdy.pairs.evm_btor2.translation.translator import translate_bytecode

    spec = EvmBtor2Spec(
        bytecode=BytecodeRef(hex=hexcode), property=ReachProperty(kind=kind)
    )
    return translate_bytecode(bytes.fromhex(hexcode), spec).encode("utf-8")


@_needs_z3
@pytest.mark.parametrize(
    "btor2,bound,expected",
    [(_REACH0, 3, "reachable"), (_COUNTER3_UNREACH, 3, "unreachable")],
)
def test_native_and_bridged_paths_agree(btor2, bound, expected):
    cc = cross_check(btor2, bound=bound)
    assert cc.agree, cc.summary()
    assert cc.verdict == expected
    assert set(cc.verdicts) == {"native", "bridged"}


@_needs_z3
def test_cross_check_validates_real_riscv_translator_output():
    """The hub payoff: the SMT-LIB bridge independently corroborates the real
    riscv-btor2 translator's BTOR2 (all layers), not a hand-written model. A
    native-vs-bridged disagreement here would be a real riscv translation bug."""
    cc = cross_check(_riscv_reg10_reaches_2_btor2(), bound=10)
    assert cc.agree, cc.summary()
    assert cc.verdict == "reachable"


@_needs_z3
def test_cross_check_validates_real_aarch64_translator_output():
    """Same payoff for the second hub pair: the bridge corroborates real
    aarch64-btor2 translator output. The cross-check is pair-agnostic — it
    operates on BTOR2 bytes — so one primitive checks every translator."""
    cc = cross_check(_aarch64_reg0_reaches_2_btor2(), bound=10)
    assert cc.agree, cc.summary()
    assert cc.verdict == "reachable"


@_needs_z3
def test_cross_check_validates_real_ebpf_translator_output():
    """Same payoff for the third hub pair: the SMT-LIB bridge corroborates real
    ebpf-btor2 translator output (bv64 registers / bv32 insn_idx / bv1 flags).
    The cross-check is pair-agnostic — one primitive checks every translator —
    so the newly-registered ebpf pair joins riscv and aarch64 on the hub."""
    cc = cross_check(_ebpf_exit_reached_btor2(), bound=3)
    assert cc.agree, cc.summary()
    assert cc.verdict == "reachable"


@_needs_z3
def test_cross_check_validates_real_wasm_translator_output():
    """Fourth hub pair: the SMT-LIB bridge corroborates real wasm-btor2 output,
    which carries an *array* sort (linear memory) — so the bridge's array
    handling is exercised end-to-end. native and bridged agree (unreachable)."""
    cc = cross_check(_wasm_add_wrap_btor2(), bound=8)
    assert cc.agree, cc.summary()
    assert cc.verdict == "unreachable"


@_needs_z3
@pytest.mark.parametrize(
    "kind_name,expected",
    [("stop", "reachable"), ("revert", "unreachable")],
)
def test_cross_check_validates_real_evm_translator_output(kind_name, expected):
    """The hub primitive is pair-agnostic enough to corroborate even an
    *unregistered* translator: real evm-btor2 output (bv256 + arrays) for a
    ``STOP`` program agrees native-vs-bridged on both polarities — reaches STOP
    (reachable) but never REVERTs (unreachable). A disagreement would localize
    an evm translation/encoding bug; agreement de-risks the future evm Pair
    registration's solver path (PLAN.md Stage 7.E)."""
    from gurdy.pairs.evm_btor2.spec import ReachKind

    cc = cross_check(_evm_btor2("00", ReachKind(kind_name)), bound=4)
    assert cc.agree, cc.summary()
    assert cc.verdict == expected


@_needs_z3
def test_cross_isa_equivalence_riscv_vs_aarch64():
    """First cross-language equivalence through the hub: the same logical
    property — "a register reaches the value 2 after a tiny program that sets
    it" — expressed in RV64 and in A64, lowered to BTOR2 by two independent
    translators, yields the *same* verdict; and each is corroborated
    native-vs-bridged. Disagreement would localize a bug to one ISA's
    translator."""
    rv = cross_check(_riscv_reg10_reaches_2_btor2(), bound=10)
    a64 = cross_check(_aarch64_reg0_reaches_2_btor2(), bound=10)
    assert rv.agree, rv.summary()
    assert a64.agree, a64.summary()
    assert rv.verdict == a64.verdict == "reachable", f"riscv={rv.verdict} aarch64={a64.verdict}"


def test_disagreement_is_reported_and_localizable():
    """A divergence between paths is surfaced (agree=False, no single verdict)
    so a translator/encoder bug can be localized to the offending path."""
    cc = CrossCheck(bound=3, verdicts={"native": "reachable", "bridged": "unreachable"}, agree=False)
    assert not cc.agree
    assert cc.verdict is None
    assert "DISAGREE" in cc.summary()
    assert "native=reachable" in cc.summary() and "bridged=unreachable" in cc.summary()
