"""wasm-btor2 spec language.

Defines ``WasmBtor2Spec`` (a ``BaseSpec`` subclass) and the pair-
specific observable / assumption / property / directive types listed in
SCHEMA.md v1.0.0. The structural validator below is registered as the
pair's ``SpecValidator`` and emits diagnostics for malformed specs
without compiling.
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


PAIR_ID = "wasm-btor2"


# ---------------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------------


class Comparison(str, enum.Enum):
    EQ = "eq"
    NE = "ne"
    LT = "lt"    # signed less-than
    LE = "le"    # signed less-or-equal
    GT = "gt"    # signed greater-than
    GE = "ge"    # signed greater-or-equal
    LTU = "ltu"  # unsigned less-than
    LEU = "leu"  # unsigned less-or-equal
    GTU = "gtu"  # unsigned greater-than
    GEU = "geu"  # unsigned greater-or-equal


# ---------------------------------------------------------------------------
# Source references
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WasmModuleRef:
    """Reference to a WebAssembly module binary plus optional content hash.

    ``path``: path to the ``.wasm`` binary on disk.
    ``content_hash``: optional SHA-256 hex digest for cache validation.
    """

    path: str
    content_hash: str | None = None


@dataclass(frozen=True)
class AnalysisScope:
    """Entry point and callee inclusion set for a single-module analysis.

    ``entry_function``: exported function name that begins execution; must
    be an export of kind ``func`` in the module.
    ``included_callees``: additional exported function names inlined into
    the dispatch table. All other callees are self-looped per SCHEMA.md §3.
    """

    entry_function: str = ""
    included_callees: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Observables
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LocalAt(BaseObservable):
    """Value of a local variable at a given execution step.

    ``func_idx``: 0-indexed function index in the module (matches the
    WASM binary's function section order, counting imports).
    ``local_idx``: 0-indexed local index within that function's frame
    (parameters come first per the WASM spec).
    ``step``: 0-indexed cycle number.
    """

    func_idx: int
    local_idx: int
    step: int


@dataclass(frozen=True)
class GlobalAt(BaseObservable):
    """Value of a mutable global at a given execution step.

    ``global_idx``: 0-indexed module global index (imports count first).
    ``step``: 0-indexed cycle number.
    """

    global_idx: int
    step: int


@dataclass(frozen=True)
class MemoryByteAt(BaseObservable):
    """Single byte from linear memory at a given step.

    ``address``: byte address in the range 0..2^32-1.
    ``step``: 0-indexed cycle number.
    """

    address: int
    step: int


@dataclass(frozen=True)
class StackDepthAt(BaseObservable):
    """Number of values on the operand stack at a given step.

    Useful for asserting stack discipline invariants and reasoning about
    the value stack model's bounds.
    ``step``: 0-indexed cycle number.
    """

    step: int


# ---------------------------------------------------------------------------
# Assumptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LocalInit(BaseAssumption):
    """Constraint on a local variable's value at step 0 (function entry).

    WASM locals are zero-initialized by the spec; this tightens or pins
    one to a non-default value for bounded analysis.
    ``func_idx``, ``local_idx``: as in ``LocalAt``.
    """

    func_idx: int
    local_idx: int
    op: Comparison
    value: int


@dataclass(frozen=True)
class GlobalInit(BaseAssumption):
    """Constraint on a mutable global's initial value.

    Tightens or replaces the global's module-level constant initializer.
    ``global_idx``: 0-indexed (imports first).
    """

    global_idx: int
    op: Comparison
    value: int


@dataclass(frozen=True)
class MemoryInit(BaseAssumption):
    """Constraint on initial linear memory contents at a given address.

    ``address``: byte address.
    ``width``: access width in bytes — must be 1, 2, 4, or 8.
    ``op``: comparison relation applied to the little-endian integer value.
    ``value``: integer value to compare against.
    """

    address: int
    width: int
    op: Comparison
    value: int


@dataclass(frozen=True)
class ImportFixed(BaseAssumption):
    """Pin a host-import's return value to a constant (Free binding override).

    ``import_module`` and ``import_name`` identify the import by its
    two-level name as declared in the module's import section.
    ``value``: constant integer return value (single i32 or i64 result;
    multi-value returns are deferred to a future schema bump).
    """

    import_module: str
    import_name: str
    value: int


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------


class PropertyKind(str, enum.Enum):
    """Discriminant for the WASM property being checked.

    REACH_TRAP      — module traps within ``bound`` steps (P1).
    REACH_HOST_CALL — module invokes a host import with args matching
                      ``predicate`` within ``bound`` steps (P1).
    REACH_MEMORY    — linear memory or a global satisfies a
                      ``predicate`` at some step (post-P1).
    SAFETY          — an invariant expressed in ``predicate`` holds at
                      every step; requires a k-induction engine (P10+).
    """

    REACH_TRAP = "reach_trap"
    REACH_HOST_CALL = "reach_host_call"
    REACH_MEMORY = "reach_memory"
    SAFETY = "safety"


@dataclass(frozen=True)
class QuestionSpec(BaseProperty):
    """The property being asked of the WASM module.

    ``kind`` discriminates the property shape (see ``PropertyKind``).
    ``predicate``: opaque string parsed by the translator for kinds other
    than ``REACH_TRAP``; the canonical empty string for ``REACH_TRAP``.
    ``negate``: flips the polarity for synthesis or reachability of the
    complement.
    """

    kind: PropertyKind = PropertyKind.REACH_TRAP
    predicate: str = ""
    negate: bool = False


# ---------------------------------------------------------------------------
# Analysis directive
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisDirective(BaseAnalysisDirective):
    """Solver-selection and resource parameters.

    Inherits ``engine``, ``bound``, and ``timeout`` from
    ``BaseAnalysisDirective``.
    ``extra_options``: engine-specific flags (e.g. z3 tactic tuning)
    as key-value string pairs.
    """

    extra_options: Mapping[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WasmBtor2Spec(BaseSpec):
    """Top-level question spec for the wasm-btor2 pair.

    A frozen, hashable record capturing the complete analysis question:
    which module, which scope, which observables to record, which
    assumptions hold, what property to check, and how to dispatch to
    the solver. Conforms to SCHEMA.md v1.0.0.
    """

    pair = PAIR_ID
    module: WasmModuleRef = WasmModuleRef(path="")
    scope: AnalysisScope = field(default_factory=AnalysisScope)
    observables: tuple[BaseObservable, ...] = ()
    assumptions: tuple[BaseAssumption, ...] = ()
    question: QuestionSpec = field(default_factory=QuestionSpec)
    analysis: AnalysisDirective = AnalysisDirective(engine="z3-bmc")

    # ----- JSON round-trip -----

    @classmethod
    def from_jsonable(cls, obj: Mapping[str, Any]) -> "WasmBtor2Spec":
        if obj.get("pair") != PAIR_ID:
            raise ValueError(f"not a {PAIR_ID} spec: pair={obj.get('pair')!r}")
        f = obj.get("fields", {})
        module = _module_from(f.get("module"))
        scope = _scope_from(f.get("scope"))
        observables = tuple(_obs_from(o) for o in f.get("observables", []))
        assumptions = tuple(_asm_from(a) for a in f.get("assumptions", []))
        question = _question_from(f.get("question"))
        analysis = _analysis_from(f.get("analysis"))
        return cls(
            module=module,
            scope=scope,
            observables=observables,
            assumptions=assumptions,
            question=question,
            analysis=analysis,
        )


# ---------- per-component decoders ----------


def _module_from(obj: Any) -> WasmModuleRef:
    if obj is None:
        return WasmModuleRef(path="")
    return WasmModuleRef(
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


def _obs_from(obj: Any) -> BaseObservable:
    t = obj.get("__type__", "")
    if t == "LocalAt":
        return LocalAt(
            func_idx=int(obj["func_idx"]),
            local_idx=int(obj["local_idx"]),
            step=int(obj["step"]),
        )
    if t == "GlobalAt":
        return GlobalAt(global_idx=int(obj["global_idx"]), step=int(obj["step"]))
    if t == "MemoryByteAt":
        return MemoryByteAt(address=int(obj["address"]), step=int(obj["step"]))
    if t == "StackDepthAt":
        return StackDepthAt(step=int(obj["step"]))
    raise ValueError(f"unknown observable type {t!r}")


def _asm_from(obj: Any) -> BaseAssumption:
    t = obj.get("__type__", "")
    if t == "LocalInit":
        return LocalInit(
            func_idx=int(obj["func_idx"]),
            local_idx=int(obj["local_idx"]),
            op=Comparison(obj["op"]),
            value=int(obj["value"]),
        )
    if t == "GlobalInit":
        return GlobalInit(
            global_idx=int(obj["global_idx"]),
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
    if t == "ImportFixed":
        return ImportFixed(
            import_module=obj["import_module"],
            import_name=obj["import_name"],
            value=int(obj["value"]),
        )
    raise ValueError(f"unknown assumption type {t!r}")


def _question_from(obj: Any) -> QuestionSpec:
    if obj is None:
        return QuestionSpec()
    return QuestionSpec(
        kind=PropertyKind(obj.get("kind", PropertyKind.REACH_TRAP.value)),
        predicate=obj.get("predicate", ""),
        negate=bool(obj.get("negate", False)),
    )


def _analysis_from(obj: Any) -> AnalysisDirective:
    if obj is None:
        return AnalysisDirective(engine="z3-bmc")
    extras = dict(obj.get("extra_options", {}))
    return AnalysisDirective(
        engine=obj.get("engine", "z3-bmc"),
        bound=obj.get("bound"),
        timeout=obj.get("timeout"),
        extra_options=extras,
    )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _err(code: str, msg: str, **detail) -> Diagnostic:
    return Diagnostic(Severity.ERROR, f"wasm-btor2/spec/{code}", msg, detail=detail or None)


def validate_wasm_btor2_spec(spec: WasmBtor2Spec, source: Any = None) -> Iterable[Diagnostic]:
    """Structural validator for ``WasmBtor2Spec``. Does not compile.

    ``source`` is an optional ``WasmSource`` (available from P2 onward);
    when present it validates that the entry function is exported and that
    included callees resolve to real function names. Pass ``None`` (the
    default) for schema-only validation before the source layer lands.
    """
    diags: list[Diagnostic] = []

    if not isinstance(spec, WasmBtor2Spec):
        diags.append(_err("0001", "spec is not a WasmBtor2Spec"))
        return diags

    if not spec.module.path:
        diags.append(_err("0002", "module.path is empty"))

    if not spec.scope.entry_function:
        diags.append(_err("0003", "scope.entry_function is empty"))
    elif source is not None:
        if hasattr(source, "export") and source.export(spec.scope.entry_function) is None:
            diags.append(
                _err(
                    "0004",
                    f"scope.entry_function {spec.scope.entry_function!r} "
                    "not found in module exports",
                )
            )
        for callee in spec.scope.included_callees:
            if hasattr(source, "export") and source.export(callee) is None:
                diags.append(
                    _err(
                        "0005",
                        f"included callee {callee!r} not found in module exports",
                    )
                )

    for obs in spec.observables:
        if isinstance(obs, LocalAt):
            if obs.func_idx < 0:
                diags.append(_err("0010", f"func_idx must be non-negative: {obs.func_idx}"))
            if obs.local_idx < 0:
                diags.append(_err("0011", f"local_idx must be non-negative: {obs.local_idx}"))
        if isinstance(obs, (LocalAt, GlobalAt, MemoryByteAt, StackDepthAt)):
            if obs.step < 0:
                diags.append(_err("0012", f"step must be non-negative: {obs.step}"))
        if isinstance(obs, GlobalAt):
            if obs.global_idx < 0:
                diags.append(_err("0013", f"global_idx must be non-negative: {obs.global_idx}"))
        if isinstance(obs, MemoryByteAt):
            if obs.address < 0:
                diags.append(_err("0014", f"address must be non-negative: {obs.address}"))

    for asm in spec.assumptions:
        if isinstance(asm, LocalInit):
            if asm.func_idx < 0:
                diags.append(_err("0020", f"LocalInit.func_idx must be non-negative: {asm.func_idx}"))
            if asm.local_idx < 0:
                diags.append(_err("0021", f"LocalInit.local_idx must be non-negative: {asm.local_idx}"))
        elif isinstance(asm, GlobalInit):
            if asm.global_idx < 0:
                diags.append(_err("0022", f"GlobalInit.global_idx must be non-negative: {asm.global_idx}"))
        elif isinstance(asm, MemoryInit):
            if asm.address < 0:
                diags.append(_err("0023", f"MemoryInit.address must be non-negative: {asm.address}"))
            if asm.width not in (1, 2, 4, 8):
                diags.append(_err("0024", f"MemoryInit.width must be 1/2/4/8, got {asm.width}"))

    if spec.analysis.bound is not None and spec.analysis.bound < 0:
        diags.append(_err("0030", "AnalysisDirective.bound must be non-negative"))

    if spec.analysis.timeout is not None and spec.analysis.timeout <= 0:
        diags.append(_err("0031", "AnalysisDirective.timeout must be positive"))

    return diags


__all__ = [
    "PAIR_ID",
    "Comparison",
    "WasmModuleRef",
    "AnalysisScope",
    "LocalAt",
    "GlobalAt",
    "MemoryByteAt",
    "StackDepthAt",
    "LocalInit",
    "GlobalInit",
    "MemoryInit",
    "ImportFixed",
    "PropertyKind",
    "QuestionSpec",
    "AnalysisDirective",
    "WasmBtor2Spec",
    "validate_wasm_btor2_spec",
]
