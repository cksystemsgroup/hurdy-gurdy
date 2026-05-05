"""Concrete evaluation of riscv-btor2 spec predicates.

The translator emits BTOR2 fragments for observables, assumptions,
and the property; this module evaluates the *same* spec types against
a concrete ``SourceTrace`` produced by the source interpreter. The
two paths share grammar (``translation/exprs.py``) but evaluate to
ints rather than nids.

A spec predicate falls into one of three buckets:

- **Structured types** (``RegisterAt``, ``RegisterInit``,
  ``Property(expression='true'|'false')``, …) — evaluated directly
  against the trace.
- **String-expression types** (``CycleInvariant``, ``Property`` with
  a non-trivial expression) — evaluated by the small concrete
  expression evaluator below; unsupported sub-forms produce a
  structured "unsupported" diagnostic rather than failing.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from gurdy.core.interp.diagnostics import (
    CODE_ASSUMPTION_UNSUPPORTED,
    CODE_ASSUMPTION_VACUOUS,
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
from gurdy.pairs.riscv_btor2.source_interp.bindings import RiscvInputBinding
from gurdy.pairs.riscv_btor2.spec import (
    Comparison,
    CycleInvariant,
    Executed,
    MemoryAt,
    MemoryInit,
    PCAtStep,
    Property,
    RegisterAt,
    RegisterInit,
    RiscvBtor2Spec,
)


MASK64 = (1 << 64) - 1


# ---------------------------------------------------------------------------
# Concrete state extraction
# ---------------------------------------------------------------------------


def _pre_step_regs(
    trace: SourceTrace, binding: RiscvInputBinding, step: int
) -> tuple[int, ...]:
    """Register snapshot *before* step ``step`` executes.

    For step 0 it's the binding's register init layered over zeros.
    For step i > 0 it's the post-step regs of step i-1.
    """
    if step <= 0:
        regs = [0] * 32
        for r, v in (binding.register_init or {}).items():
            if 1 <= r < 32:
                regs[r] = v & MASK64
        return tuple(regs)
    return tuple(trace.steps[step - 1].deltas.get("regs", ()) or ())


def _pre_step_pc(
    trace: SourceTrace, binding: RiscvInputBinding, step: int
) -> int | None:
    if step <= 0:
        return binding.pc
    return trace.steps[step - 1].deltas.get("pc")


def _post_step_regs(trace: SourceTrace, step: int) -> tuple[int, ...]:
    if 0 <= step < len(trace.steps):
        return tuple(trace.steps[step].deltas.get("regs", ()) or ())
    return ()


# ---------------------------------------------------------------------------
# Concrete expression evaluator (mirrors translation/exprs.py grammar)
# ---------------------------------------------------------------------------


import re

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
    """Evaluates a spec expression against a concrete (regs, mem, pc) view.

    The grammar matches ``translation/exprs.py`` but evaluation
    targets ints. ``mem`` is supported only when explicit memory state
    is provided.
    """

    def __init__(
        self,
        regs: Sequence[int],
        pc: int,
        mem: Mapping[int, int] | None = None,
    ):
        self.regs = list(regs) + [0] * (32 - len(regs)) if len(regs) < 32 else list(regs)
        self.pc = int(pc) & MASK64
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
                if 0 <= idx < 32:
                    return self.regs[idx] & MASK64
                raise _UnsupportedExpr(f"reg({idx}) out of range")
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


# ---------------------------------------------------------------------------
# Comparison helper for RegisterInit / MemoryInit
# ---------------------------------------------------------------------------


def _cmp(actual: int, op: Comparison, target: int) -> bool:
    actual &= MASK64
    target &= MASK64
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
    a = _to_signed(actual)
    t = _to_signed(target)
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
    obs, trace: SourceTrace, binding: RiscvInputBinding
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
    asm, trace: SourceTrace, binding: RiscvInputBinding
) -> SpecPredicateResult:
    if isinstance(asm, RegisterInit):
        actual = (binding.register_init or {}).get(asm.register, 0)
        held = _cmp(actual, asm.op, asm.value)
        return SpecPredicateResult(
            name=f"RegisterInit(x{asm.register} {asm.op.value} {asm.value})",
            kind=PredicateKind.ASSUMPTION,
            holds=held,
            violations=() if held else (0,),
            note=None if held else f"actual={actual}",
        )
    if isinstance(asm, MemoryInit):
        # Read width bytes little-endian from binding.memory_init.
        v = 0
        for k in range(asm.width):
            v |= ((binding.memory_init or {}).get(asm.address + k, 0) & 0xFF) << (8 * k)
        held = _cmp(v, asm.op, asm.value)
        return SpecPredicateResult(
            name=f"MemoryInit(0x{asm.address:x}/{asm.width} {asm.op.value} {asm.value})",
            kind=PredicateKind.ASSUMPTION,
            holds=held,
            violations=() if held else (0,),
            note=None if held else f"actual=0x{v:x}",
        )
    if isinstance(asm, CycleInvariant):
        # Evaluate the expression at every step's pre-state.
        violations: list[int] = []
        for i in range(len(trace.steps) + 1):
            regs = _pre_step_regs(trace, binding, i)
            pc = _pre_step_pc(trace, binding, i)
            if pc is None:
                continue
            try:
                v = _ConcreteExprEvaluator(regs, pc).eval(asm.expression)
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
    prop: Property, trace: SourceTrace, binding: RiscvInputBinding
) -> SpecPredicateResult:
    expr = prop.expression.strip()
    if expr in ("false",):
        # Bad expression always-false → never fires → property holds.
        return SpecPredicateResult(
            name="property",
            kind=PredicateKind.PROPERTY,
            holds=True,
            note="bad-expression is constant false",
        )
    if expr in ("true",):
        return SpecPredicateResult(
            name="property",
            kind=PredicateKind.PROPERTY,
            holds=False,
            violations=(0,),
            note="bad-expression is constant true",
        )

    fires_at: list[int] = []
    for i in range(len(trace.steps) + 1):
        regs = _pre_step_regs(trace, binding, i)
        pc = _pre_step_pc(trace, binding, i)
        if pc is None:
            continue
        try:
            v = _ConcreteExprEvaluator(regs, pc).eval(expr)
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
        # Negated property: bad expression's complement is the bad. We flip.
        all_steps = list(range(len(trace.steps) + 1))
        held_steps = [s for s in all_steps if s not in fires_at]
        violations = tuple(s for s in all_steps if s in fires_at)
        violations = tuple(s for s in all_steps if s not in fires_at)
        # Negated: bad fires when expr is *false*, so violations = held_steps.
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
    spec: RiscvBtor2Spec,
    trace: SourceTrace,
    binding: RiscvInputBinding,
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
        pair="riscv-btor2",
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
