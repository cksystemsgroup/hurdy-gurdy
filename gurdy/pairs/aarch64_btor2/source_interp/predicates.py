"""Concrete evaluation of aarch64-btor2 spec predicates.

Adapted from ``gurdy/pairs/riscv_btor2/source_interp/predicates.py``.
The translator emits BTOR2 fragments for observables, assumptions, and
the property; this module evaluates the *same* spec types against a
concrete ``SourceTrace`` produced by the AArch64 source interpreter.
The two paths share grammar (``translation/exprs.py``) but evaluate to
ints rather than nids.

AArch64-specific changes vs riscv-btor2 (SCHEMA.md §3, §14):

- 31 GPRs (x0–x30); register 31 is XZR/SP and is *not* a GPR state
  variable. The stack pointer is its own state, exposed as ``sp`` in
  expressions and pinned/observed via ``SPInit`` / ``SPAt``.
- NZCV condition flags are a 4-bit state, exposed as ``nzcv`` in
  expressions and pinned/observed via ``NZCVInit`` / ``NZCVAt``.
- The concrete expression evaluator therefore carries ``sp`` and
  ``nzcv`` terminals in addition to the shared ``reg``/``mem``/``pc``
  forms.

A spec predicate falls into one of three buckets:

- **Structured types** (``RegisterAt``, ``SPAt``, ``NZCVAt``,
  ``RegisterInit``, ``Property(expression='true'|'false')``, …) —
  evaluated directly against the trace.
- **String-expression types** (``CycleInvariant``, ``Property`` with a
  non-trivial expression) — evaluated by the small concrete expression
  evaluator below; unsupported sub-forms produce a structured
  "unsupported" diagnostic rather than failing.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from gurdy.core.interp.diagnostics import (
    CODE_ASSUMPTION_UNSUPPORTED,
    CODE_ASSUMPTION_VIOLATED,
    CODE_OBSERVABLE_NEVER_FIRES,
    CODE_PROPERTY_HOLDS_CONCRETELY,
    CODE_PROPERTY_UNSUPPORTED,
    CODE_PROPERTY_VIOLATED_CONCRETELY,
)
from gurdy.core.interp.types import (
    PredicateKind,
    SourceTrace,
    SpecEvaluation,
    SpecPredicateResult,
)
from gurdy.pairs.aarch64_btor2.source_interp.bindings import AArch64InputBinding, Free
from gurdy.pairs.aarch64_btor2.spec import (
    Aarch64Btor2Spec,
    Comparison,
    CycleInvariant,
    Executed,
    MemoryAt,
    MemoryInit,
    NZCVAt,
    NZCVInit,
    PCAtStep,
    Property,
    RegisterAt,
    RegisterInit,
    SPAt,
    SPInit,
)


MASK64 = (1 << 64) - 1
MASK4 = 0xF
_GPR_COUNT = 31  # x0–x30; x31 is XZR/SP, tracked separately as ``sp``.


# ---------------------------------------------------------------------------
# Concrete state extraction
# ---------------------------------------------------------------------------


def _as_int(cell: Any) -> int:
    """Coerce a binding cell to an int. ``Free`` cells collapse to 0.

    The ``check`` tool runs the plain interpreter, which rejects FREE
    fields up front, so a binding that reaches here is concrete. The
    guard is defensive only.
    """
    if isinstance(cell, Free):
        return 0
    return int(cell) & MASK64


def _pre_step_regs(
    trace: SourceTrace, binding: AArch64InputBinding, step: int
) -> tuple[int, ...]:
    """GPR snapshot (x0–x30) *before* step ``step`` executes.

    For step 0 it's the binding's register init layered over zeros.
    For step i > 0 it's the post-step regs of step i-1.
    """
    if step <= 0:
        regs = [0] * _GPR_COUNT
        for r, v in (binding.register_init or {}).items():
            if 0 <= r < _GPR_COUNT:
                regs[r] = _as_int(v)
        return tuple(regs)
    return tuple(trace.steps[step - 1].deltas.get("regs", ()) or ())


def _pre_step_sp(
    trace: SourceTrace, binding: AArch64InputBinding, step: int
) -> int:
    if step <= 0:
        return _as_int(binding.sp_init) if binding.sp_init is not None else 0
    sp = trace.steps[step - 1].deltas.get("sp")
    return int(sp) & MASK64 if sp is not None else 0


def _pre_step_nzcv(
    trace: SourceTrace, binding: AArch64InputBinding, step: int
) -> int:
    if step <= 0:
        return (_as_int(binding.nzcv_init) & MASK4) if binding.nzcv_init is not None else 0
    nz = trace.steps[step - 1].deltas.get("nzcv")
    return int(nz) & MASK4 if nz is not None else 0


def _pre_step_pc(
    trace: SourceTrace, binding: AArch64InputBinding, step: int
) -> int | None:
    if step <= 0:
        return binding.pc
    return trace.steps[step - 1].deltas.get("pc")


# ---------------------------------------------------------------------------
# Concrete expression evaluator (mirrors translation/exprs.py grammar)
# ---------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"\s*([(),]|0x[0-9A-Fa-f]+|-?\d+|[A-Za-z_][A-Za-z_0-9.]*)")


def _tokenize(s: str) -> list[str]:
    out: list[str] = []
    pos = 0
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m:
            if s[pos].isspace():
                pos += 1
                continue
            raise ValueError(f"unexpected character {s[pos]!r} at position {pos}")
        out.append(m.group(1))
        pos = m.end()
    return out


class _UnsupportedExpr(Exception):
    """Raised when the concrete evaluator hits a form it doesn't model."""


