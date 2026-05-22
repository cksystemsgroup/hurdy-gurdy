"""ebpf-btor2 spec language.

Defines ``EbpfBtor2Spec`` and the pair-specific observable / assumption /
property / directive types. Covers the P1 subset: ALU64, branch, exit.
Load/store, helper calls, and maps are added in later schema bumps.
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


PAIR_ID = "ebpf-btor2"

# eBPF has 11 registers r0–r10; r10 is the read-only stack pointer.
_NUM_REGS = 11


# ---------------------------------------------------------------------------
# Source reference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EbpfProgramRef:
    """Reference to an eBPF program as a path to a compiled .bpf.o object.

    ``entry_offset``: byte offset of the entry instruction within the
    .bpf.o's ``maps``/``progs`` section (0 = first instruction of the
    named prog section).
    ``prog_section``: ELF section name holding the bytecode; defaults to
    the first ``SEC("...")`` section found.
    """

    path: str
    content_hash: str | None = None
    prog_section: str = ""
    entry_offset: int = 0


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EbpfScope:
    """What the translator and verifier should analyse.

    ``max_insns``: upper bound on the number of instructions to unroll
    (BMC bound). The kernel verifier uses 1 000 000; start smaller.
    ``prog_type``: eBPF program type string (e.g. ``"socket_filter"``).
    Used by the kernel-verifier baseline adapter to select the correct
    ``BPF_PROG_TYPE_*`` constant.
    """

    max_insns: int = 4096
    prog_type: str = "socket_filter"


# ---------------------------------------------------------------------------
# Observables
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisterAt(BaseObservable):
    """Value of register ``reg`` after instruction at ``insn_idx``."""

    reg: int
    insn_idx: int


@dataclass(frozen=True)
class ExitReached(BaseObservable):
    """Whether the program reaches its BPF_EXIT_INSN."""

    insn_idx: int


# ---------------------------------------------------------------------------
# Assumptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisterBound(BaseAssumption):
    """Initial bound on register ``reg``: ``value_lo <= reg <= value_hi``."""

    reg: int
    value_lo: int
    value_hi: int


@dataclass(frozen=True)
class PacketBound(BaseAssumption):
    """Constrain packet length: ``len_lo <= packet_len <= len_hi``.

    Deferred to P10 (packet/context memory model); present in the spec
    language from P1 so specs written early remain forward-compatible.
    """

    len_lo: int
    len_hi: int


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Property(BaseProperty):
    """Bad-state expression for the BTOR2 ``bad`` node.

    ``expression``: pair-specific symbolic expression the translator
    parses. ``negate`` flips polarity (used for synthesis / dual-role).
    """

    expression: str
    negate: bool = False


# ---------------------------------------------------------------------------
# Analysis directive
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisDirective(BaseAnalysisDirective):
    pass


# ---------------------------------------------------------------------------
# Top-level spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EbpfBtor2Spec(BaseSpec):
    pair = PAIR_ID

    program: EbpfProgramRef = field(default_factory=lambda: EbpfProgramRef(path=""))
    scope: EbpfScope = field(default_factory=EbpfScope)
    observables: tuple[BaseObservable, ...] = ()
    assumptions: tuple[BaseAssumption, ...] = ()
    property: Property = field(default_factory=lambda: Property(expression="false"))
    analysis: AnalysisDirective = field(
        default_factory=lambda: AnalysisDirective(engine="z3-bmc")
    )

    @classmethod
    def from_jsonable(cls, obj: Mapping[str, Any]) -> "EbpfBtor2Spec":
        if obj.get("pair") != PAIR_ID:
            raise ValueError(f"not a {PAIR_ID} spec: pair={obj.get('pair')!r}")
        f = obj.get("fields", {})
        program = _program_from(f.get("program"))
        scope = _scope_from(f.get("scope"))
        observables = tuple(_obs_from(o) for o in f.get("observables", []))
        assumptions = tuple(_asm_from(a) for a in f.get("assumptions", []))
        prop = _prop_from(f.get("property"))
        analysis = _analysis_from(f.get("analysis"))
        return cls(
            program=program,
            scope=scope,
            observables=observables,
            assumptions=assumptions,
            property=prop,
            analysis=analysis,
        )


# ---------------------------------------------------------------------------
# Per-component decoders
# ---------------------------------------------------------------------------


def _program_from(obj: Any) -> EbpfProgramRef:
    if obj is None:
        return EbpfProgramRef(path="")
    return EbpfProgramRef(
        path=obj.get("path", ""),
        content_hash=obj.get("content_hash"),
        prog_section=obj.get("prog_section", ""),
        entry_offset=int(obj.get("entry_offset", 0)),
    )


def _scope_from(obj: Any) -> EbpfScope:
    if obj is None:
        return EbpfScope()
    return EbpfScope(
        max_insns=int(obj.get("max_insns", 4096)),
        prog_type=obj.get("prog_type", "socket_filter"),
    )


def _obs_from(obj: Any) -> BaseObservable:
    t = obj.get("__type__", "")
    if t == "RegisterAt":
        return RegisterAt(reg=int(obj["reg"]), insn_idx=int(obj["insn_idx"]))
    if t == "ExitReached":
        return ExitReached(insn_idx=int(obj["insn_idx"]))
    raise ValueError(f"unknown observable type {t!r}")


def _asm_from(obj: Any) -> BaseAssumption:
    t = obj.get("__type__", "")
    if t == "RegisterBound":
        return RegisterBound(
            reg=int(obj["reg"]),
            value_lo=int(obj["value_lo"]),
            value_hi=int(obj["value_hi"]),
        )
    if t == "PacketBound":
        return PacketBound(
            len_lo=int(obj["len_lo"]),
            len_hi=int(obj["len_hi"]),
        )
    raise ValueError(f"unknown assumption type {t!r}")


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
    return AnalysisDirective(
        engine=obj.get("engine", "z3-bmc"),
        bound=obj.get("bound"),
        timeout=obj.get("timeout"),
    )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _err(code: str, msg: str, **detail) -> Diagnostic:
    return Diagnostic(Severity.ERROR, f"ebpf-btor2/spec/{code}", msg, detail=detail or None)


def validate_ebpf_btor2_spec(spec: EbpfBtor2Spec, source) -> Iterable[Diagnostic]:
    """Structural validator. Does not compile."""
    diags: list[Diagnostic] = []

    if not isinstance(spec, EbpfBtor2Spec):
        diags.append(_err("0001", "spec is not an EbpfBtor2Spec"))
        return diags

    if not spec.program.path:
        diags.append(_err("0002", "program.path is empty"))

    if spec.scope.max_insns <= 0:
        diags.append(_err("0003", f"scope.max_insns must be positive, got {spec.scope.max_insns}"))

    for obs in spec.observables:
        if isinstance(obs, RegisterAt):
            if not 0 <= obs.reg < _NUM_REGS:
                diags.append(_err("0010", f"RegisterAt.reg out of range: {obs.reg}"))
            if obs.insn_idx < 0:
                diags.append(_err("0011", f"RegisterAt.insn_idx must be non-negative"))

    for asm in spec.assumptions:
        if isinstance(asm, RegisterBound):
            if not 0 <= asm.reg < _NUM_REGS:
                diags.append(_err("0020", f"RegisterBound.reg out of range: {asm.reg}"))
            if asm.value_lo > asm.value_hi:
                diags.append(
                    _err("0021", f"RegisterBound: value_lo > value_hi ({asm.value_lo} > {asm.value_hi})")
                )
        elif isinstance(asm, PacketBound):
            if asm.len_lo < 0:
                diags.append(_err("0022", f"PacketBound.len_lo must be non-negative"))
            if asm.len_lo > asm.len_hi:
                diags.append(_err("0023", f"PacketBound: len_lo > len_hi"))

    if spec.analysis.bound is not None and spec.analysis.bound < 0:
        diags.append(_err("0030", "AnalysisDirective.bound must be non-negative"))

    if spec.analysis.timeout is not None and spec.analysis.timeout <= 0:
        diags.append(_err("0031", "AnalysisDirective.timeout must be positive"))

    return diags


__all__ = [
    "PAIR_ID",
    "EbpfProgramRef",
    "EbpfScope",
    "RegisterAt",
    "ExitReached",
    "RegisterBound",
    "PacketBound",
    "Property",
    "AnalysisDirective",
    "EbpfBtor2Spec",
    "validate_ebpf_btor2_spec",
]
