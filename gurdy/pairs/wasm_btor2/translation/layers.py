"""Per-layer emission for the wasm-btor2 pair.

P17 scope: adds four i64 arithmetic instructions: ``i64.const``, ``i64.add``,
``i64.sub``, ``i64.mul``.  The bv64 stack introduced in P16 makes these
straightforward: push/pop bv64 values directly (no uext/slice conversion).

``i64.const N``: push bv64 constant to stack[sp], sp++.
``i64.add``: pop bv64 rhs (sp-1) and lhs (sp-2), add as bv64, push to sp-2,
sp--.
``i64.sub``: same with subtraction.
``i64.mul``: same with multiplication.
No trap semantics for any of the four instructions.

P16 scope: widens the value stack element sort from bv32 to bv64 and adds
three type-conversion instructions: ``i32.wrap_i64``, ``i64.extend_i32_s``,
``i64.extend_i32_u``.

Stack format change: the stack array sort is now ``Array[bv8, bv64]``
(previously ``Array[bv8, bv32]``).  All i32 push sites zero-extend the bv32
result to bv64 via ``uext(val, 32)`` before writing; all i32 pop sites read
bv64 from the array and truncate to bv32 via ``slice(val, 31, 0)``.  Two
helpers, ``_stack_pop_i32`` and ``_stack_push_i32``, encapsulate these
conversions so every existing instruction lowering is unchanged in intent.

``i64.extend_i32_u``: pop bv32 top-of-stack, zero-extend to bv64 via
``uext(val, 32)``, write the bv64 result back to the same slot (SP
unchanged).
``i64.extend_i32_s``: same, but sign-extend via ``sext(val, 32)``.
``i32.wrap_i64``: pop bv64 top-of-stack (read directly), truncate to bv32 via
``slice(val, 31, 0)``, push the bv32 result (zero-extended to bv64 by the
push helper).  SP unchanged.
No trap semantics for any of the three instructions.

P15 scope: adds ``call`` (direct intra-module function call) to the P14
instruction set, enables multi-function modules.

The translator linearises all local (non-import) function bodies into a single
PC space: the entry function occupies PCs 0..len(entry_body)-1; other functions
follow in module order.  A new bv4 call-stack pointer (``csp``) and a
``call_stack`` array (Array[bv4, bv16]) carry return addresses.

``call N`` (function-index immediate): if function N exists in the module,
saves pc+1 to ``call_stack[csp]``, increments csp, and jumps to the entry PC
of function N.  If N is not a local function, sets trap (unsupported callee).

``return`` and function-level ``end``: when csp > 0 (caller present) the
instruction pops the call stack (decrement csp, read saved return PC) and
jumps back.  When csp == 0 (top-level) it self-loops and sets halted = 1, as
before.

Callee locals: P15 does not model per-activation local frames.  The machine's
local state (``local_0, local_1, ...``) belongs to the entry function; callee
functions should have no params and no extra locals for correct behaviour.
Future iterations may add per-activation save/restore.

P14 scope: adds ``i32.clz``, ``i32.ctz``, ``i32.popcnt`` unary bit-counting
instructions to the P13 instruction set.

``i32.clz``: count leading zeros of the top-of-stack bv32 value.  Returns
bv32 in [0, 32]; clz(0) = 32 per WASM spec.  Encoded as a 32-deep ITE
priority encoder — iterate bit positions from MSB (31) down to LSB (0);
the highest set bit determines the count.  No trap semantics.

``i32.ctz``: count trailing zeros.  Returns bv32 in [0, 32]; ctz(0) = 32.
Encoded symmetrically from LSB to MSB.  No trap semantics.

``i32.popcnt``: population count (number of set bits).  Returns bv32 in
[0, 32].  Encoded as the sum of all 32 ``uext(slice(x, k, k), 31)``
contributions, one per bit position.  No trap semantics.

None of the three instructions consume an extra operand; each pops one
value, computes a result, and pushes it back in-place (SP unchanged).

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
    next_csp_nid: int | None = None         # None → csp unchanged
    next_call_stack_nid: int | None = None  # None → call_stack unchanged


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
    stack_nid: int = 0    # state Array[bv8, bv64] — value stack (bv64 elements; i32 ops truncate on pop)
    local_nids: list[int] = field(default_factory=list)   # state bv32 per local
    trap_nid: int = 0     # state bv1  — trap flag
    halted_nid: int = 0   # state bv1  — normal-exit flag
    param_input_nids: list[int] = field(default_factory=list)  # input bv32 per param
    n_params: int = 0
    n_locals: int = 0
    csp_nid: int = 0      # state bv4  — call stack pointer
    call_stack_nid: int = 0  # state Array[bv4, bv16] — saved return PCs
    # populated by emit_library:
    func_entry_pcs: dict[int, int] = field(default_factory=dict)  # func_idx → first PC
    instrs: list = field(default_factory=list)
    lowerings: dict[int, InstrLowering] = field(default_factory=dict)
    # populated by emit_dispatch:
    next_pc_expr: int = 0
    next_sp_expr: int = 0
    next_stack_expr: int = 0
    next_local_exprs: list[int] = field(default_factory=list)
    next_trap_expr: int = 0
    next_halted_expr: int = 0
    next_csp_expr: int = 0
    next_call_stack_expr: int = 0


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


def _stack_pop_i32(b: Builder, stack_nid: int, addr_nid: int) -> int:
    """Read a bv32 value from the bv64-element stack (slice low 32 bits)."""
    val64 = b.read("bv64", stack_nid, addr_nid)
    return b.slice_("bv32", val64, 31, 0)


def _stack_push_i32(b: Builder, stack_nid: int, addr_nid: int, val_bv32: int) -> int:
    """Write a bv32 value to the bv64-element stack (zero-extend to bv64)."""
    val64 = b.uext("bv64", val_bv32, 32)
    return b.write("stack", stack_nid, addr_nid, val64)


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
# Bit-counting helpers (clz / ctz / popcnt)
# ---------------------------------------------------------------------------


def _clz_nid(b: Builder, x_nid: int) -> int:
    """Encode i32.clz as a 32-deep ITE priority encoder; returns bv32 (0..32).

    Iterates bit positions k=0..31, applying each as the *outermost* ITE last,
    so bit 31 (MSB) wins: result = ite(bit31, 0, ite(bit30, 1, ... ite(bit0, 31, 32))).
    """
    result = b.const("bv32", 32)  # clz(0) = 32
    for k in range(32):  # k=31 applied last → MSB has highest priority
        bit_k = b.slice_("bv1", x_nid, k, k)
        result = b.ite("bv32", bit_k, b.const("bv32", 31 - k), result)
    return result


def _ctz_nid(b: Builder, x_nid: int) -> int:
    """Encode i32.ctz as a 32-deep ITE priority encoder; returns bv32 (0..32).

    Iterates bit positions k=31..0, applying each as the *outermost* ITE last,
    so bit 0 (LSB) wins: result = ite(bit0, 0, ite(bit1, 1, ... ite(bit31, 31, 32))).
    """
    result = b.const("bv32", 32)  # ctz(0) = 32
    for k in range(31, -1, -1):  # k=0 applied last → LSB has highest priority
        bit_k = b.slice_("bv1", x_nid, k, k)
        result = b.ite("bv32", bit_k, b.const("bv32", k), result)
    return result


def _popcnt_nid(b: Builder, x_nid: int) -> int:
    """Encode i32.popcnt as the sum of 32 single-bit contributions; returns bv32 (0..32)."""
    result = b.const("bv32", 0)
    for k in range(32):
        bit_k = b.slice_("bv1", x_nid, k, k)
        bit32 = b.uext("bv32", bit_k, 31)
        result = b.add("bv32", result, bit32)
    return result


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
    next_csp_nid: int | None = None
    next_call_stack_nid: int | None = None

    if op == "unreachable":
        next_pc_nid = b.const("bv16", p)  # self-loop
        trap_nid = b.const("bv1", 1)

    elif op == "nop":
        pass  # just advance PC

    elif op == "end" and is_func_end:
        # When csp > 0 we are a callee: pop the call stack and jump back.
        # When csp == 0 we are the top-level entry: self-loop and halt.
        has_caller = b.neq(ctx.csp_nid, b.const("bv4", 0))
        new_csp = b.sub("bv4", ctx.csp_nid, b.const("bv4", 1))
        ret_pc = b.read("bv16", ctx.call_stack_nid, new_csp)
        next_pc_nid = b.ite("bv16", has_caller, ret_pc, b.const("bv16", p))
        next_csp_nid = b.ite("bv4", has_caller, new_csp, ctx.csp_nid)
        halted_nid = b.ite("bv1", has_caller, b.const("bv1", 0), b.const("bv1", 1))

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
        condition = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        nonzero = b.neq(condition, b.const("bv32", 0))
        jump_target = ins.br_target if ins.br_target >= 0 else p + 1
        next_pc_nid = b.ite(
            "bv16", nonzero, b.const("bv16", jump_target), b.const("bv16", p + 1)
        )
        next_sp_nid = sp_m1

    elif op == "if":
        # Pop condition; branch on nonzero (ins.alt is the false target).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        condition = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
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
        has_caller = b.neq(ctx.csp_nid, b.const("bv4", 0))
        new_csp = b.sub("bv4", ctx.csp_nid, b.const("bv4", 1))
        ret_pc = b.read("bv16", ctx.call_stack_nid, new_csp)
        next_pc_nid = b.ite("bv16", has_caller, ret_pc, b.const("bv16", p))
        next_csp_nid = b.ite("bv4", has_caller, new_csp, ctx.csp_nid)
        halted_nid = b.ite("bv1", has_caller, b.const("bv1", 0), b.const("bv1", 1))

    elif op == "call":
        callee_idx = ins.imm[0]
        if callee_idx not in ctx.func_entry_pcs:
            # Callee not in this module (import or not yet supported): trap.
            next_pc_nid = b.const("bv16", p)
            trap_nid = b.const("bv1", 1)
        else:
            callee_pc = ctx.func_entry_pcs[callee_idx]
            ret_addr = b.const("bv16", p + 1)
            next_call_stack_nid = b.write(
                "call_stack", ctx.call_stack_nid, ctx.csp_nid, ret_addr
            )
            next_csp_nid = b.add("bv4", ctx.csp_nid, b.const("bv4", 1))
            next_pc_nid = b.const("bv16", callee_pc)

    elif op == "drop":
        next_sp_nid = _sp_sub(b, ctx.sp_nid, 1)

    elif op == "i32.const":
        c = ins.imm[0] & 0xFFFFFFFF
        val_nid = b.const("bv32", c)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, ctx.sp_nid, val_nid)
        next_sp_nid = b.add("bv8", ctx.sp_nid, b.const("bv8", 1))

    elif op == "i32.add":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.add("bv32", lhs, rhs)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1  # sp - 1

    elif op == "i32.sub":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.sub("bv32", lhs, rhs)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.mul":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.mul("bv32", lhs, rhs)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.div_s":
        # Traps if divisor==0 or (dividend==INT32_MIN and divisor==-1).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
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
            _stack_push_i32(b, ctx.stack_nid, sp_m2, result),
        )
        trap_nid = b.ite("bv1", trap_cond, b.const("bv1", 1), ctx.trap_nid)

    elif op == "i32.div_u":
        # Traps if divisor==0.
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        trap_cond = b.eq(rhs, b.const("bv32", 0))
        result = b.udiv("bv32", lhs, rhs)
        next_pc_nid = b.ite("bv16", trap_cond, b.const("bv16", p), b.const("bv16", p + 1))
        next_sp_nid = b.ite("bv8", trap_cond, ctx.sp_nid, sp_m1)
        next_stack_nid = b.ite(
            "stack", trap_cond, ctx.stack_nid,
            _stack_push_i32(b, ctx.stack_nid, sp_m2, result),
        )
        trap_nid = b.ite("bv1", trap_cond, b.const("bv1", 1), ctx.trap_nid)

    elif op == "i32.rem_s":
        # Traps if divisor==0. INT32_MIN % -1 == 0 (no trap, per WASM spec).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        trap_cond = b.eq(rhs, b.const("bv32", 0))
        result = b.srem("bv32", lhs, rhs)
        next_pc_nid = b.ite("bv16", trap_cond, b.const("bv16", p), b.const("bv16", p + 1))
        next_sp_nid = b.ite("bv8", trap_cond, ctx.sp_nid, sp_m1)
        next_stack_nid = b.ite(
            "stack", trap_cond, ctx.stack_nid,
            _stack_push_i32(b, ctx.stack_nid, sp_m2, result),
        )
        trap_nid = b.ite("bv1", trap_cond, b.const("bv1", 1), ctx.trap_nid)

    elif op == "i32.rem_u":
        # Traps if divisor==0.
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        trap_cond = b.eq(rhs, b.const("bv32", 0))
        result = b.urem("bv32", lhs, rhs)
        next_pc_nid = b.ite("bv16", trap_cond, b.const("bv16", p), b.const("bv16", p + 1))
        next_sp_nid = b.ite("bv8", trap_cond, ctx.sp_nid, sp_m1)
        next_stack_nid = b.ite(
            "stack", trap_cond, ctx.stack_nid,
            _stack_push_i32(b, ctx.stack_nid, sp_m2, result),
        )
        trap_nid = b.ite("bv1", trap_cond, b.const("bv1", 1), ctx.trap_nid)

    elif op == "i32.and":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.and_("bv32", lhs, rhs)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.or":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.or_("bv32", lhs, rhs)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.xor":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.xor("bv32", lhs, rhs)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.shl":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        count = b.and_("bv32", rhs, b.const("bv32", 31))
        result = b.sll("bv32", lhs, count)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.shr_s":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        count = b.and_("bv32", rhs, b.const("bv32", 31))
        result = b.sra("bv32", lhs, count)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.shr_u":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        count = b.and_("bv32", rhs, b.const("bv32", 31))
        result = b.srl("bv32", lhs, count)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.rotl":
        # rotl(a, n) = (a << (n&31)) | (a >> (32 - (n&31)))
        # When count==0: srl(a, 32) is 0 in z3 theory, a>>0 in evaluator;
        # either way or(sll(a,0), ...) = a.
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        count = b.and_("bv32", rhs, b.const("bv32", 31))
        anti = b.sub("bv32", b.const("bv32", 32), count)
        left_part = b.sll("bv32", lhs, count)
        right_part = b.srl("bv32", lhs, anti)
        result = b.or_("bv32", left_part, right_part)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.rotr":
        # rotr(a, n) = (a >> (n&31)) | (a << (32 - (n&31)))
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        count = b.and_("bv32", rhs, b.const("bv32", 31))
        anti = b.sub("bv32", b.const("bv32", 32), count)
        right_part = b.srl("bv32", lhs, count)
        left_part = b.sll("bv32", lhs, anti)
        result = b.or_("bv32", right_part, left_part)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.eqz":
        # Unary: pop 1, compare with zero, push bv32 result (0 or 1).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        operand = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        cmp = _comparison_nid(b, Comparison.EQ, operand, b.const("bv32", 0))
        result = b.uext("bv32", cmp, 31)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m1, result)
        # sp unchanged — eqz replaces top of stack in-place

    elif op == "i32.eq":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.EQ, lhs, rhs), 31)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.ne":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.NE, lhs, rhs), 31)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.lt_s":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.LT, lhs, rhs), 31)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.lt_u":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.LTU, lhs, rhs), 31)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.gt_s":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.GT, lhs, rhs), 31)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.gt_u":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.GTU, lhs, rhs), 31)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.le_s":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.LE, lhs, rhs), 31)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.le_u":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.LEU, lhs, rhs), 31)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.ge_s":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.GE, lhs, rhs), 31)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.ge_u":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        lhs = _stack_pop_i32(b, ctx.stack_nid, sp_m2)
        result = b.uext("bv32", _comparison_nid(b, Comparison.GEU, lhs, rhs), 31)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i32.clz":
        # Unary: pop 1, count leading zeros, push bv32 result (0..32).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        operand = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        result = _clz_nid(b, operand)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m1, result)
        # sp unchanged — clz replaces top of stack in-place

    elif op == "i32.ctz":
        # Unary: pop 1, count trailing zeros, push bv32 result (0..32).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        operand = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        result = _ctz_nid(b, operand)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m1, result)

    elif op == "i32.popcnt":
        # Unary: pop 1, count set bits, push bv32 result (0..32).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        operand = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        result = _popcnt_nid(b, operand)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m1, result)

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
            top_val = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
            next_local_writes[k] = top_val
            next_sp_nid = sp_m1

    elif op == "local.tee":
        k = ins.imm[0]
        if k >= len(ctx.local_nids):
            next_pc_nid = b.const("bv16", p)
            trap_nid = b.const("bv1", 1)
        else:
            sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
            top_val = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
            next_local_writes[k] = top_val
            # sp unchanged; stack unchanged

    elif op == "i64.const":
        c = ins.imm[0] & 0xFFFFFFFFFFFFFFFF
        val_nid = b.const("bv64", c)
        next_stack_nid = b.write("stack", ctx.stack_nid, ctx.sp_nid, val_nid)
        next_sp_nid = b.add("bv8", ctx.sp_nid, b.const("bv8", 1))

    elif op == "i64.add":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv64", ctx.stack_nid, sp_m1)
        lhs = b.read("bv64", ctx.stack_nid, sp_m2)
        result = b.add("bv64", lhs, rhs)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i64.sub":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv64", ctx.stack_nid, sp_m1)
        lhs = b.read("bv64", ctx.stack_nid, sp_m2)
        result = b.sub("bv64", lhs, rhs)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i64.mul":
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        sp_m2 = _sp_sub(b, ctx.sp_nid, 2)
        rhs = b.read("bv64", ctx.stack_nid, sp_m1)
        lhs = b.read("bv64", ctx.stack_nid, sp_m2)
        result = b.mul("bv64", lhs, rhs)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m2, result)
        next_sp_nid = sp_m1

    elif op == "i64.extend_i32_u":
        # Pop i32 top-of-stack, zero-extend to i64, write back in-place (SP unchanged).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        operand = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        result64 = b.uext("bv64", operand, 32)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m1, result64)

    elif op == "i64.extend_i32_s":
        # Pop i32 top-of-stack, sign-extend to i64, write back in-place (SP unchanged).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        operand = _stack_pop_i32(b, ctx.stack_nid, sp_m1)
        result64 = b.sext("bv64", operand, 32)
        next_stack_nid = b.write("stack", ctx.stack_nid, sp_m1, result64)

    elif op == "i32.wrap_i64":
        # Pop i64 top-of-stack, truncate to i32 (low 32 bits), push i32 (SP unchanged).
        sp_m1 = _sp_sub(b, ctx.sp_nid, 1)
        operand64 = b.read("bv64", ctx.stack_nid, sp_m1)
        result32 = b.slice_("bv32", operand64, 31, 0)
        next_stack_nid = _stack_push_i32(b, ctx.stack_nid, sp_m1, result32)

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
        next_csp_nid=next_csp_nid,
        next_call_stack_nid=next_call_stack_nid,
    )


# ---------------------------------------------------------------------------
# header layer
# ---------------------------------------------------------------------------


def emit_header(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "header")
    for name in ("bv1", "bv4", "bv8", "bv16", "bv32", "bv64"):
        b.declare_sort(name)
    b.declare_array_sort("stack", "bv8", "bv64")
    b.declare_array_sort("call_stack", "bv4", "bv16")
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
        b.declare_array_sort("stack", "bv8", "bv64"),
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
    ctx.csp_nid = b.emit_no_sort(
        "state", b.declare_sort("bv4"), symbol="csp"
    )
    ctx.call_stack_nid = b.emit_no_sort(
        "state",
        b.declare_array_sort("call_stack", "bv4", "bv16"),
        symbol="call_stack",
    )
    _layer_end(b, "machine")


# ---------------------------------------------------------------------------
# library layer
# ---------------------------------------------------------------------------


def emit_library(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "library")

    entry_func_idx, _, _ = _resolve_entry(ctx)

    # Compute PC layout: entry function first, then other local functions in
    # module order.  func_entry_pcs maps func_idx → first global PC.
    current_pc = 0
    ordered_funcs: list[tuple[int, object]] = []  # (func_idx, code)

    entry_code = ctx.source.code_entry(entry_func_idx)
    ctx.func_entry_pcs[entry_func_idx] = current_pc
    ordered_funcs.append((entry_func_idx, entry_code))
    current_pc += len(entry_code.body)

    for fidx in range(ctx.source.total_func_count):
        if ctx.source.is_import(fidx) or fidx == entry_func_idx:
            continue
        code = ctx.source.code_entry(fidx)
        if code is None:
            continue
        ctx.func_entry_pcs[fidx] = current_pc
        ordered_funcs.append((fidx, code))
        current_pc += len(code.body)

    # Translate each function body into the shared PC space.
    all_instrs: list = []
    for fidx, code in ordered_funcs:
        func_start = ctx.func_entry_pcs[fidx]
        func_ends = _function_end_indices(code.body)
        for local_p, ins in enumerate(code.body):
            global_p = func_start + local_p
            all_instrs.append(ins)
            lowering = _lower_instr(b, ctx, global_p, ins, local_p in func_ends)
            ctx.lowerings[global_p] = lowering

    ctx.instrs = all_instrs
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

    # --- next_csp ---
    nxt = ctx.csp_nid
    for p in reversed(all_pcs):
        c = ctx.lowerings[p].next_csp_nid
        if c is not None:
            cond = b.eq(ctx.pc_nid, b.const("bv16", p))
            nxt = b.ite("bv4", cond, c, nxt)
    ctx.next_csp_expr = nxt

    # --- next_call_stack ---
    nxt = ctx.call_stack_nid
    for p in reversed(all_pcs):
        cs = ctx.lowerings[p].next_call_stack_nid
        if cs is not None:
            cond = b.eq(ctx.pc_nid, b.const("bv16", p))
            nxt = b.ite("call_stack", cond, cs, nxt)
    ctx.next_call_stack_expr = nxt

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

    bv4 = b.declare_sort("bv4")

    b.emit_no_sort("init", bv16, ctx.pc_nid, b.const("bv16", 0))
    b.emit_no_sort("init", bv8, ctx.sp_nid, b.const("bv8", 0))
    b.emit_no_sort("init", bv1, ctx.trap_nid, b.const("bv1", 0))
    b.emit_no_sort("init", bv1, ctx.halted_nid, b.const("bv1", 0))
    b.emit_no_sort("init", bv4, ctx.csp_nid, b.const("bv4", 0))

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

    bv4 = b.declare_sort("bv4")
    bv8 = b.declare_sort("bv8")
    bv16 = b.declare_sort("bv16")
    bv32 = b.declare_sort("bv32")
    bv1 = b.declare_sort("bv1")
    stack_sort = b.declare_array_sort("stack", "bv8", "bv64")
    call_stack_sort = b.declare_array_sort("call_stack", "bv4", "bv16")

    b.emit_no_sort("next", bv16, ctx.pc_nid, ctx.next_pc_expr)
    b.emit_no_sort("next", bv8, ctx.sp_nid, ctx.next_sp_expr)
    b.emit_no_sort("next", stack_sort, ctx.stack_nid, ctx.next_stack_expr)
    for k in range(ctx.n_locals):
        b.emit_no_sort("next", bv32, ctx.local_nids[k], ctx.next_local_exprs[k])
    b.emit_no_sort("next", bv1, ctx.trap_nid, ctx.next_trap_expr)
    b.emit_no_sort("next", bv1, ctx.halted_nid, ctx.next_halted_expr)
    b.emit_no_sort("next", bv4, ctx.csp_nid, ctx.next_csp_expr)
    b.emit_no_sort("next", call_stack_sort, ctx.call_stack_nid, ctx.next_call_stack_expr)

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