class _ConcreteExprEvaluator:
    """Evaluates a spec expression against a concrete machine view.

    The grammar matches ``translation/exprs.py`` (including the AArch64
    ``sp`` and ``nzcv`` terminals) but evaluation targets ints. ``mem``
    is supported only when explicit memory state is provided.
    """

    def __init__(
        self,
        regs: Sequence[int],
        pc: int,
        sp: int = 0,
        nzcv: int = 0,
        mem: Mapping[int, int] | None = None,
    ):
        regs = list(regs)
        if len(regs) < _GPR_COUNT:
            regs = regs + [0] * (_GPR_COUNT - len(regs))
        self.regs = regs
        self.pc = int(pc) & MASK64
        self.sp = int(sp) & MASK64
        self.nzcv = int(nzcv) & MASK4
        self.mem = dict(mem or {})

    def eval(self, expr: str) -> int:
        tokens = _tokenize(expr)
        i = 0

        def parse_expr():
            nonlocal i
            t = tokens[i]; i += 1
            if t == "true":
                return 1
            if t == "false":
                return 0
            if t == "pc":
                return self.pc
            if t == "sp":
                return self.sp
            if t == "nzcv":
                return self.nzcv
            if t.startswith("0x"):
                return int(t, 16) & MASK64
            if t.lstrip("-").isdigit():
                return int(t) & MASK64
            if i >= len(tokens) or tokens[i] != "(":
                raise _UnsupportedExpr(f"bare identifier {t!r}")
            i += 1
            args = []
            while tokens[i] != ")":
                args.append(parse_expr())
                if tokens[i] == ",":
                    i += 1
            i += 1
            return apply(t, args)

        def apply(name, args):
            if name == "reg" and len(args) == 1:
                idx = args[0]
                if 0 <= idx < _GPR_COUNT:
                    return self.regs[idx] & MASK64
                raise _UnsupportedExpr(f"reg({idx}) out of range 0–30")
            if name == "const" and len(args) == 1:
                return args[0] & MASK64
            if name == "mem" and len(args) == 2:
                addr, width = args
                v = 0
                for k in range(width):
                    v |= (self.mem.get(addr + k, 0) & 0xFF) << (8 * k)
                return v & ((1 << (8 * width)) - 1)
            if name == "eq" and len(args) == 2:
                return 1 if args[0] == args[1] else 0
            if name == "neq" and len(args) == 2:
                return 0 if args[0] == args[1] else 1
            if name == "ltu" and len(args) == 2:
                return 1 if args[0] < args[1] else 0
            if name == "leu" and len(args) == 2:
                return 1 if args[0] <= args[1] else 0
            if name == "gtu" and len(args) == 2:
                return 1 if args[0] > args[1] else 0
            if name == "geu" and len(args) == 2:
                return 1 if args[0] >= args[1] else 0
            if name == "lt" and len(args) == 2:
                return 1 if _to_signed(args[0]) < _to_signed(args[1]) else 0
            if name == "le" and len(args) == 2:
                return 1 if _to_signed(args[0]) <= _to_signed(args[1]) else 0
            if name == "gt" and len(args) == 2:
                return 1 if _to_signed(args[0]) > _to_signed(args[1]) else 0
            if name == "ge" and len(args) == 2:
                return 1 if _to_signed(args[0]) >= _to_signed(args[1]) else 0
            if name == "add" and len(args) == 2:
                return (args[0] + args[1]) & MASK64
            if name == "sub" and len(args) == 2:
                return (args[0] - args[1]) & MASK64
            if name == "and" and len(args) == 2:
                return args[0] & args[1] & MASK64
            if name == "or" and len(args) == 2:
                return (args[0] | args[1]) & MASK64
            if name == "xor" and len(args) == 2:
                return (args[0] ^ args[1]) & MASK64
            if name == "not" and len(args) == 1:
                return (~args[0]) & MASK64
            raise _UnsupportedExpr(f"{name}/{len(args)}")

        result = parse_expr()
        if i != len(tokens):
            raise _UnsupportedExpr(f"trailing tokens: {tokens[i:]}")
        return result & MASK64


