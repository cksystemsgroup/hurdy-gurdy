"""Per-layer emission for the wasm-btor2 pair.

P13 scope: adds ``br_if`` and ``br`` branch instructions, plus the
``block`` and ``loop`` structural markers needed for loop patterns.

``br_if`` (label-depth immediate, pre-resolved to ``ins.br_target``): pops
one i32 condition.  If the condition is nonzero execution jumps to
``ins.br_target`` (the exit of the enclosing block, or the back-edge for
an enclosing loop); otherwise falls through to pc+1.  SP is decremented by
1 in either case (condition consumed).
``br`` (label-depth immediate, pre-resolved to ``ins.br_target``):
unconditional jump to ``ins.br_target``.  No stack effect for void blocks.
``block`` and ``loop``: structural label markers; execution just advances
PC by one (the label stack is not modeled in the BTOR2 transition system).
Together these four instructions enable the ``loop + br_if = while`` pattern
and early-exit from blocks.

P12 scope: adds ``if``/``else``/``end`` structured control flow to the P11
instruction set.

``if`` (type ``[] → []``, no result value): pops one i32 condition from the
stack.  If the condition is nonzero the true branch executes (PC advances to
p+1); if it is zero execution jumps to ``ins.alt`` (the start of the false
branch, or the instruction after ``end`` when there is no ``else``).
``else``: when the true branch finishes and execution reaches the ``else``
marker it jumps unconditionally to ``ins.br_target`` (the instruction after the
matching ``end``), skipping the false branch.  Block-level ``end`` just
advances PC by one (the existing fall-through handling is unchanged).
Both instructions produce no values and have no trap semantics.

P11 scope: adds i32.eqz (unary) and ten binary comparison instructions
(i32.eq, i32.ne, i32.lt_s, i32.lt_u, i32.gt_s, i32.gt_u, i32.le_s,
i32.le_u, i32.ge_s, i32.ge_u) to the P10 instruction set.

Comparison semantics: WASM comparisons return i32 (0 or 1), not i1.
The BTOR2 comparison nodes produce bv1; each lowering zero-extends the
result to bv32 via ``uext(cmp_bv1, 31)`` before writing to the stack.
No trap paths exist for any comparison instruction.

P10 scope: adds i32.and, i32.or, i32.xor, i32.shl, i32.shr_s, i32.shr_u,
i32.rotl, i32.rotr to the P9 instruction set (const, add, sub, mul,
div_s, div_u, rem_s, rem_u, local.get/set/tee, drop, nop, unreachable,
return, function-level end).

Shift semantics: WASM masks shift counts mod 32.  Each shift lowering
emits an explicit ``and(rhs, 0x1F)`` mask before the BTOR2 shift node,
so the model-checker sees the correct semantics regardless of backend.

Rotation lowering: BTOR2 has no native rotate op; rotl/rotr are expressed
as ``or(sll(a, count), srl(a, 32 - count))``.  When count == 0 the
right-shift operand is 32: z3 treats bvlshr(a,32)=0 and the evaluator
masks 32&31=0 so both give a|0=a (correct) or a|a=a (also correct).

Unsupported instructions (including float, SIMD, call) set the trap flag
rather than silently producing wrong results.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gurdy.pairs.wasm_btor2.btor2.nodes import Comment
from gurdy.pairs.wasm_btor2.source import WasmSource
from gurdy.pairs.wasm_btor2.spec import (
    Comparison,
    LocalInit,
    PropertyKind,
    WasmBtor2Spec,
)
from gurdy.pairs.wasm_btor2.translation.builder import Builder


LAYER_NAMES = (
    "header",
    "machine",
    "library",
    "dispatch",
    "init",
    "constraint",
    "bad",
    "binding",
)


# ---------------------------------------------------------------------------
# Lowering result for one instruction
# ---------------------------------------------------------------------------


@dataclass
class InstrLowering:
    """Precomputed BTOR2 expression nids for one instruction's transition.

    All nids reference current-state variables (pc, sp, stack, locals).
    The dispatch layer weaves them into PC-keyed ITE trees to produce
    the full next-state expressions.

    ``trap_nid``: None means trap is unchanged; a nid produces a new bv1
    value (typically the constant ``1``).
    ``halted_nid``: same convention.
    """

    instr_pc: int
    next_pc_nid: int
    next_sp_nid: int
    next_stack_nid: int
    next_local_writes: dict[int, int]  # local_idx -> new value nid
    trap_nid: int | None
    halted_nid: int | None


# ---------------------------------------------------------------------------
# Emit context
# ---------------------------------------------------------------------------


@dataclass
class EmitContext:
    spec: WasmBtor2Spec
    source: WasmSource
    builder: Builder
    # populated by emit_machine:
    pc_nid: int = 0       # state bv16 — instruction index within function body
    sp_nid: int = 0       # state bv8  — stack pointer (# items on stack)
    stack_nid: int = 0    # state Array[bv8, bv32] — value stack
    local_nids: list[int] = field(default_factory=list)   # state bv32 per local
    trap_nid: int = 0     # state bv1  — trap flag
    halted_nid: int = 0   # state bv1  — normal-exit flag
    param_input_nids: list[int] = field(default_factory=list)  # input bv32 per param
    n_params: int = 0
    n_locals: int = 0
    # populated by emit_library:
    instrs: list = field(default_factory=list)
    lowerings: dict[int, InstrLowering] = field(default_factory=dict)
    # populated by emit_dispatch:
    next_pc_expr: int = 0
    next_sp_expr: int = 0
    next_stack_expr: int = 0
    next_local_exprs: list[int] = field(default_factory=list)
    next_trap_expr: int = 0
    next_halted_expr: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _layer_marker(b: Builder, name: str) -> None:
    b.comment(f":layer:{name}:begin")


def _layer_end(b: Builder, name: str) -> None:
    b.comment(f":layer:{name}:end")


def _resolve_entry(ctx: EmitContext):
    """Return (func_idx, CodeEntry, FuncType) for the spec's entry function."""
    entry = ctx.spec.scope.entry_function
    if not entry:
        raise ValueError("scope.entry_function is empty")
    func_idx = ctx.source.export_func_idx(entry)
    if func_idx is None:
        raise ValueError(f"entry function {entry!r} not found in module exports")
    ftype = ctx.source.func_type(func_idx)
    if ftype is None:
        raise ValueError(f"no FuncType for function index {func_idx}")
    code = ctx.source.code_entry(func_idx)
    if code is None:
        raise ValueError(
            f"function {func_idx} has no code body (it is an import)"
        )
    return func_idx, code, ftype


