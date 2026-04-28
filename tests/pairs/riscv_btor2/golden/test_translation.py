"""End-to-end tests for the translation pipeline."""

from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
from gurdy.pairs.riscv_btor2.btor2.parser import from_text
from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    Comparison,
    Property,
    RegisterAt,
    RegisterInit,
    RiscvBtor2Spec,
)
from gurdy.pairs.riscv_btor2.translation.translate import Translator

from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000

# Same instructions used in phase 6 tests:
# addi a0, x0, 1
# addi a0, a0, 1
# ret  (jalr x0, 0(ra))
ADD2_BYTES = bytes.fromhex("13050100" "13051500" "67800000")


def _make_binary(tmp_path):
    funcs = [FuncDef(name="add2", addr=TEXT_BASE, size=len(ADD2_BYTES))]
    p = tmp_path / "add2.elf"
    p.write_bytes(build_elf(ADD2_BYTES, TEXT_BASE, funcs))
    return p


def _basic_spec(path):
    return RiscvBtor2Spec(
        binary=BinaryRef(path=str(path)),
        scope=AnalysisScope(entry_function="add2"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )


def _translate(spec, src):
    sidecar = AnnotationSidecar(schema_version="1.0.0", spec_hash=spec.spec_hash())
    emitter = AnnotationEmitter(sidecar)
    return Translator().translate(spec, src, emitter)


def test_translate_emits_all_layers(tmp_path):
    p = _make_binary(tmp_path)
    src = load_riscv_binary(p)
    spec = _basic_spec(p)
    art = _translate(spec, src)
    expected = {
        "header",
        "machine",
        "library",
        "dispatch",
        "init",
        "constraint",
        "bad",
        "binding",
        "havoc",
    }
    assert set(art.layers) == expected
    # Header must be non-empty; havoc may be empty.
    assert len(art.layers["header"].body) > 0
    assert len(art.layers["machine"].body) > 0
    assert len(art.layers["library"].body) > 0


def test_flattened_output_parses_through_btor2_parser(tmp_path):
    p = _make_binary(tmp_path)
    spec = _basic_spec(p)
    art = _translate(spec, load_riscv_binary(p))
    res = from_text(art.flattened.decode("utf-8"))
    assert not res.has_errors(), [d.render() for d in res.diagnostics][:5]


def test_compile_is_byte_deterministic(tmp_path):
    p = _make_binary(tmp_path)
    spec = _basic_spec(p)
    a1 = _translate(spec, load_riscv_binary(p))
    a2 = _translate(spec, load_riscv_binary(p))
    assert a1.flattened == a2.flattened
    assert a1.spec_hash == a2.spec_hash


def test_layer_reuse_changing_property_does_not_disturb_lower_layers(tmp_path):
    p = _make_binary(tmp_path)
    spec1 = _basic_spec(p)
    spec2 = RiscvBtor2Spec(
        binary=spec1.binary,
        scope=spec1.scope,
        observables=spec1.observables,
        property=Property(expression="eq(reg(10), 7)"),
        analysis=spec1.analysis,
    )
    a1 = _translate(spec1, load_riscv_binary(p))
    a2 = _translate(spec2, load_riscv_binary(p))
    for stable in ("header", "machine", "library", "dispatch", "binding"):
        assert a1.layers[stable].body == a2.layers[stable].body, (
            f"layer {stable!r} should be stable across property-only changes"
        )
    assert a1.layers["bad"].body != a2.layers["bad"].body


def test_layer_reuse_changing_havoc_only_changes_havoc(tmp_path):
    p = _make_binary(tmp_path)
    spec1 = _basic_spec(p)
    spec2 = RiscvBtor2Spec(
        binary=spec1.binary,
        scope=spec1.scope,
        observables=spec1.observables,
        property=spec1.property,
        analysis=AnalysisDirective(
            engine="z3-bmc", bound=10, havoc_registers=frozenset([3])
        ),
    )
    a1 = _translate(spec1, load_riscv_binary(p))
    a2 = _translate(spec2, load_riscv_binary(p))
    for stable in ("header", "machine", "library", "dispatch", "init", "bad", "binding"):
        assert a1.layers[stable].body == a2.layers[stable].body, stable
    assert a1.layers["havoc"].body != a2.layers["havoc"].body


def test_register_init_lands_in_init_layer(tmp_path):
    p = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="add2"),
        assumptions=(RegisterInit(register=10, op=Comparison.EQ, value=0),),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    art = _translate(spec, load_riscv_binary(p))
    init = art.layers["init"].body.decode("utf-8")
    assert "init" in init


def test_annotation_records_state_emissions(tmp_path):
    p = _make_binary(tmp_path)
    art = _translate(_basic_spec(p), load_riscv_binary(p))
    states = art.annotation.by_role("state")
    # 31 GPRs (excluding x0) + pc + mem + halted = 34
    assert len(states) >= 31