def _to_signed(v: int) -> int:
    v &= MASK64
    return v - (1 << 64) if v & (1 << 63) else v


def _eval_at(
    trace: SourceTrace, binding: AArch64InputBinding, step: int, expr: str
) -> int:
    """Evaluate ``expr`` against the pre-state of ``step``."""
    regs = _pre_step_regs(trace, binding, step)
    pc = _pre_step_pc(trace, binding, step)
    sp = _pre_step_sp(trace, binding, step)
    nzcv = _pre_step_nzcv(trace, binding, step)
    return _ConcreteExprEvaluator(regs, pc or 0, sp, nzcv).eval(expr)


# ---------------------------------------------------------------------------
# Comparison helper for RegisterInit / SPInit / NZCVInit / MemoryInit
# ---------------------------------------------------------------------------


def _cmp(actual: int, op: Comparison, target: int, mask: int = MASK64) -> bool:
    actual &= mask
    target &= mask
    if op == Comparison.EQ:
        return actual == target
    if op == Comparison.NE:
        return actual != target
    if op == Comparison.LTU:
        return actual < target
    if op == Comparison.LEU:
        return actual <= target
    if op == Comparison.GTU:
        return actual > target
    if op == Comparison.GEU:
        return actual >= target
    a = _to_signed(actual) if mask == MASK64 else actual
    t = _to_signed(target) if mask == MASK64 else target
    if op == Comparison.LT:
        return a < t
    if op == Comparison.LE:
        return a <= t
    if op == Comparison.GT:
        return a > t
    if op == Comparison.GE:
        return a >= t
    return False


# ---------------------------------------------------------------------------
# Predicate evaluators
# ---------------------------------------------------------------------------


def evaluate_observable(
    obs, trace: SourceTrace, binding: AArch64InputBinding
) -> SpecPredicateResult:
    if isinstance(obs, RegisterAt):
        values: list[tuple[int, Any]] = []
        for i, step in enumerate(trace.steps):
            pc = (step.location or {}).get("pc")
            if pc == obs.pc:
                regs = _pre_step_regs(trace, binding, i)
                if 0 <= obs.register < len(regs):
                    values.append((i, int(regs[obs.register])))
        return SpecPredicateResult(
            name=f"RegisterAt(x{obs.register}@0x{obs.pc:x})",
            kind=PredicateKind.OBSERVABLE,
            fired=bool(values),
            values=tuple(values),
        )
    if isinstance(obs, SPAt):
        values = []
        for i, step in enumerate(trace.steps):
            if (step.location or {}).get("pc") == obs.pc:
                values.append((i, _pre_step_sp(trace, binding, i)))
        return SpecPredicateResult(
            name=f"SPAt(0x{obs.pc:x})",
            kind=PredicateKind.OBSERVABLE,
            fired=bool(values),
            values=tuple(values),
        )
    if isinstance(obs, NZCVAt):
        values = []
        for i, step in enumerate(trace.steps):
            if (step.location or {}).get("pc") == obs.pc:
                values.append((i, _pre_step_nzcv(trace, binding, i)))
        return SpecPredicateResult(
            name=f"NZCVAt(0x{obs.pc:x})",
            kind=PredicateKind.OBSERVABLE,
            fired=bool(values),
            values=tuple(values),
        )
    if isinstance(obs, PCAtStep):
        if 0 <= obs.step < len(trace.steps):
            pc = (trace.steps[obs.step].location or {}).get("pc")
            return SpecPredicateResult(
                name=f"PCAtStep({obs.step})",
                kind=PredicateKind.OBSERVABLE,
                fired=True,
                values=((obs.step, pc),),
            )
        return SpecPredicateResult(
            name=f"PCAtStep({obs.step})",
            kind=PredicateKind.OBSERVABLE,
            fired=False,
            note="step beyond trace bound",
        )
    if isinstance(obs, Executed):
        visited = [
            (i, (step.location or {}).get("pc"))
            for i, step in enumerate(trace.steps)
            if (step.location or {}).get("pc") == obs.pc
        ]
        return SpecPredicateResult(
            name=f"Executed(0x{obs.pc:x})",
            kind=PredicateKind.OBSERVABLE,
            fired=bool(visited),
            values=tuple(visited),
        )
    if isinstance(obs, MemoryAt):
        return SpecPredicateResult(
            name=f"MemoryAt(0x{obs.address:x},{obs.width})",
            kind=PredicateKind.OBSERVABLE,
            fired=False,
            note="memory observables not yet supported in concrete check",
        )
    return SpecPredicateResult(
        name=type(obs).__name__,
        kind=PredicateKind.OBSERVABLE,
        fired=False,
        note=f"unsupported observable type: {type(obs).__name__}",
    )