def _function_end_indices(instrs: list) -> set[int]:
    """Return the set of instruction positions that are function-level 'end'."""
    depth = 0
    result: set[int] = set()
    for i, ins in enumerate(instrs):
        if ins.op in ("block", "loop", "if"):
            depth += 1
        elif ins.op == "end":
            if depth == 0:
                result.add(i)
            else:
                depth -= 1
    return result


def _sp_sub(b: Builder, sp: int, offset: int) -> int:
    """Emit sp - offset (bv8 arithmetic)."""
    if offset == 0:
        return sp
    return b.sub("bv8", sp, b.const("bv8", offset))


def _comparison_nid(b: Builder, op: Comparison, a: int, c: int) -> int:
    """Emit a bv1 comparison expression."""
    if op == Comparison.EQ:
        return b.eq(a, c)
    if op == Comparison.NE:
        return b.neq(a, c)
    if op == Comparison.LT:
        return b.slt(a, c)
    if op == Comparison.LE:
        return b.emit("slte", "bv1", a, c)
    if op == Comparison.GT:
        return b.emit("sgt", "bv1", a, c)
    if op == Comparison.GE:
        return b.emit("sgte", "bv1", a, c)
    if op == Comparison.LTU:
        return b.ult(a, c)
    if op == Comparison.LEU:
        return b.emit("ulte", "bv1", a, c)
    if op == Comparison.GTU:
        return b.emit("ugt", "bv1", a, c)
    if op == Comparison.GEU:
        return b.emit("ugte", "bv1", a, c)
    raise ValueError(f"unsupported comparison: {op}")


