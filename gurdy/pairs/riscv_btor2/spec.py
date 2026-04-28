"""riscv-btor2 spec language.

Defines ``RiscvBtor2Spec`` (a ``BaseSpec`` subclass) and the pair-
specific observable / assumption / property / directive types listed
in PLAN.md. The structural validator below is registered as the
pair's ``SpecValidator`` and emits diagnostics for malformed specs
without compiling.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from gurdy.core.diagnostics import Diagnostic, Severity
from gurdy.core.spec.base import (
    BaseAnalysisDirective,
    BaseAssumption,
    BaseObservable,
    BaseProperty,
    BaseSpec,
)


PAIR_ID = "riscv-btor2"


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
    """Reference to the RV64 ELF on disk plus optional content hash."""

    path: str
    content_hash: str | None = None


@dataclass(frozen=True)
class AnalysisScope:
    """Which functions to inline.

    ``entry_function``: name of the entry function (must be present
    as an STT_FUNC symbol). ``included_callees``: a tuple of function
    names also inlined into the dispatch table; everything else is
    out of scope and self-loops per SCHEMA.md.
    """

    entry_function: str = ""
    included_callees: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Observables
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisterAt(BaseObservable):
    register: int
    pc: int


@dataclass(frozen=True)
class MemoryAt(BaseObservable):
    address: int
    width: int  # bytes
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
    register: int
    op: Comparison
    value: int


@dataclass(frozen=True)
class MemoryInit(BaseAssumption):
    address: int
    width: int  # bytes
    op: Comparison
    value: int


@dataclass(frozen=True)
class CycleInvariant(BaseAssumption):
    """A constraint added at every cycle. ``expression`` is a
    pair-specific symbolic expression encoded as a string the
    translator parses; the framework treats it as opaque."""

    expression: str
    provenance: str = ""


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
    excluded_pc_ranges: tuple[tuple[int, int], ...] = ()


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Property(BaseProperty):
    """The bad expression. ``negate`` flips polarity (synthesis).
    ``expression`` is parsed by the translator the same way as a
    CycleInvariant's expression."""

    expression: str
    negate: bool = False


# ---------------------------------------------------------------------------
# Analysis directive
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisDirective(BaseAnalysisDirective):
    havoc_registers: frozenset[int] = field(default_factory=frozenset)
    extra_options: Mapping[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiscvBtor2Spec(BaseSpec):
    pair = PAIR_ID
    binary: BinaryRef = BinaryRef(path="")
    scope: AnalysisScope = field(default_factory=AnalysisScope)
    entry: EntryAssumptions = field(default_factory=EntryAssumptions)
    observables: tuple[BaseObservable, ...] = ()
    assumptions: tuple[BaseAssumption, ...] = ()
    learned: tuple[LearnedFact, ...] = ()
    property: Property = Property(expression="false")
    analysis: AnalysisDirective = AnalysisDirective(engine="z3-bmc")

    # ----- JSON round-trip -----

    @classmethod
    def from_jsonable(cls, obj: Mapping[str, Any]) -> "RiscvBtor2Spec":
        if obj.get("pair") != PAIR_ID:
            raise ValueError(f"not a {PAIR_ID} spec: pair={obj.get('pair')!r}")
        f = obj.get("fields", {})
        binary = _binary_from(f.get("binary"))
        scope = _scope_from(f.get("scope"))
        entry = _entry_from(f.get("entry"))
        observables = tuple(_obs_from(o) for o in f.get("observables", []))
        assumptions = tuple(_asm_from(a) for a in f.get("assumptions", []))
        learned = tuple(_learned_from(l) for l in f.get("learned", []))
        prop = _prop_from(f.get("property"))
        analysis = _analysis_from(f.get("analysis"))
        return cls(
            binary=binary,
            scope=scope,
            entry=entry,
            observables=observables,
            assumptions=assumptions,
            learned=learned,
            property=prop,
            analysis=analysis,
        )


# ---------- per-component decoders ----------


def _binary_from(obj: Any) -> BinaryRef:
    if obj is None:
        return BinaryRef(path="")
    return BinaryRef(
        path=obj.get("path", ""),
        content_hash=obj.get("content_hash"),
    )


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
    ranges = tuple(
        (int(r[0]), int(r[1])) for r in obj.get("excluded_pc_ranges", [])
    )
    return EntryAssumptions(excluded_pc_ranges=ranges)


def _obs_from(obj: Any) -> BaseObservable:
    t = obj.get("__type__", "")
    if t == "RegisterAt":
        return RegisterAt(register=int(obj["register"]), pc=int(obj["pc"]))
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
    # to_jsonable encodes frozensets as ["__set__", v1, v2, ...].
    if isinstance(havoc_raw, list) and havoc_raw and havoc_raw[0] == "__set__":
        havoc_raw = havoc_raw[1:]
    havoc = frozenset(int(r) for r in havoc_raw)
    extras = dict(obj.get("extra_options", {}))
    return AnalysisDirective(
        engine=obj.get("engine", "z3-bmc"),
        bound=obj.get("bound"),
        timeout=obj.get("timeout"),
        havoc_registers=havoc,
        extra_options=extras,
    )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _err(code: str, msg: str, **detail) -> Diagnostic:
    return Diagnostic(Severity.ERROR, f"riscv-btor2/spec/{code}", msg, detail=detail or None)


def validate_riscv_btor2_spec(spec: RiscvBtor2Spec, source) -> Iterable[Diagnostic]:
    """Structural validator. Does not compile.

    ``source`` is a ``RISCVSource``; we use it to validate that the
    entry function exists and that included callees are real symbols.
    """
    diags: list[Diagnostic] = []

    if not isinstance(spec, RiscvBtor2Spec):
        diags.append(_err("0001", "spec is not a RiscvBtor2Spec"))
        return diags

    if not spec.binary.path:
        diags.append(_err("0002", "binary.path is empty"))

    if not spec.scope.entry_function:
        diags.append(_err("0003", "scope.entry_function is empty"))
    elif source is not None:
        fn = None
        if hasattr(source, "function"):
            fn = source.function(spec.scope.entry_function)
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
            if not 0 <= obs.register < 32:
                diags.append(
                    _err("0010", f"RegisterAt.register out of range: {obs.register}")
                )
        elif isinstance(obs, MemoryAt):
            if obs.width not in (1, 2, 4, 8):
                diags.append(
                    _err(
                        "0011",
                        f"MemoryAt.width must be 1/2/4/8, got {obs.width}",
                    )
                )

    for asm in spec.assumptions:
        if isinstance(asm, RegisterInit):
            if not 0 <= asm.register < 32:
                diags.append(
                    _err(
                        "0020",
                        f"RegisterInit.register out of range: {asm.register}",
                    )
                )
        elif isinstance(asm, MemoryInit):
            if asm.width not in (1, 2, 4, 8):
                diags.append(
                    _err(
                        "0021",
                        f"MemoryInit.width must be 1/2/4/8, got {asm.width}",
                    )
                )

    for r in spec.analysis.havoc_registers:
        if not 0 <= r < 32:
            diags.append(
                _err("0030", f"AnalysisDirective.havoc_registers entry out of range: {r}")
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
    "MemoryAt",
    "PCAtStep",
    "Executed",
    "RegisterInit",
    "MemoryInit",
    "CycleInvariant",
    "LearnedFact",
    "EntryAssumptions",
    "Property",
    "AnalysisDirective",
    "RiscvBtor2Spec",
    "validate_riscv_btor2_spec",
]