def evaluate_assumption(
    asm, trace: SourceTrace, binding: AArch64InputBinding
) -> SpecPredicateResult:
    if isinstance(asm, RegisterInit):
        actual = _as_int((binding.register_init or {}).get(asm.register, 0))
        held = _cmp(actual, asm.op, asm.value)
        return SpecPredicateResult(
            name=f"RegisterInit(x{asm.register} {asm.op.value} {asm.value})",
            kind=PredicateKind.ASSUMPTION,
            holds=held,
            violations=() if held else (0,),
            note=None if held else f"actual={actual}",
        )
    if isinstance(asm, SPInit):
        actual = _as_int(binding.sp_init) if binding.sp_init is not None else 0
        held = _cmp(actual, asm.op, asm.value)
        return SpecPredicateResult(
            name=f"SPInit({asm.op.value} {asm.value})",
            kind=PredicateKind.ASSUMPTION,
            holds=held,
            violations=() if held else (0,),
            note=None if held else f"actual={actual}",
        )
    if isinstance(asm, NZCVInit):
        actual = (_as_int(binding.nzcv_init) & MASK4) if binding.nzcv_init is not None else 0
        held = _cmp(actual, asm.op, asm.value, mask=MASK4)
        return SpecPredicateResult(
            name=f"NZCVInit({asm.op.value} {asm.value})",
            kind=PredicateKind.ASSUMPTION,
            holds=held,
            violations=() if held else (0,),
            note=None if held else f"actual={actual}",
        )
    if isinstance(asm, MemoryInit):
        v = 0
        for k in range(asm.width):
            v |= (_as_int((binding.memory_init or {}).get(asm.address + k, 0)) & 0xFF) << (8 * k)
        held = _cmp(v, asm.op, asm.value)
        return SpecPredicateResult(
            name=f"MemoryInit(0x{asm.address:x}/{asm.width} {asm.op.value} {asm.value})",
            kind=PredicateKind.ASSUMPTION,
            holds=held,
            violations=() if held else (0,),
            note=None if held else f"actual=0x{v:x}",
        )
    if isinstance(asm, CycleInvariant):
        violations: list[int] = []
        for i in range(len(trace.steps) + 1):
            if _pre_step_pc(trace, binding, i) is None:
                continue
            try:
                v = _eval_at(trace, binding, i, asm.expression)
            except _UnsupportedExpr as exc:
                return SpecPredicateResult(
                    name=f"CycleInvariant({asm.expression!r})",
                    kind=PredicateKind.ASSUMPTION,
                    holds=None,
                    note=f"unsupported in concrete check: {exc}",
                )
            if not v:
                violations.append(i)
        return SpecPredicateResult(
            name=f"CycleInvariant({asm.expression!r})",
            kind=PredicateKind.ASSUMPTION,
            holds=not violations,
            violations=tuple(violations),
        )
    return SpecPredicateResult(
        name=type(asm).__name__,
        kind=PredicateKind.ASSUMPTION,
        holds=None,
        note=f"unsupported assumption type: {type(asm).__name__}",
    )