# ---------------------------------------------------------------------------
# Per-instruction lowering
# ---------------------------------------------------------------------------


def _lower_instr(
    b: Builder, ctx: EmitContext, p: int, ins, is_func_end: bool
) -> InstrLowering:
    """Compute the BTOR2 transition expressions for instruction at position p."""
    op = ins.op

    # Defaults: advance PC by 1, everything else unchanged.
    next_pc_nid: int = b.const("bv16", p + 1)
    next_sp_nid: int = ctx.sp_nid
    next_stack_nid: int = ctx.stack_nid
    next_local_writes: dict[int, int] = {}
    trap_nid: int | None = None
    halted_nid: int | None = None

    if op == "unreachable":
        next_pc_nid = b.const("bv16", p)  # self-loop
        trap_nid = b.const("bv1", 1)

    elif op == "nop":
        pass  # just advance PC

    elif op == "end" and is_func_end:
        next_pc_nid = b.const("bv16", p)  # self-loop
        halted_nid = b.const("bv1", 1)

    elif op == "end":
        # Block-level end: label stack is not modeled; just advance PC.
        pass

    elif op == "block":
        pass  # structural marker; just advance PC

    elif op == "loop":
        pass  # structural marker; just advance PC to loop body

    elif op == "br":
        jump_target = ins.br_target if ins.br_target >= 0 else p + 1
        next_pc_nid = b.const("bv16", jump_target)

    elif op == "br_if":
        # Pop condition; jump to br_target if nonzero, otherwise fall through.
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        condition = b.read("bv32", ctx.stack_nid, sp_m1)
        nonzero = b.neq(condition, b.const("bv32", 0))
        jump_target = ins.br_target if ins.br_target >= 0 else p + 1
        next_pc_nid = b.ite(
            "bv16", nonzero, b.const("bv16", jump_target), b.const("bv16", p + 1)
        )
        next_sp_nid = sp_m1

    elif op == "if":
        # Pop condition; branch on nonzero (ins.alt is the false target).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        condition = b.read("bv32", ctx.stack_nid, sp_m1)
        nonzero = b.neq(condition, b.const("bv32", 0))
        false_target = ins.alt if ins.alt >= 0 else p + 1
        next_pc_nid = b.ite(
            "bv16", nonzero, b.const("bv16", p + 1), b.const("bv16", false_target)
        )
        next_sp_nid = sp_m1

    elif op == "else":
        # True branch finished; jump past the matching end (ins.br_target).
        jump_target = ins.br_target if ins.br_target >= 0 else p + 1
        next_pc_nid = b.const("bv16", jump_target)

    elif op == "return":
        next_pc_nid = b.const("bv16", p)  # self-loop
        halted_nid = b.const("bv1", 1)

    elif op == "drop":
        next_sp_nid = _sp_sub(b, ctx.sp_nid, 1)

    elif op == "i32.const":
        c = ins.imm[0] & 0xFFFFFFFF
        val_nid = b.const("bv32", c)
        next_stack_nid = b.write("stack", ctx.stack_nid, ctx.sp_nid, val_nid)
        next_sp_nid = b.add("bv8", ctx.sp_nid, b.const("bv8", 1))

    elif op == "i32.add":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.add("bv32", lhs, rhs)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1  # sp - 1

    elif op == "i32.sub":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.sub("bv32", lhs, rhs)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.mul":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.mul("bv32", lhs, rhs)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.div_s":
        # Traps if divisor==0 or (dividend==INT32_MIN and divisor==-1).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        zero_div = b.eq(rhs, b.const("bv32", 0))
        overflow = b.and_(
            "bv1",
            b.eq(lhs, b.const("bv32", 0x80000000)),
            b.eq(rhs, b.ones("bv32")),
        )
        trap_cond = b.or_("bv1", zero_div, overflow)
        result = b.sdiv("bv32", lhs, rhs)
        next_pc_nid = b.ite("bv16", trap_cond, b.const("bv16", p), b.const("bv16", p + 1))
        next_sp_nid = b.ite("bv8", trap_cond, ctx.sp_nid, sp_m1)
        next_stack_nid = b.ite(
            "stack", trap_cond, ctx.stack_nid,
            b.write("stack", ctx.stack_nid, sp_m2, result),
        )
        trap_nid = b.ite("bv1", trap_cond, b.const("bv1", 1), ctx.trap_nid)

    elif op == "i32.div_u":
        # Traps if divisor==0.
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        trap_cond = b.eq(rhs, b.const("bv32", 0))
        result = b.udiv("bv32", lhs, rhs)
        next_pc_nid = b.ite("bv16", trap_cond, b.const("bv16", p), b.const("bv16", p + 1))
        next_sp_nid = b.ite("bv8", trap_cond, ctx.sp_nid, sp_m1)
        next_stack_nid = b.ite(
            "stack", trap_cond, ctx.stack_nid,
            b.write("stack", ctx.stack_nid, sp_m2, result),
        )
        trap_nid = b.ite("bv1", trap_cond, b.const("bv1", 1), ctx.trap_nid)

    elif op == "i32.rem_s":
        # Traps if divisor==0. INT32_MIN % -1 == 0 (no trap, per WASM spec).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        trap_cond = b.eq(rhs, b.const("bv32", 0))
        result = b.srem("bv32", lhs, rhs)
        next_pc_nid = b.ite("bv16", trap_cond, b.const("bv16", p), b.const("bv16", p + 1))
        next_sp_nid = b.ite("bv8", trap_cond, ctx.sp_nid, sp_m1)
        next_stack_nid = b.ite(
            "stack", trap_cond, ctx.stack_nid,
            b.write("stack", ctx.stack_nid, sp_m2, result),
        )
        trap_nid = b.ite("bv1", trap_cond, b.const("bv1", 1), ctx.trap_nid)

    elif op == "i32.rem_u":
        # Traps if divisor==0.
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        trap_cond = b.eq(rhs, b.const("bv32", 0))
        result = b.urem("bv32", lhs, rhs)
        next_pc_nid = b.ite("bv16", trap_cond, b.const("bv16", p), b.const("bv16", p + 1))
        next_sp_nid = b.ite("bv8", trap_cond, ctx.sp_nid, sp_m1)
        next_stack_nid = b.ite(
            "stack", trap_cond, ctx.stack_nid,
            b.write("stack", ctx.stack_nid, sp_m2, result),
        )
        trap_nid = b.ite("bv1", trap_cond, b.const("bv1", 1), ctx.trap_nid)

    elif op == "i32.and":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.and_("bv32", lhs, rhs)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.or":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.or_("bv32", lhs, rhs)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.xor":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.xor("bv32", lhs, rhs)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.shl":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        count = b.and_("bv32", rhs, b.const("bv32", 31))
        result = b.sll("bv32", lhs, count)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.shr_s":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        count = b.and_("bv32", rhs, b.const("bv32", 31))
        result = b.sra("bv32", lhs, count)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.shr_u":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        count = b.and_("bv32", rhs, b.const("bv32", 31))
        result = b.srl("bv32", lhs, count)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.rotl":
        # rotl(a, n) = (a << (n&31)) | (a >> (32 - (n&31)))
        # When count==0: srl(a, 32) is 0 in z3 theory, a>>0 in evaluator;
        # either way or(sll(a,0), ...) = a.
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        count = b.and_("bv32", rhs, b.const("bv32", 31))
        anti = b.sub("bv32", b.const("bv32", 32), count)
        left_part = b.sll("bv32", lhs, count)
        right_part = b.srl("bv32", lhs, anti)
        result = b.or_("bv32", left_part, right_part)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.rotr":
        # rotr(a, n) = (a >> (n&31)) | (a << (32 - (n&31)))
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        count = b.and_("bv32", rhs, b.const("bv32", 31))
        anti = b.sub("bv32", b.const("bv32", 32), count)
        right_part = b.srl("bv32", lhs, count)
        left_part = b.sll("bv32", lhs, anti)
        result = b.or_("bv32", right_part, left_part)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.eqz":
        # Unary: pop 1, compare with zero, push bv32 result (0 or 1).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        operand = b.read("bv32", ctx.stack_nid, sp_m1)
        cmp = _comparison_nid(b, Comparison.EQ, operand, b.const("bv32", 0))
        result = b.uext("bv32", cmp, 31)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m1, result)
        # sp unchanged — eqz replaces top of stack in-place

    elif op == "i32.eq":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.EQ, lhs, rhs), 31)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.ne":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.NE, lhs, rhs), 31)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.lt_s":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.LT, lhs, rhs), 31)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.lt_u":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.LTU, lhs, rhs), 31)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.gt_s":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.GT, lhs, rhs), 31)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.gt_u":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.GTU, lhs, rhs), 31)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.le_s":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.LE, lhs, rhs), 31)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.le_u":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.LEU, lhs, rhs), 31)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.ge_s":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.GE, lhs, rhs), 31)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.ge_u":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv32", ctx.stack_nid, sp_m1)
        lhs = b.read("bv32", ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.GEU, lhs, rhs), 31)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "local.get":
        k = ins.imm[0]
        if k >= len(ctx.local_nids):
            next_pc_nid = b.const("bv16", p)
            trap_nid = b.const("bv1", 1)
        else:
            next_stack_nid = b.write(
                "stack", ctx.stack_nid, ctx.sp_nid, ctx.local_nids[k]
            )
            next_sp_nid = b.add("bv8", ctx.sp_nid, b.const("bv8", 1))

    elif op == "local.set":
        k = ins.imm[0]
        if k >= len(ctx.local_nids):
            next_pc_nid = b.const("bv16", p)
            trap_nid = b.const("bv1", 1)
        else:
            sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
            top_val = b.read("bv32", ctx.stack_nid, sp_m1)
            next_local_writes[k] = top_val
            next_sp_nid = sp_m1

    elif op == "local.tee":
        k = ins.imm[0]
        if k >= len(ctx.local_nids):
            next_pc_nid = b.const("bv16", p)
            trap_nid = b.const("bv1", 1)
        else:
            sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
            top_val = b.read("bv32", ctx.stack_nid, sp_m1)
            next_local_writes[k] = top_val
            # sp unchanged; stack unchanged

    else:
        # Unsupported instruction: trap and self-loop.
        next_pc_nid = b.const("bv16", p)
        trap_nid = b.const("bv1", 1)

    return InstrLowering(
        instr_pc=p,
        next_pc_nid=next_pc_nid,
        next_sp_nid=next_sp_nid,
        next_stack_nid=next_stack_nid,
        next_local_writes=next_local_writes,
        trap_nid=trap_nid,
        halted_nid=halted_nid,
    )


