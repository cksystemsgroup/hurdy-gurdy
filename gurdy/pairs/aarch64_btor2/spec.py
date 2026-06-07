"""QuestionSpec for the aarch64-btor2 pair.

Adapted from gurdy/pairs/riscv_btor2/spec.py (v2-bootstrap).
ISA-specific changes vs riscv-btor2:
- 31 GPRs (x0–x30); register 31 is XZR/SP (context-sensitive, no state).
- SP is a separate named field in bindings and assumptions.
- NZCV condition flags exposed as NZCVInit assumption.
- Link-register entry assumption targets x30 (not x1).
- W-register behaviour: zero-extension (not sign-extension).
- SDIV/UDIV div-by-zero → 0 (not -1 / 2^64-1 like RV64).
See SCHEMA.md §14 for the full divergence table.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from gurdy.core.diagnostics import Diagnostic, Severity
from gurdy.core.spec.base import (
    BaseAnalysisDirective,
    BaseAssumption,
    BaseObservable,
    BaseProperty,
    BaseSpec,
)


PAIR_ID = "aarch64-btor2"

# GPR index range: x0–x30 (31 registers). Register 31 is XZR/SP, not a state.
_GPR_COUNT = 31
_VALID_GPR = range(_GPR_COUNT)


# ---------------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------------


class Comparison(str, enum.Enum):
    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    LTU = "ltu"
    LEU = "leu"
    GTU = "gtu"
    GEU = "geu"


# ---------------------------------------------------------------------------
# Source references
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BinaryRef:
    path: str
    content_hash: str | None = None


@dataclass(frozen=True)
class AnalysisScope:
    entry_function: str = ""
    included_callees: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Observables
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisterAt(BaseObservable):
    """Observe GPR x{register} (0–30) at a given PC."""
    register: int
    pc: int


@dataclass(frozen=True)
class SPAt(BaseObservable):
    """Observe the stack pointer at a given PC."""
    pc: int


@dataclass(frozen=True)
class NZCVAt(BaseObservable):
    """Observe the 4-bit NZCV flags at a given PC."""
    pc: int


@dataclass(frozen=True)
class MemoryAt(BaseObservable):
    address: int
    width: int  # bytes; 1, 2, 4, or 8
    pc: int


@dataclass(frozen=True)
class PCAtStep(BaseObservable):
    step: int


@dataclass(frozen=True)
class Executed(BaseObservable):
    pc: int


# ---------------------------------------------------------------------------
# Assumptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisterInit(BaseAssumption):
    """Pin GPR x{register} (0–30) at entry."""
    register: int
    op: Comparison
    value: int


@dataclass(frozen=True)
class SPInit(BaseAssumption):
    """Pin the stack pointer at entry."""
    op: Comparison
    value: int


@dataclass(frozen=True)
class NZCVInit(BaseAssumption):
    """Pin the NZCV flags at entry as a 4-bit value (N=3, Z=2, C=1, V=0)."""
    op: Comparison
    value: int  # 0–15


@dataclass(frozen=True)
class MemoryInit(BaseAssumption):
    address: int
    width: int  # bytes; 1, 2, 4, or 8
    op: Comparison
    value: int


@dataclass(frozen=True)
class CycleInvariant(BaseAssumption):
    """A constraint held at every cycle. ``expression`` is pair-specific
    symbolic syntax parsed by the translator."""
    expression: str
    provenance: str = ""


@dataclass(frozen=True)
class BranchPin(BaseAssumption):
    """Pin a conditional branch's direction at a specific step.
    See SCHEMA.md §5.3 for condition codes and BTOR2 encoding."""
    step: int
    taken: bool
    pc: int


# ---------------------------------------------------------------------------
# Learned facts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LearnedFact:
    expression: str
    source_question_hash: str
    source_engine: str
    validated: bool


# ---------------------------------------------------------------------------
# Entry assumptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntryAssumptions:
    # PC ranges the link register (x30) is constrained to point outside.
    excluded_pc_ranges: tuple[tuple[int, int], ...] = ()


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Property(BaseProperty):
    expression: str
    negate: bool = False


# ---------------------------------------------------------------------------
# Analysis directive
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisDirective(BaseAnalysisDirective):
    # GPR indices 0–30 to havoc. SP havoced separately via havoc_sp.
    havoc_registers: frozenset[int] = field(default_factory=frozenset)
    havoc_sp: bool = False
    extra_options: Mapping[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Aarch64Btor2Spec(BaseSpec):
    pair = PAIR_ID
    binary: BinaryRef = field(default_factory=lambda: BinaryRef(path=""))
    scope: AnalysisScope = field(default_factory=AnalysisScope)
    entry: EntryAssumptions = field(default_factory=EntryAssumptions)
    observables: tuple[BaseObservable, ...] = ()
    assumptions: tuple[BaseAssumption, ...] = ()
    learned: tuple[LearnedFact, ...] = ()
    property: Property = field(default_factory=lambda: Property(expression="false"))
    analysis: AnalysisDirective = field(
        default_factory=lambda: AnalysisDirective(engine="z3-bmc")
    )

    @classmethod
    def from_jsonable(cls, obj: Mapping[str, Any]) -> "Aarch64Btor2Spec":
        if obj.get("pair") != PAIR_ID:
            raise ValueError(f"not a {PAIR_ID} spec: pair={obj.get('pair')!r}")
        f = obj.get("fields", {})
        return cls(
            binary=_binary_from(f.get("binary")),
            scope=_scope_from(f.get("scope")),
            entry=_entry_from(f.get("entry")),
            observables=tuple(_obs_from(o) for o in f.get("observables", [])),
            assumptions=tuple(_asm_from(a) for a in f.get("assumptions", [])),
            learned=tuple(_learned_from(l) for l in f.get("learned", [])),
            property=_prop_from(f.get("property")),
            analysis=_analysis_from(f.get("analysis")),
        )


# ---------- per-component decoders ----------


def _binary_from(obj: Any) -> BinaryRef:
    if obj is None:
        return BinaryRef(path="")
    return BinaryRef(path=obj.get("path", ""), content_hash=obj.get("content_hash"))


def _scope_from(obj: Any) -> AnalysisScope:
    if obj is None:
        return AnalysisScope()
    return AnalysisScope(
        entry_function=obj.get("entry_function", ""),
        included_callees=tuple(obj.get("included_callees", [])),
    )


def _entry_from(obj: Any) -> EntryAssumptions:
    if obj is None:
        return EntryAssumptions()
    return EntryAssumptions(
        excluded_pc_ranges=tuple(
            (int(r[0]), int(r[1])) for r in obj.get("excluded_pc_ranges", [])
        )
    )


def _obs_from(obj: Any) -> BaseObservable:
    t = obj.get("__type__", "")
    if t == "RegisterAt":
        return RegisterAt(register=int(obj["register"]), pc=int(obj["pc"]))
    if t == "SPAt":
        return SPAt(pc=int(obj["pc"]))
    if t == "NZCVAt":
        return NZCVAt(pc=int(obj["pc"]))
    if t == "MemoryAt":
        return MemoryAt(
            address=int(obj["address"]), width=int(obj["width"]), pc=int(obj["pc"])
        )
    if t == "PCAtStep":
        return PCAtStep(step=int(obj["step"]))
    if t == "Executed":
        return Executed(pc=int(obj["pc"]))
    raise ValueError(f"unknown observable type {t!r}")


def _asm_from(obj: Any) -> BaseAssumption:
    t = obj.get("__type__", "")
    if t == "RegisterInit":
        return RegisterInit(
            register=int(obj["register"]),
            op=Comparison(obj["op"]),
            value=int(obj["value"]),
        )
    if t == "SPInit":
        return SPInit(op=Comparison(obj["op"]), value=int(obj["value"]))
    if t == "NZCVInit":
        return NZCVInit(op=Comparison(obj["op"]), value=int(obj["value"]))
    if t == "MemoryInit":
        return MemoryInit(
            address=int(obj["address"]),
            width=int(obj["width"]),
            op=Comparison(obj["op"]),
            value=int(obj["value"]),
        )
    if t == "CycleInvariant":
        return CycleInvariant(
            expression=obj["expression"], provenance=obj.get("provenance", "")
        )
    if t == "BranchPin":
        return BranchPin(
            step=int(obj["step"]), taken=bool(obj["taken"]), pc=int(obj["pc"])
        )
    raise ValueError(f"unknown assumption type {t!r}")


def _learned_from(obj: Any) -> LearnedFact:
    return LearnedFact(
        expression=obj["expression"],
        source_question_hash=obj["source_question_hash"],
        source_engine=obj["source_engine"],
        validated=bool(obj.get("validated", False)),
    )


def _prop_from(obj: Any) -> Property:
    if obj is None:
        return Property(expression="false")
    return Property(
        expression=obj.get("expression", "false"),
        negate=bool(obj.get("negate", False)),
    )


def _analysis_from(obj: Any) -> AnalysisDirective:
    if obj is None:
        return AnalysisDirective(engine="z3-bmc")
    havoc_raw = obj.get("havoc_registers", [])
    if isinstance(havoc_raw, list) and havoc_raw and havoc_raw[0] == "__set__":
        havoc_raw = havoc_raw[1:]
    return AnalysisDirective(
        engine=obj.get("engine", "z3-bmc"),
        bound=obj.get("bound"),
        timeout=obj.get("timeout"),
        havoc_registers=frozenset(int(r) for r in havoc_raw),
        havoc_sp=bool(obj.get("havoc_sp", False)),
        extra_options=dict(obj.get("extra_options", {})),
    )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _err(code: str, msg: str, **detail) -> Diagnostic:
    return Diagnostic(
        Severity.ERROR, f"aarch64-btor2/spec/{code}", msg, detail=detail or None
    )


def validate_aarch64_btor2_spec(
    spec: Aarch64Btor2Spec, source: Any
) -> Iterable[Diagnostic]:
    """Structural validator. Does not compile.

    ``source`` is an ``Aarch64Source``; used to check that entry_function
    and included_callees exist as ELF symbols.
    """
    diags: list[Diagnostic] = []

    if not isinstance(spec, Aarch64Btor2Spec):
        diags.append(_err("0001", "spec is not an Aarch64Btor2Spec"))
        return diags

    if not spec.binary.path:
        diags.append(_err("0002", "binary.path is empty"))

    if not spec.scope.entry_function:
        diags.append(_err("0003", "scope.entry_function is empty"))
    elif source is not None:
        fn = source.function(spec.scope.entry_function) if hasattr(source, "function") else None
        if fn is None:
            diags.append(
                _err(
                    "0004",
                    f"scope.entry_function {spec.scope.entry_function!r} "
                    "not found in binary symbols",
                )
            )
        for callee in spec.scope.included_callees:
            if hasattr(source, "function") and source.function(callee) is None:
                diags.append(
                    _err(
                        "0005",
                        f"included callee {callee!r} not found in binary symbols",
                    )
                )

    for obs in spec.observables:
        if isinstance(obs, RegisterAt):
            if obs.register not in _VALID_GPR:
                diags.append(
                    _err(
                        "0010",
                        f"RegisterAt.register out of range 0–30: {obs.register}",
                    )
                )
        elif isinstance(obs, MemoryAt):
            if obs.width not in (1, 2, 4, 8):
                diags.append(
                    _err("0011", f"MemoryAt.width must be 1/2/4/8, got {obs.width}")
                )
        elif isinstance(obs, NZCVAt):
            pass  # always valid

    for asm in spec.assumptions:
        if isinstance(asm, RegisterInit):
            if asm.register not in _VALID_GPR:
                diags.append(
                    _err(
                        "0020",
                        f"RegisterInit.register out of range 0–30: {asm.register}",
                    )
                )
        elif isinstance(asm, NZCVInit):
            if not 0 <= asm.value <= 15:
                diags.append(
                    _err(
                        "0021",
                        f"NZCVInit.value must be 0–15 (4-bit), got {asm.value}",
                    )
                )
        elif isinstance(asm, MemoryInit):
            if asm.width not in (1, 2, 4, 8):
                diags.append(
                    _err("0022", f"MemoryInit.width must be 1/2/4/8, got {asm.width}")
                )
        elif isinstance(asm, BranchPin):
            if asm.step < 0:
                diags.append(
                    _err("0023", f"BranchPin.step must be non-negative, got {asm.step}")
                )
            if asm.pc < 0:
                diags.append(
                    _err("0024", f"BranchPin.pc must be non-negative, got {asm.pc}")
                )

    for r in spec.analysis.havoc_registers:
        if r not in _VALID_GPR:
            diags.append(
                _err(
                    "0030",
                    f"AnalysisDirective.havoc_registers entry out of range 0–30: {r}",
                )
            )

    if spec.analysis.bound is not None and spec.analysis.bound < 0:
        diags.append(_err("0031", "AnalysisDirective.bound must be non-negative"))

    if spec.analysis.timeout is not None and spec.analysis.timeout <= 0:
        diags.append(_err("0032", "AnalysisDirective.timeout must be positive"))

    return diags


__all__ = [
    "PAIR_ID",
    "Comparison",
    "BinaryRef",
    "AnalysisScope",
    "RegisterAt",
    "SPAt",
    "NZCVAt",
    "MemoryAt",
    "PCAtStep",
    "Executed",
    "RegisterInit",
    "SPInit",
    "NZCVInit",
    "MemoryInit",
    "CycleInvariant",
    "BranchPin",
    "LearnedFact",
    "EntryAssumptions",
    "Property",
    "AnalysisDirective",
    "Aarch64Btor2Spec",
    "validate_aarch64_btor2_spec",
]
