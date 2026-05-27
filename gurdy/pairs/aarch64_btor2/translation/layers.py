"""Per-layer emission for the aarch64-btor2 pair.

Adapted from gurdy/pairs/riscv_btor2/translation/layers.py.
AArch64-specific differences:
- 31 GPRs x0–x30 (all real, writable; x0 is NOT a constant zero).
- Separate ``sp`` state (bv64) distinct from the GPR file.
- ``nzcv`` state (bv4) updated by flag-setting instructions.
- All instructions are 4 bytes (no compressed). seq PC += 4.
- R31 = XZR (DP context) or SP (memory context) — resolved at decode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from gurdy.core.annotation.sidecar import AnnotationEmitter
from gurdy.core.annotation.types import Role
from gurdy.pairs.aarch64_btor2.source.decoder import Decoded, decode
from gurdy.pairs.aarch64_btor2.source.loader import AArch64Source
from gurdy.pairs.aarch64_btor2.spec import (
    AnalysisScope,
    Aarch64Btor2Spec,
    Comparison,
    CycleInvariant,
    MemoryInit,
    NZCVInit,
    Property,
    RegisterInit,
    SPInit,
)
from gurdy.pairs.aarch64_btor2.translation.builder import Builder
from gurdy.pairs.aarch64_btor2.translation.library import (
    LoweringResult,
    RegSnapshot,
    lower,
)


LAYER_NAMES = (
    "header",
    "machine",
    "library",
    "dispatch",
    "init",
    "constraint",
    "volatile",
    "bad",
    "binding",
    "havoc",
)


@dataclass
class EmitContext:
    spec: Aarch64Btor2Spec
    source: AArch64Source
    builder: Builder
    annotator: AnnotationEmitter
    # populated by emit_machine
    reg_state_nids: dict[int, int] = field(default_factory=dict)
    """x0–x30 → state nid."""
    sp_nid: int = 0
    pc_nid: int = 0
    nzcv_nid: int = 0
    mem_nid: int = 0
    halted_nid: int = 0
    nondet_nid: int = 0
    # populated by emit_library
    lowerings: dict[int, LoweringResult] = field(default_factory=dict)
    decoded: list[Decoded] = field(default_factory=list)
    # populated by emit_dispatch
    next_pc_expr: int = 0
    next_reg_expr: dict[int, int] = field(default_factory=dict)
    next_sp_expr: int = 0
    next_nzcv_expr: int = 0
    next_mem_expr: int = 0
    next_halt_expr: int = 0
    dual_role_constraint_nids: dict[int, int] = field(default_factory=dict)


def _layer_marker(b: Builder, name: str) -> None:
    b.comment(f":layer:{name}:begin")


def _layer_end(b: Builder, name: str) -> None:
    b.comment(f":layer:{name}:end")


def _scope_pcs(spec: Aarch64Btor2Spec, source: AArch64Source):
    from gurdy.pairs.aarch64_btor2.source.elf import FunctionRange
    funcs: list[FunctionRange] = []
    entry = source.function(spec.scope.entry_function)
    if entry is not None:
        funcs.append(entry)
    for c in spec.scope.included_callees:
        f = source.function(c)
        if f is not None and f not in funcs:
            funcs.append(f)
    return funcs


# ---------------------------------------------------------------------------
# header
# ---------------------------------------------------------------------------


def emit_header(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "header")
    b.comment(" sorts ")
    for name in ("bv1", "bv4", "bv8", "bv16", "bv32", "bv64"):
        nid = b.declare_sort(name)
        ctx.annotator.emit("header", nid, Role.SORT, source_mapping={"sort_name": name})
    mem_sort = b.declare_array_sort("mem", "bv64", "bv8")
    ctx.annotator.emit("header", mem_sort, Role.SORT, source_mapping={"sort_name": "mem"})
    _layer_end(b, "header")


# ---------------------------------------------------------------------------
# machine
# ---------------------------------------------------------------------------


def emit_machine(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "machine")
    b.comment(" registers x0..x30, sp, pc, nzcv, mem, halted, nondet ")
    for i in range(31):
        nid = b.emit_no_sort("state", b.declare_sort("bv64"), symbol=f"reg_x{i}")
        ctx.reg_state_nids[i] = nid
        ctx.annotator.emit("machine", nid, Role.STATE, source_mapping={"register": i})
    sp_nid = b.emit_no_sort("state", b.declare_sort("bv64"), symbol="sp")
    ctx.sp_nid = sp_nid
    ctx.annotator.emit("machine", sp_nid, Role.STATE, source_mapping={"role": "sp"})
    pc_nid = b.emit_no_sort("state", b.declare_sort("bv64"), symbol="pc")
    ctx.pc_nid = pc_nid
    ctx.annotator.emit("machine", pc_nid, Role.STATE, source_mapping={"role": "pc"})
    nzcv_nid = b.emit_no_sort("state", b.declare_sort("bv4"), symbol="nzcv")
    ctx.nzcv_nid = nzcv_nid
    ctx.annotator.emit("machine", nzcv_nid, Role.STATE, source_mapping={"role": "nzcv"})
    mem_nid = b.emit_no_sort("state", b.declare_array_sort("mem", "bv64", "bv8"), symbol="mem")
    ctx.mem_nid = mem_nid
    ctx.annotator.emit("machine", mem_nid, Role.STATE, source_mapping={"role": "mem"})
    halted_nid = b.emit_no_sort("state", b.declare_sort("bv1"), symbol="halted")
    ctx.halted_nid = halted_nid
    ctx.annotator.emit("machine", halted_nid, Role.STATE, source_mapping={"role": "halted"})
    nondet_nid = b.emit_no_sort("input", b.declare_sort("bv64"), symbol="nondet")
    ctx.nondet_nid = nondet_nid
    ctx.annotator.emit("machine", nondet_nid, Role.INPUT, source_mapping={"role": "nondet"})
    _layer_end(b, "machine")


# ---------------------------------------------------------------------------
# library + dispatch
# ---------------------------------------------------------------------------


def _decode_function(source: AArch64Source, fn) -> list[Decoded]:
    bytemap = source.binary.loadable_byte_map()
    decoded: list[Decoded] = []
    pc = fn.start
    while pc < fn.end:
        b0 = bytemap.get(pc)
        b1 = bytemap.get(pc + 1)
        b2 = bytemap.get(pc + 2)
        b3 = bytemap.get(pc + 3)
        if b0 is None or b1 is None or b2 is None or b3 is None:
            break
        word = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
        d = decode(word, pc)
        if d is not None:
            decoded.append(d)
        pc += 4
    return decoded


def emit_library(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "library")
    b.comment(" per-instruction lowerings ")
    funcs = _scope_pcs(ctx.spec, ctx.source)
    for fn in funcs:
        ds = _decode_function(ctx.source, fn)
        for d in ds:
            ctx.decoded.append(d)
            xzr = b.const("bv64", 0)
            snap = RegSnapshot(nids=ctx.reg_state_nids, sp_nid=ctx.sp_nid, xzr_nid=xzr)
            res = lower(b, d, snap, ctx.pc_nid, ctx.mem_nid, ctx.nzcv_nid)
            ctx.lowerings[d.pc] = res
            ctx.annotator.emit(
                "library", res.next_pc, Role.EXPRESSION,
                source_mapping={"pc": d.pc, "mnemonic": d.mnemonic, "field": "next_pc"},
            )
    _layer_end(b, "library")


def emit_dispatch(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "dispatch")
    b.comment(" PC-keyed dispatch ")
    funcs = _scope_pcs(ctx.spec, ctx.source)
    in_scope_pcs: set[int] = set()
    for fn in funcs:
        for d in ctx.decoded:
            if fn.start <= d.pc < fn.end:
                in_scope_pcs.add(d.pc)

    pc_in_scope = _scope_predicate(b, ctx.pc_nid, sorted(in_scope_pcs))
    ctx.annotator.emit("dispatch", pc_in_scope, Role.DISPATCH, source_mapping={"role": "in_scope"})

    # next_pc
    next_pc = ctx.pc_nid  # self-loop for out-of-scope
    for pc in sorted(in_scope_pcs, reverse=True):
        cond = b.eq(ctx.pc_nid, b.const("bv64", pc))
        next_pc = b.ite("bv64", cond, ctx.lowerings[pc].next_pc, next_pc)
    ctx.next_pc_expr = next_pc
    ctx.annotator.emit("dispatch", next_pc, Role.DISPATCH, source_mapping={"role": "next_pc"})

    # per-register next
    for reg in range(31):
        cur = ctx.reg_state_nids[reg]
        writers = [
            (pc, ctx.lowerings[pc].reg_writes[reg])
            for pc in sorted(in_scope_pcs)
            if reg in ctx.lowerings[pc].reg_writes
        ]
        next_val = cur
        for pc, val in reversed(writers):
            cond = b.eq(ctx.pc_nid, b.const("bv64", pc))
            next_val = b.ite("bv64", cond, val, next_val)
        ctx.next_reg_expr[reg] = next_val
        ctx.annotator.emit(
            "dispatch", next_val, Role.DISPATCH,
            source_mapping={"role": "next_reg", "register": reg},
        )

    # next SP
    cur_sp = ctx.sp_nid
    next_sp = cur_sp
    for pc in sorted(in_scope_pcs, reverse=True):
        s = ctx.lowerings[pc].sp_next
        if s is None:
            continue
        cond = b.eq(ctx.pc_nid, b.const("bv64", pc))
        next_sp = b.ite("bv64", cond, s, next_sp)
    ctx.next_sp_expr = next_sp
    ctx.annotator.emit("dispatch", next_sp, Role.DISPATCH, source_mapping={"role": "next_sp"})

    # next NZCV
    cur_nzcv = ctx.nzcv_nid
    next_nzcv = cur_nzcv
    for pc in sorted(in_scope_pcs, reverse=True):
        n = ctx.lowerings[pc].nzcv_next
        if n is None:
            continue
        cond = b.eq(ctx.pc_nid, b.const("bv64", pc))
        next_nzcv = b.ite("bv4", cond, n, next_nzcv)
    ctx.next_nzcv_expr = next_nzcv
    ctx.annotator.emit("dispatch", next_nzcv, Role.DISPATCH, source_mapping={"role": "next_nzcv"})

    # next mem
    cur_mem = ctx.mem_nid
    next_mem = cur_mem
    for pc in sorted(in_scope_pcs, reverse=True):
        m = ctx.lowerings[pc].mem_next
        if m is None:
            continue
        cond = b.eq(ctx.pc_nid, b.const("bv64", pc))
        next_mem = b.ite("mem", cond, m, next_mem)
    ctx.next_mem_expr = next_mem
    ctx.annotator.emit("dispatch", next_mem, Role.DISPATCH, source_mapping={"role": "next_mem"})

    # next halted (sticky: once set, stays set)
    halted = ctx.halted_nid
    next_halt = halted
    for pc in sorted(in_scope_pcs, reverse=True):
        h = ctx.lowerings[pc].halt_next
        if h is None:
            continue
        cond = b.eq(ctx.pc_nid, b.const("bv64", pc))
        next_halt = b.ite("bv1", cond, h, next_halt)
    ctx.next_halt_expr = next_halt

    _layer_end(b, "dispatch")


def _scope_predicate(b: Builder, pc_nid: int, pcs: list[int]) -> int:
    if not pcs:
        return b.const("bv1", 0)
    pred = b.eq(pc_nid, b.const("bv64", pcs[0]))
    for pc in pcs[1:]:
        pred = b.or_("bv1", pred, b.eq(pc_nid, b.const("bv64", pc)))
    return pred


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def emit_init(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "init")
    b.comment(" initial state ")
    funcs = _scope_pcs(ctx.spec, ctx.source)
    if funcs:
        entry_pc = funcs[0].start
        init_pc_const = b.const("bv64", entry_pc)
        b.emit_no_sort("init", b.declare_sort("bv64"), ctx.pc_nid, init_pc_const)
        ctx.annotator.emit(
            "init", init_pc_const, Role.INIT,
            source_mapping={"role": "pc_init", "pc": entry_pc},
        )
    for asm in ctx.spec.assumptions:
        if isinstance(asm, RegisterInit):
            _emit_register_init(ctx, asm)
        elif isinstance(asm, SPInit):
            _emit_sp_init(ctx, asm)
        elif isinstance(asm, NZCVInit):
            _emit_nzcv_init(ctx, asm)
        elif isinstance(asm, MemoryInit):
            _emit_memory_init(ctx, asm)
    _layer_end(b, "init")


def _comparison_op(b: Builder, op: Comparison, a: int, c: int) -> int:
    if op == Comparison.EQ:
        return b.eq(a, c)
    if op == Comparison.NE:
        return b.neq(a, c)
    if op == Comparison.LT:
        return b.slt(a, c)
    if op == Comparison.LE:
        return b.emit("slte", "bv1", a, c)
    if op == Comparison.GT:
        return b.sgt(a, c)
    if op == Comparison.GE:
        return b.emit("sgte", "bv1", a, c)
    if op == Comparison.LTU:
        return b.ult(a, c)
    if op == Comparison.LEU:
        return b.emit("ulte", "bv1", a, c)
    if op == Comparison.GTU:
        return b.emit("ugt", "bv1", a, c)
    if op == Comparison.GEU:
        return b.uge(a, c)
    raise ValueError(f"unsupported comparison: {op}")


def _emit_register_init(ctx: EmitContext, asm: RegisterInit) -> None:
    b = ctx.builder
    val = b.const("bv64", asm.value & 0xFFFFFFFFFFFFFFFF)
    if asm.op == Comparison.EQ:
        b.emit_no_sort("init", b.declare_sort("bv64"), ctx.reg_state_nids[asm.register], val)
    else:
        cond = _comparison_op(b, asm.op, ctx.reg_state_nids[asm.register], val)
        b.emit_no_sort("constraint", cond)
    ctx.annotator.emit(
        "init", val, Role.INIT,
        source_mapping={"role": "register_init", "register": asm.register, "op": asm.op.value},
    )


def _emit_sp_init(ctx: EmitContext, asm) -> None:
    b = ctx.builder
    val = b.const("bv64", asm.value & 0xFFFFFFFFFFFFFFFF)
    if asm.op == Comparison.EQ:
        b.emit_no_sort("init", b.declare_sort("bv64"), ctx.sp_nid, val)
    else:
        cond = _comparison_op(b, asm.op, ctx.sp_nid, val)
        b.emit_no_sort("constraint", cond)
    ctx.annotator.emit("init", val, Role.INIT, source_mapping={"role": "sp_init"})


def _emit_nzcv_init(ctx: EmitContext, asm: NZCVInit) -> None:
    b = ctx.builder
    val = b.const("bv4", asm.value & 0xF)
    if asm.op == Comparison.EQ:
        b.emit_no_sort("init", b.declare_sort("bv4"), ctx.nzcv_nid, val)
    else:
        cond = _comparison_op(b, asm.op, ctx.nzcv_nid, val)
        b.emit_no_sort("constraint", cond)
    ctx.annotator.emit("init", val, Role.INIT, source_mapping={"role": "nzcv_init"})


def _emit_memory_init(ctx: EmitContext, asm: MemoryInit) -> None:
    b = ctx.builder
    addr_nid = b.const("bv64", asm.address)
    n = asm.width
    if n == 1:
        cur = b.read("bv8", ctx.mem_nid, addr_nid)
    else:
        parts = []
        for i in range(n):
            off = b.add("bv64", addr_nid, b.const("bv64", i))
            parts.append(b.read("bv8", ctx.mem_nid, off))
        cur = parts[0]
        for i in range(1, n):
            cur = b.concat(f"bv{8*(i+1)}", parts[i], cur)
    target = b.const(f"bv{8*n}", asm.value & ((1 << (8*n)) - 1))
    cond = _comparison_op(b, asm.op, cur, target)
    b.emit_no_sort("constraint", cond)
    ctx.annotator.emit(
        "init", cond, Role.INIT,
        source_mapping={"role": "memory_init", "address": asm.address,
                        "width": asm.width, "op": asm.op.value},
    )


# ---------------------------------------------------------------------------
# constraint
# ---------------------------------------------------------------------------


def emit_constraint(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "constraint")
    b.comment(" cycle invariants ")
    from gurdy.pairs.aarch64_btor2.translation.exprs import ExprContext, parse_and_emit
    expr_ctx = ExprContext(
        builder=b, reg_nid=ctx.reg_state_nids,
        sp_nid=ctx.sp_nid, pc_nid=ctx.pc_nid,
        nzcv_nid=ctx.nzcv_nid, mem_nid=ctx.mem_nid,
    )
    for asm in ctx.spec.assumptions:
        if isinstance(asm, CycleInvariant):
            nid = parse_and_emit(asm.expression, expr_ctx)
            b.emit_no_sort("constraint", nid)
            if asm.dual_role:
                ctx.dual_role_constraint_nids[id(asm)] = nid
            ctx.annotator.emit(
                "constraint", nid, Role.CONSTRAINT,
                source_mapping={"provenance": asm.provenance, "dual_role": asm.dual_role},
            )
    _layer_end(b, "constraint")


# ---------------------------------------------------------------------------
# volatile
# ---------------------------------------------------------------------------


def emit_volatile(ctx: EmitContext) -> None:
    b = ctx.builder
    from gurdy.pairs.aarch64_btor2.spec import BranchPin, CycleInvariant
    branch_pins = [a for a in ctx.spec.assumptions if isinstance(a, BranchPin)]
    dual_role_invs = [
        a for a in ctx.spec.assumptions
        if isinstance(a, CycleInvariant) and a.dual_role
    ]
    if not branch_pins and not dual_role_invs:
        return

    _layer_marker(b, "volatile")
    b.comment(" volatile: branch pins and dual-role checks ")

    step_count_nid: int | None = None
    if branch_pins:
        bv64 = b.declare_sort("bv64")
        step_count_nid = b.emit_no_sort("state", bv64, symbol="step_count")
        ctx.annotator.emit("volatile", step_count_nid, Role.STATE,
                           source_mapping={"role": "step_count"})
        zero64 = b.const("bv64", 0)
        b.emit_no_sort("init", bv64, step_count_nid, zero64)
        one64 = b.const("bv64", 1)
        next_step = b.add("bv64", step_count_nid, one64)
        b.emit_no_sort("next", bv64, step_count_nid, next_step)

    for pin in branch_pins:
        if pin.pc not in ctx.lowerings or ctx.lowerings[pin.pc].branch_cond is None:
            ctx.annotator.emit("volatile", 0, Role.OTHER,
                               source_mapping={"role": "branch_pin_soft_noop", "pc": pin.pc})
            continue
        assert step_count_nid is not None
        cond_nid = ctx.lowerings[pin.pc].branch_cond
        assert cond_nid is not None
        step_const = b.const("bv64", pin.step)
        pc_const = b.const("bv64", pin.pc)
        step_ne = b.neq(step_count_nid, step_const)
        pc_ne = b.neq(ctx.pc_nid, pc_const)
        cond_target = b.const("bv1", 1 if pin.taken else 0)
        cond_eq = b.eq(cond_nid, cond_target)
        disj = b.or_("bv1", b.or_("bv1", step_ne, pc_ne), cond_eq)
        b.emit_no_sort("constraint", disj)
        ctx.annotator.emit("volatile", disj, Role.CONSTRAINT,
                           source_mapping={"role": "branch_pin", "step": pin.step,
                                           "pc": pin.pc, "taken": pin.taken})

    for asm in dual_role_invs:
        paired_nid = ctx.dual_role_constraint_nids.get(id(asm))
        if paired_nid is None:
            continue
        neg_nid = b.not_("bv1", paired_nid)
        b.emit_no_sort("bad", neg_nid)
        ctx.annotator.emit("volatile", neg_nid, Role.BAD,
                           source_mapping={"role": "dual_role_check"})

    _layer_end(b, "volatile")


# ---------------------------------------------------------------------------
# bad
# ---------------------------------------------------------------------------


def emit_bad(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "bad")
    b.comment(" bad expression ")
    from gurdy.pairs.aarch64_btor2.translation.exprs import ExprContext, parse_and_emit
    expr_ctx = ExprContext(
        builder=b, reg_nid=ctx.reg_state_nids,
        sp_nid=ctx.sp_nid, pc_nid=ctx.pc_nid,
        nzcv_nid=ctx.nzcv_nid, mem_nid=ctx.mem_nid,
    )
    nid = parse_and_emit(ctx.spec.property.expression, expr_ctx)
    if ctx.spec.property.negate:
        nid = b.not_("bv1", nid)
    b.emit_no_sort("bad", nid)
    ctx.annotator.emit("bad", nid, Role.BAD, source_mapping={"role": "bad"})
    _layer_end(b, "bad")


# ---------------------------------------------------------------------------
# binding
# ---------------------------------------------------------------------------


def emit_binding(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "binding")
    b.comment(" wire next clauses ")
    bv64 = b.declare_sort("bv64")
    # PC
    b.emit_no_sort("next", bv64, ctx.pc_nid, ctx.next_pc_expr)
    ctx.annotator.emit("binding", ctx.pc_nid, Role.BINDING, source_mapping={"role": "next_pc"})
    # GPRs x0–x30
    for reg in range(31):
        b.emit_no_sort("next", bv64, ctx.reg_state_nids[reg], ctx.next_reg_expr[reg])
        ctx.annotator.emit("binding", ctx.reg_state_nids[reg], Role.BINDING,
                           source_mapping={"role": "next_reg", "register": reg})
    # SP
    b.emit_no_sort("next", bv64, ctx.sp_nid, ctx.next_sp_expr)
    ctx.annotator.emit("binding", ctx.sp_nid, Role.BINDING, source_mapping={"role": "next_sp"})
    # NZCV
    bv4 = b.declare_sort("bv4")
    b.emit_no_sort("next", bv4, ctx.nzcv_nid, ctx.next_nzcv_expr)
    ctx.annotator.emit("binding", ctx.nzcv_nid, Role.BINDING, source_mapping={"role": "next_nzcv"})
    # mem
    mem_sort = b.declare_array_sort("mem", "bv64", "bv8")
    b.emit_no_sort("next", mem_sort, ctx.mem_nid, ctx.next_mem_expr)
    ctx.annotator.emit("binding", ctx.mem_nid, Role.BINDING, source_mapping={"role": "next_mem"})
    # halted
    bv1 = b.declare_sort("bv1")
    b.emit_no_sort("next", bv1, ctx.halted_nid, ctx.next_halt_expr)
    ctx.annotator.emit("binding", ctx.halted_nid, Role.BINDING, source_mapping={"role": "next_halted"})
    _layer_end(b, "binding")


# ---------------------------------------------------------------------------
# havoc
# ---------------------------------------------------------------------------


def emit_havoc(ctx: EmitContext) -> None:
    b = ctx.builder
    _layer_marker(b, "havoc")
    havoc = ctx.spec.analysis.havoc_registers
    sp_havoc = getattr(ctx.spec.analysis, "havoc_sp", False)
    if not havoc and not sp_havoc:
        _layer_end(b, "havoc")
        return
    b.comment(" havoc register inputs ")
    for r in sorted(havoc):
        if r not in range(31):
            continue
        nid = b.emit_no_sort("input", b.declare_sort("bv64"), symbol=f"havoc_x{r}")
        next_expr = ctx.next_reg_expr[r]
        cond = b.eq(next_expr, nid)
        b.emit_no_sort("constraint", cond)
        ctx.annotator.emit("havoc", nid, Role.HAVOC, source_mapping={"register": r})
    if sp_havoc:
        nid = b.emit_no_sort("input", b.declare_sort("bv64"), symbol="havoc_sp")
        cond = b.eq(ctx.next_sp_expr, nid)
        b.emit_no_sort("constraint", cond)
        ctx.annotator.emit("havoc", nid, Role.HAVOC, source_mapping={"register": "sp"})
    _layer_end(b, "havoc")


__all__ = [
    "EmitContext", "LAYER_NAMES",
    "emit_header", "emit_machine", "emit_library", "emit_dispatch",
    "emit_init", "emit_constraint", "emit_volatile",
    "emit_bad", "emit_binding", "emit_havoc",
]
