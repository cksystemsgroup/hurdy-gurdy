from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    Comparison,
    Executed,
    MemoryInit,
    PCAtStep,
    Property,
    RegisterAt,
    RegisterInit,
    RiscvBtor2Spec,
    validate_riscv_btor2_spec,
)


class _SourceStub:
    def __init__(self, names):
        self._names = set(names)

    def function(self, name):
        if name in self._names:
            class F:
                pass
            f = F()
            f.start = 0x1000
            f.end = 0x2000
            return f
        return None


def test_valid_spec_passes_validation():
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path="bin.elf"),
        scope=AnalysisScope(entry_function="main"),
        observables=(RegisterAt(register=10, pc=0x1000),),
        assumptions=(RegisterInit(register=2, op=Comparison.EQ, value=0),),
        property=Property(expression="bad"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    src = _SourceStub(["main"])
    diags = list(validate_riscv_btor2_spec(spec, src))
    assert diags == [], diags


def test_missing_binary_path_diagnoses():
    spec = RiscvBtor2Spec(scope=AnalysisScope(entry_function="main"))
    diags = list(validate_riscv_btor2_spec(spec, _SourceStub(["main"])))
    codes = [d.code for d in diags]
    assert "riscv-btor2/spec/0002" in codes


def test_unknown_entry_function_diagnoses():
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path="bin.elf"),
        scope=AnalysisScope(entry_function="missing"),
    )
    diags = list(validate_riscv_btor2_spec(spec, _SourceStub(["main"])))
    codes = [d.code for d in diags]
    assert "riscv-btor2/spec/0004" in codes


def test_unknown_callee_diagnoses():
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path="bin.elf"),
        scope=AnalysisScope(entry_function="main", included_callees=("nope",)),
    )
    diags = list(validate_riscv_btor2_spec(spec, _SourceStub(["main"])))
    codes = [d.code for d in diags]
    assert "riscv-btor2/spec/0005" in codes


def test_register_out_of_range_diagnoses():
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path="bin.elf"),
        scope=AnalysisScope(entry_function="main"),
        observables=(RegisterAt(register=99, pc=0),),
    )
    diags = list(validate_riscv_btor2_spec(spec, _SourceStub(["main"])))
    codes = [d.code for d in diags]
    assert "riscv-btor2/spec/0010" in codes


def test_havoc_register_validated():
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path="bin.elf"),
        scope=AnalysisScope(entry_function="main"),
        analysis=AnalysisDirective(engine="z3-bmc", havoc_registers=frozenset([100])),
    )
    diags = list(validate_riscv_btor2_spec(spec, _SourceStub(["main"])))
    codes = [d.code for d in diags]
    assert "riscv-btor2/spec/0030" in codes


def test_negative_bound_diagnoses():
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path="bin.elf"),
        scope=AnalysisScope(entry_function="main"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=-1),
    )
    diags = list(validate_riscv_btor2_spec(spec, _SourceStub(["main"])))
    codes = [d.code for d in diags]
    assert "riscv-btor2/spec/0031" in codes


def test_spec_round_trips_through_jsonable():
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path="bin.elf"),
        scope=AnalysisScope(entry_function="main", included_callees=("foo",)),
        observables=(
            RegisterAt(register=10, pc=0x1000),
            PCAtStep(step=5),
            Executed(pc=0x1010),
        ),
        assumptions=(
            RegisterInit(register=2, op=Comparison.EQ, value=0),
            MemoryInit(address=0x2000, width=4, op=Comparison.EQ, value=42),
        ),
        property=Property(expression="bad", negate=True),
        analysis=AnalysisDirective(
            engine="z3-spacer",
            timeout=5.0,
            havoc_registers=frozenset([3, 5]),
            extra_options={"k": "v"},
        ),
    )
    obj = spec.to_jsonable()
    rebuilt = RiscvBtor2Spec.from_jsonable(obj)
    assert rebuilt.scope.entry_function == "main"
    assert rebuilt.scope.included_callees == ("foo",)
    assert rebuilt.observables[0] == RegisterAt(register=10, pc=0x1000)
    assert rebuilt.assumptions[0] == RegisterInit(register=2, op=Comparison.EQ, value=0)
    assert rebuilt.property.negate
    assert rebuilt.analysis.havoc_registers == frozenset([3, 5])


def test_spec_hash_changes_with_field():
    s1 = RiscvBtor2Spec(
        binary=BinaryRef(path="a"), scope=AnalysisScope(entry_function="m")
    )
    s2 = RiscvBtor2Spec(
        binary=BinaryRef(path="b"), scope=AnalysisScope(entry_function="m")
    )
    assert s1.spec_hash() != s2.spec_hash()