# ---------------------------------------------------------------------------
# header layer
# ---------------------------------------------------------------------------


def emit_header(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "header")
    for name in ("bv1", "bv8", "bv16", "bv32", "bv64"):
        b.declare_sort(name)
    b.declare_array_sort("stack", "bv8", "bv32")
    _layer_end(b, "header")


# ---------------------------------------------------------------------------
# machine layer
# ---------------------------------------------------------------------------


def emit_machine(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "machine")

    _, code, ftype = _resolve_entry(ctx)

    n_params = len(ftype.params)
    n_extra = sum(ld.count for ld in code.locals)
    n_locals = n_params + n_extra
    ctx.n_params = n_params
    ctx.n_locals = n_locals

    ctx.pc_nid = b.emit_no_sort(
        "state", b.declare_sort("bv16"), symbol="pc"
    )
    ctx.sp_nid = b.emit_no_sort(
        "state", b.declare_sort("bv8"), symbol="sp"
    )
    ctx.stack_nid = b.emit_no_sort(
        "state",
        b.declare_array_sort("stack", "bv8", "bv32"),
        symbol="stack",
    )

    bv32 = b.declare_sort("bv32")
    for k in range(n_params):
        local_nid = b.emit_no_sort("state", bv32, symbol=f"local_{k}")
        ctx.local_nids.append(local_nid)
        param_input = b.emit_no_sort("input", bv32, symbol=f"param_{k}_init")
        ctx.param_input_nids.append(param_input)
    for k in range(n_params, n_locals):
        local_nid = b.emit_no_sort("state", bv32, symbol=f"local_{k}")
        ctx.local_nids.append(local_nid)

    ctx.trap_nid = b.emit_no_sort(
        "state", b.declare_sort("bv1"), symbol="trap"
    )
    ctx.halted_nid = b.emit_no_sort(
        "state", b.declare_sort("bv1"), symbol="halted"
    )
    _layer_end(b, "machine")