def evaluate_property(
    prop: Property, trace: SourceTrace, binding: AArch64InputBinding
) -> SpecPredicateResult:
    expr = prop.expression.strip()
    if expr == "false":
        return SpecPredicateResult(
            name="property",
            kind=PredicateKind.PROPERTY,
            holds=True,
            note="bad-expression is constant false",
        )
    if expr == "true":
        return SpecPredicateResult(
            name="property",
            kind=PredicateKind.PROPERTY,
            holds=False,
            violations=(0,),
            note="bad-expression is constant true",
        )

    fires_at: list[int] = []
    for i in range(len(trace.steps) + 1):
        if _pre_step_pc(trace, binding, i) is None:
            continue
        try:
            v = _eval_at(trace, binding, i, expr)
        except _UnsupportedExpr as exc:
            return SpecPredicateResult(
                name="property",
                kind=PredicateKind.PROPERTY,
                holds=None,
                note=f"unsupported in concrete check: {exc}",
            )
        if v:
            fires_at.append(i)

    polarity = "negated" if prop.negate else "direct"
    if prop.negate:
        # Negated: the bad fires where the expression is *false*, so the
        # violations are the steps the expression does not hold.
        all_steps = [
            s for s in range(len(trace.steps) + 1)
            if _pre_step_pc(trace, binding, s) is not None
        ]
        held_steps = [s for s in all_steps if s not in fires_at]
        return SpecPredicateResult(
            name="property",
            kind=PredicateKind.PROPERTY,
            holds=not held_steps,
            violations=tuple(held_steps),
            note=f"polarity={polarity}",
        )
    return SpecPredicateResult(
        name="property",
        kind=PredicateKind.PROPERTY,
        holds=not fires_at,
        violations=tuple(fires_at),
        note=f"polarity={polarity}",
    )


# ---------------------------------------------------------------------------
# Top-level wrapper used by the framework's ``check`` tool
# ---------------------------------------------------------------------------


def evaluate_spec(
    spec: Aarch64Btor2Spec,
    trace: SourceTrace,
    binding: AArch64InputBinding,
) -> SpecEvaluation:
    obs_results = tuple(evaluate_observable(o, trace, binding) for o in spec.observables)
    asm_results = tuple(evaluate_assumption(a, trace, binding) for a in spec.assumptions)
    prop_result = evaluate_property(spec.property, trace, binding)

    diagnostics: list[Mapping[str, Any]] = []
    for o in obs_results:
        if not o.fired and not o.note:
            diagnostics.append({
                "severity": "warning",
                "code": CODE_OBSERVABLE_NEVER_FIRES,
                "message": f"{o.name} never fired in concrete trace",
            })
    for a in asm_results:
        if a.holds is False:
            diagnostics.append({
                "severity": "warning",
                "code": CODE_ASSUMPTION_VIOLATED,
                "message": f"{a.name} violated in concrete binding",
            })
        elif a.note and "unsupported" in a.note:
            diagnostics.append({
                "severity": "info",
                "code": CODE_ASSUMPTION_UNSUPPORTED,
                "message": f"{a.name}: {a.note}",
            })
    if prop_result.note and "unsupported" in (prop_result.note or ""):
        diagnostics.append({
            "severity": "info",
            "code": CODE_PROPERTY_UNSUPPORTED,
            "message": prop_result.note,
        })
    elif prop_result.holds is False:
        diagnostics.append({
            "severity": "warning",
            "code": CODE_PROPERTY_VIOLATED_CONCRETELY,
            "message": (
                f"property concretely violated at step(s) "
                f"{list(prop_result.violations)}"
            ),
        })
    elif prop_result.holds is True:
        diagnostics.append({
            "severity": "info",
            "code": CODE_PROPERTY_HOLDS_CONCRETELY,
            "message": "property holds on this concrete trace",
        })

    return SpecEvaluation(
        pair="aarch64-btor2",
        inputs_hash=binding.inputs_hash(),
        steps_executed=len(trace.steps),
        halted=trace.halted,
        observables=obs_results,
        assumptions=asm_results,
        property_result=prop_result,
        diagnostics=tuple(diagnostics),
    )


__all__ = [
    "evaluate_observable",
    "evaluate_assumption",
    "evaluate_property",
    "evaluate_spec",
]