# ---------------------------------------------------------------------------
# library layer
# ---------------------------------------------------------------------------


def emit_library(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "library")

    _, code, _ = _resolve_entry(ctx)
    instrs = code.body
    ctx.instrs = instrs

    func_ends = _function_end_indices(instrs)
    for p, ins in enumerate(instrs):
        lowering = _lower_instr(b, ctx, p, ins, p in func_ends)
        ctx.lowerings[p] = lowering

    _layer_end(b, "library")


# ---------------------------------------------------------------------------
# dispatch layer  (PC-keyed ITE trees for every state component)
# ---------------------------------------------------------------------------


def emit_dispatch(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "dispatch")

    all_pcs = sorted(ctx.lowerings.keys())

    # --- next_pc ---
    nxt = ctx.pc_nid  # default: self-loop
    for p in reversed(all_pcs):
        cond = b.eq(ctx.pc_nid, b.const("bv16", p))
        nxt = b.ite("bv16", cond, ctx.lowerings[p].next_pc_nid, nxt)
    ctx.next_pc_expr = nxt

    # --- next_sp ---
    nxt = ctx.sp_nid
    for p in reversed(all_pcs):
        cond = b.eq(ctx.pc_nid, b.const("bv16", p))
        nxt = b.ite("bv8", cond, ctx.lowerings[p].next_sp_nid, nxt)
    ctx.next_sp_expr = nxt

    # --- next_stack ---
    nxt = ctx.stack_nid
    for p in reversed(all_pcs):
        cond = b.eq(ctx.pc_nid, b.const("bv16", p))
        nxt = b.ite("stack", cond, ctx.lowerings[p].next_stack_nid, nxt)
    ctx.next_stack_expr = nxt

    # --- next_local[k] ---
    ctx.next_local_exprs = list(ctx.local_nids)  # default: identity
    for k in range(ctx.n_locals):
        nxt_k = ctx.local_nids[k]
        for p in reversed(all_pcs):
            if k in ctx.lowerings[p].next_local_writes:
                cond = b.eq(ctx.pc_nid, b.const("bv16", p))
                nxt_k = b.ite(
                    "bv32", cond, ctx.lowerings[p].next_local_writes[k], nxt_k
                )
        ctx.next_local_exprs[k] = nxt_k

    # --- next_trap ---
    nxt = ctx.trap_nid
    for p in reversed(all_pcs):
        t = ctx.lowerings[p].trap_nid
        if t is not None:
            cond = b.eq(ctx.pc_nid, b.const("bv16", p))
            nxt = b.ite("bv1", cond, t, nxt)
    ctx.next_trap_expr = nxt

    # --- next_halted ---
    nxt = ctx.halted_nid
    for p in reversed(all_pcs):
        h = ctx.lowerings[p].halted_nid
        if h is not None:
            cond = b.eq(ctx.pc_nid, b.const("bv16", p))
            nxt = b.ite("bv1", cond, h, nxt)
    ctx.next_halted_expr = nxt

    _layer_end(b, "dispatch")


# ---------------------------------------------------------------------------
# init layer
# ---------------------------------------------------------------------------


def emit_init(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "init")

    bv16 = b.declare_sort("bv16")
    bv8 = b.declare_sort("bv8")
    bv32 = b.declare_sort("bv32")
    bv1 = b.declare_sort("bv1")

    b.emit_no_sort("init", bv16, ctx.pc_nid, b.const("bv16", 0))
    b.emit_no_sort("init", bv8, ctx.sp_nid, b.const("bv8", 0))
    b.emit_no_sort("init", bv1, ctx.trap_nid, b.const("bv1", 0))
    b.emit_no_sort("init", bv1, ctx.halted_nid, b.const("bv1", 0))

    for k in range(ctx.n_params):
        b.emit_no_sort("init", bv32, ctx.local_nids[k], ctx.param_input_nids[k])
    for k in range(ctx.n_params, ctx.n_locals):
        b.emit_no_sort("init", bv32, ctx.local_nids[k], b.const("bv32", 0))

    _layer_end(b, "init")


# ---------------------------------------------------------------------------
# constraint layer
# ---------------------------------------------------------------------------


def emit_constraint(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "constraint")

    for asm in ctx.spec.assumptions:
        if isinstance(asm, LocalInit):
            if asm.local_idx < ctx.n_locals:
                local_nid = ctx.local_nids[asm.local_idx]
                val_nid = b.const("bv32", asm.value & 0xFFFFFFFF)
                cond = _comparison_nid(b, asm.op, local_nid, val_nid)
                b.emit_no_sort("constraint", cond)

    _layer_end(b, "constraint")


# ---------------------------------------------------------------------------
# bad layer
# ---------------------------------------------------------------------------


def emit_bad(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "bad")

    kind = ctx.spec.question.kind
    negate = ctx.spec.question.negate

    if kind == PropertyKind.REACH_TRAP:
        bad_nid = ctx.trap_nid
    else:
        # Unsupported property kinds for P4: placeholder (never bad).
        bad_nid = b.const("bv1", 0)

    if negate:
        bad_nid = b.not_("bv1", bad_nid)

    b.emit_no_sort("bad", bad_nid)
    _layer_end(b, "bad")


# ---------------------------------------------------------------------------
# binding layer
# ---------------------------------------------------------------------------


def emit_binding(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "binding")

    bv16 = b.declare_sort("bv16")
    bv8 = b.declare_sort("bv8")
    bv32 = b.declare_sort("bv32")
    bv1 = b.declare_sort("bv1")
    stack_sort = b.declare_array_sort("stack", "bv8", "bv32")

    b.emit_no_sort("next", bv16, ctx.pc_nid, ctx.next_pc_expr)
    b.emit_no_sort("next", bv8, ctx.sp_nid, ctx.next_sp_expr)
    b.emit_no_sort("next", stack_sort, ctx.stack_nid, ctx.next_stack_expr)
    for k in range(ctx.n_locals):
        b.emit_no_sort("next", bv32, ctx.local_nids[k], ctx.next_local_exprs[k])
    b.emit_no_sort("next", bv1, ctx.trap_nid, ctx.next_trap_expr)
    b.emit_no_sort("next", bv1, ctx.halted_nid, ctx.next_halted_expr)

    _layer_end(b, "binding")


__all__ = [
    "EmitContext",
    "InstrLowering",
    "LAYER_NAMES",
    "emit_bad",
    "emit_binding",
    "emit_constraint",
    "emit_dispatch",
    "emit_header",
    "emit_init",
    "emit_library",
    "emit_machine",
]
