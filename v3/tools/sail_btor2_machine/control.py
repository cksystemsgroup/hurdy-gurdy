"""The machine control harness: fetch/decode/dispatch/writeback/pc as ONE step.

This is the "next slice" that frames the per-instruction execute datapaths into
a whole-machine transition. It is built from a single shared *dispatch plan*
(``operand_kind`` + the ``InstrSpec`` decode fields + the ``EXEC`` IR trees),
lowered to:

  * z3 (``machine_step`` here) — the subject of the harness lemma in
    ``verify.py`` (proven equal to the INDEPENDENT ``reference_rv64.ref_step``);
  * BTOR2 (``emit_harness`` here) — so ``model.btor2`` is a real transition
    system, not just execute datapaths. Both lowerings consume the same plan,
    so the emitted model and the proven step cannot drift (the project's core
    no-drift principle, now extended to the control logic).

State model (pinned rv64 ALU-slice projection): regfile = z3/BTOR2 array
bv5->bv64, pc = bv64. x0 reads 0 and x0 writes are discarded. Every slice
instruction writes rd and advances pc by 4 (no control flow / mem in slice).
"""

from __future__ import annotations

import z3

from tools.sail_btor2_machine.isa import expr as E
from tools.sail_btor2_machine.isa import rv64_alu as ISA

XLEN = 64
RIDX = 5

# operand-selection kinds (shared single source for z3 + BTOR2)
RR, IMM_I, SH6, SH5, U_LUI, U_AUIPC = "rr", "imm_i", "sh6", "sh5", "lui", "auipc"

_SH6_NAMES = {"SLLI", "SRLI", "SRAI"}
_SH5_NAMES = {"SLLIW", "SRLIW", "SRAIW"}


def operand_kind(spec: ISA.InstrSpec) -> str:
    """Which operands this instruction's execute tree consumes — the single
    classification both the z3 proof and the BTOR2 emission rely on."""
    if spec.kind == "u-type":
        return U_LUI if spec.name == "LUI" else U_AUIPC
    if spec.kind == "reg-reg":
        return RR
    if spec.kind == "reg-imm":
        if spec.name in _SH6_NAMES:
            return SH6
        if spec.name in _SH5_NAMES:
            return SH5
        return IMM_I
    raise ValueError(f"unclassified spec kind {spec.kind} for {spec.name}")


# ---------------------------------------------------------------------------
# z3 lowering of the machine step (the harness-lemma subject)
# ---------------------------------------------------------------------------

def _f(iw, hi, lo):
    return z3.Extract(hi, lo, iw)


def machine_match(spec: ISA.InstrSpec, iw) -> z3.BoolRef:
    """The MACHINE decoder's recognition predicate, read from ``decode_map``
    (the InstrSpec fields) — the model under test."""
    conds = [_f(iw, 6, 0) == spec.opcode]
    if spec.funct3 is not None:
        conds.append(_f(iw, 14, 12) == spec.funct3)
    if spec.funct7 is not None:
        conds.append(_f(iw, 31, 25) == spec.funct7)
    if spec.funct7_hi is not None:
        conds.append(_f(iw, 31, 26) == spec.funct7_hi)
    return z3.And(*conds)


def _read(regfile, idx):
    return z3.If(idx == z3.BitVecVal(0, RIDX), z3.BitVecVal(0, XLEN), z3.Select(regfile, idx))


def _machine_result(spec: ISA.InstrSpec, iw, regfile, pc) -> z3.BitVecRef:
    """Evaluate this instruction's EXEC tree (the proven datapath) with the
    operands the decoder supplies, as z3."""
    kind = operand_kind(spec)
    rs1 = _f(iw, 19, 15)
    rs2 = _f(iw, 24, 20)
    imm_i = z3.SignExt(52, _f(iw, 31, 20))
    sh6 = z3.ZeroExt(58, _f(iw, 25, 20))
    sh5 = z3.ZeroExt(59, _f(iw, 24, 20))
    imm_u = z3.SignExt(32, z3.Concat(_f(iw, 31, 12), z3.BitVecVal(0, 12)))

    if kind == RR:
        env = {"a": _read(regfile, rs1), "b": _read(regfile, rs2)}
    elif kind == IMM_I:
        env = {"a": _read(regfile, rs1), "b": imm_i}
    elif kind == SH6:
        env = {"a": _read(regfile, rs1), "b": sh6}
    elif kind == SH5:
        env = {"a": _read(regfile, rs1), "b": sh5}
    elif kind == U_LUI:
        env = {"uimm": imm_u}
    elif kind == U_AUIPC:
        env = {"pc": pc, "uimm": imm_u}
    else:
        raise ValueError(kind)
    return E.to_z3(spec.execute, env)


def machine_decodes_in_slice(iw) -> z3.BoolRef:
    return z3.Or(*[machine_match(s, iw) for s in ISA.ALL_SPECS])


def _operand_env_nids(spec, nids):
    """Map an instruction's EXEC var leaves to already-emitted operand nids."""
    kind = operand_kind(spec)
    if kind == RR:
        return {"a": nids["a"], "b": nids["rs2v"]}
    if kind == IMM_I:
        return {"a": nids["a"], "b": nids["imm_i"]}
    if kind == SH6:
        return {"a": nids["a"], "b": nids["sh6"]}
    if kind == SH5:
        return {"a": nids["a"], "b": nids["sh5"]}
    if kind == U_LUI:
        return {"uimm": nids["imm_u"]}
    return {"pc": nids["pc"], "uimm": nids["imm_u"]}   # U_AUIPC


def emit_harness(bld: E.Btor2Builder, *, init_pc: int | None = None,
                 init_halted: int | None = None) -> dict:
    """Emit the BTOR2 fetch/decode/dispatch/writeback/pc transition system from
    the same decode plan the z3 ``machine_step`` uses. Returns key nids.

    Correctness of this emission is established by the harness LEMMA in
    ``verify.py`` (machine_step == reference step over the same plan): the
    emitted transition and the proven step share one source, so they cannot
    drift. State: pc (bv64), regfile (array bv5->bv64), mem (array bv64->bv8).

    ``init_pc`` / ``init_halted`` (used by the pono validation harness) emit
    initial-state constraints. pono requires an init value's nid be smaller
    than its state's, so the constants are emitted BEFORE the state lines."""
    s1, s5, s8, s32, s64 = (bld.sort(1), bld.sort(5), bld.sort(8),
                            bld.sort(32), bld.sort(64))
    s_rf = bld.raw("sort array {} {}", s5, s64)
    s_mem = bld.raw("sort array {} {}", s64, s8)

    init_pc_nid = None if init_pc is None else bld.emit("constd {} {}", s64, init_pc)
    init_h_nid = None if init_halted is None else bld.emit("constd {} {}", s1, init_halted)

    pc = bld.raw("state {} pc", s64)
    rf = bld.raw("state {} regfile", s_rf)
    mem = bld.raw("state {} mem", s_mem)
    halted = bld.raw("state {} halted", s1)

    if init_pc_nid is not None:
        bld.raw("init {} {} {}", s64, pc, init_pc_nid)
    if init_h_nid is not None:
        bld.raw("init {} {} {}", s1, halted, init_h_nid)

    # --- fetch: iw = mem[pc..pc+3], little-endian -------------------------
    c1, c2, c3 = (bld.emit("constd {} 1", s64), bld.emit("constd {} 2", s64),
                  bld.emit("constd {} 3", s64))
    b0 = bld.raw("read {} {} {}", s8, mem, pc)
    pc1 = bld.emit("add {} {} {}", s64, pc, c1); b1 = bld.raw("read {} {} {}", s8, mem, pc1)
    pc2 = bld.emit("add {} {} {}", s64, pc, c2); b2 = bld.raw("read {} {} {}", s8, mem, pc2)
    pc3 = bld.emit("add {} {} {}", s64, pc, c3); b3 = bld.raw("read {} {} {}", s8, mem, pc3)
    s16, s24 = bld.sort(16), bld.sort(24)
    hi16 = bld.emit("concat {} {} {}", s16, b3, b2)
    hi24 = bld.emit("concat {} {} {}", s24, hi16, b1)
    iw = bld.emit("concat {} {} {}", s32, hi24, b0)

    # --- decode fields ----------------------------------------------------
    def sl(hi, lo, w):
        return bld.emit("slice {} {} {} {}", bld.sort(w), iw, hi, lo)
    opcode, funct3 = sl(6, 0, 7), sl(14, 12, 3)
    funct7, funct7_hi = sl(31, 25, 7), sl(31, 26, 6)
    rd, rs1, rs2 = sl(11, 7, 5), sl(19, 15, 5), sl(24, 20, 5)
    imm_i = bld.emit("sext {} {} 52", s64, sl(31, 20, 12))
    sh6 = bld.emit("uext {} {} 58", s64, sl(25, 20, 6))
    sh5 = bld.emit("uext {} {} 59", s64, sl(24, 20, 5))
    z12 = bld.emit("constd {} 0", bld.sort(12))
    imm_u = bld.emit("sext {} {} 32", s64, bld.emit("concat {} {} {}", s32, sl(31, 12, 20), z12))

    # --- operand reads (x0 -> 0) -----------------------------------------
    z5, z64 = bld.emit("constd {} 0", s5), bld.emit("constd {} 0", s64)
    rs1_0 = bld.emit("eq {} {} {}", s1, rs1, z5)
    a = bld.emit("ite {} {} {} {}", s64, rs1_0, z64, bld.raw("read {} {} {}", s64, rf, rs1))
    rs2_0 = bld.emit("eq {} {} {}", s1, rs2, z5)
    rs2v = bld.emit("ite {} {} {} {}", s64, rs2_0, z64, bld.raw("read {} {} {}", s64, rf, rs2))
    nids = {"a": a, "rs2v": rs2v, "imm_i": imm_i, "sh6": sh6, "sh5": sh5,
            "imm_u": imm_u, "pc": pc}

    # --- dispatch: result + in-slice predicate ----------------------------
    def match(spec):
        conds = [bld.emit("eq {} {} {}", s1, opcode, bld.emit("constd {} {}", s7(), spec.opcode))]
        if spec.funct3 is not None:
            conds.append(bld.emit("eq {} {} {}", s1, funct3, bld.emit("constd {} {}", bld.sort(3), spec.funct3)))
        if spec.funct7 is not None:
            conds.append(bld.emit("eq {} {} {}", s1, funct7, bld.emit("constd {} {}", s7(), spec.funct7)))
        if spec.funct7_hi is not None:
            conds.append(bld.emit("eq {} {} {}", s1, funct7_hi, bld.emit("constd {} {}", bld.sort(6), spec.funct7_hi)))
        acc = conds[0]
        for c in conds[1:]:
            acc = bld.emit("and {} {} {}", s1, acc, c)
        return acc

    def s7():
        return bld.sort(7)

    result = z64
    in_slice = None
    for spec in reversed(ISA.ALL_SPECS):
        m = match(spec)
        bld.bindings = {k: v for k, v in _operand_env_nids(spec, nids).items()}
        # Lower each branch with a cleared expr-memo: the memo is keyed by
        # id(Expr), and freed clone objects can recycle ids across iterations,
        # which would alias one branch's nodes onto another. Clearing per branch
        # (the decode/operand nids are referenced by nid, not via the memo) keeps
        # each execute datapath independent.
        bld._memo.clear()
        rterm = bld.lower(E.clone(spec.execute))
        result = bld.emit("ite {} {} {} {}", s64, m, rterm, result)
    bld.bindings = {}
    bld._memo.clear()
    for spec in ISA.ALL_SPECS:
        in_slice = match(spec) if in_slice is None else bld.emit("or {} {} {}", s1, in_slice, match(spec))

    # --- writeback (x0 + in-slice gated) and pc/halted advance ------------
    rd_0 = bld.emit("eq {} {} {}", s1, rd, z5)
    do_write = bld.emit("and {} {} {}", s1, in_slice, bld.emit("not {} {}", s1, rd_0))
    written = bld.raw("write {} {} {} {}", s_rf, rf, rd, result)
    rf_next = bld.emit("ite {} {} {} {}", s_rf, do_write, written, rf)
    four = bld.emit("constd {} 4", s64)
    pc_next = bld.emit("ite {} {} {} {}", s64, in_slice, bld.emit("add {} {} {}", s64, pc, four), pc)
    one1 = bld.emit("constd {} 1", s1)
    halted_next = bld.emit("ite {} {} {} {}", s1, in_slice, halted, one1)   # trap on unknown

    bld.raw("next {} {} {}", s_rf, rf, rf_next)
    bld.raw("next {} {} {}", s64, pc, pc_next)
    bld.raw("next {} {} {}", s_mem, mem, mem)            # ALU slice: memory unchanged
    bld.raw("next {} {} {}", s1, halted, halted_next)
    return {"pc": pc, "regfile": rf, "mem": mem, "halted": halted,
            "iw": iw, "result": result, "in_slice": in_slice,
            "sorts": {"bv1": s1, "bv5": s5, "bv8": s8, "bv32": s32, "bv64": s64,
                      "regfile": s_rf, "mem": s_mem}}


def _match_concrete(spec: ISA.InstrSpec, iw: int) -> bool:
    if (iw & 0x7F) != spec.opcode:
        return False
    if spec.funct3 is not None and ((iw >> 12) & 0x7) != spec.funct3:
        return False
    if spec.funct7 is not None and ((iw >> 25) & 0x7F) != spec.funct7:
        return False
    if spec.funct7_hi is not None and ((iw >> 26) & 0x3F) != spec.funct7_hi:
        return False
    return True


def concrete_step(iw: int, regs: dict, pc: int):
    """Decode + execute ONE real instruction word concretely, via the machine's
    decode_map + EXEC trees. Returns (rd, value, next_pc), or None if ``iw`` is
    not a slice instruction. Used to validate the machine decoder against real
    Sail-emitted instruction words (``sail_cross.decode_vs_sail``)."""
    mask = (1 << XLEN) - 1
    spec = next((s for s in ISA.ALL_SPECS if _match_concrete(s, iw)), None)
    if spec is None:
        return None
    rd = (iw >> 7) & 0x1F
    rs1 = (iw >> 15) & 0x1F
    rs2 = (iw >> 20) & 0x1F
    a = 0 if rs1 == 0 else regs.get(rs1, 0) & mask
    b_reg = 0 if rs2 == 0 else regs.get(rs2, 0) & mask
    imm_i = ((iw >> 20) & 0xFFF)
    imm_i = imm_i | (~0xFFF if imm_i & 0x800 else 0)        # sign-extend 12 bits
    sh6 = (iw >> 20) & 0x3F
    sh5 = (iw >> 20) & 0x1F
    imm_u = (iw & 0xFFFFF000)
    imm_u = imm_u - (1 << 32) if imm_u & 0x80000000 else imm_u

    kind = operand_kind(spec)
    if kind == RR:
        env = {"a": a, "b": b_reg}
    elif kind == IMM_I:
        env = {"a": a, "b": imm_i & mask}
    elif kind == SH6:
        env = {"a": a, "b": sh6}
    elif kind == SH5:
        env = {"a": a, "b": sh5}
    elif kind == U_LUI:
        env = {"uimm": imm_u & mask}
    else:  # U_AUIPC
        env = {"pc": pc & mask, "uimm": imm_u & mask}

    z3env = {k: z3.BitVecVal(v, 64) for k, v in env.items()}
    value = z3.simplify(E.to_z3(spec.execute, z3env)).as_long() & mask
    return rd, value, (pc + 4) & mask


def machine_step(iw, regfile, pc):
    """Machine whole-instruction step as z3. Returns (regfile', pc').

    Decode is sourced from ``decode_map`` / ``InstrSpec``; execute from the
    ``EXEC`` IR trees (via ``expr.to_z3``). Mirrors the state framing of
    ``reference_rv64.ref_step`` so the harness lemma compares like for like."""
    rd = _f(iw, 11, 7)
    result = z3.BitVecVal(0, XLEN)
    for spec in reversed(ISA.ALL_SPECS):
        result = z3.If(machine_match(spec, iw),
                       _machine_result(spec, iw, regfile, pc), result)
    new_rf = z3.If(rd == z3.BitVecVal(0, RIDX), regfile, z3.Store(regfile, rd, result))
    new_pc = pc + z3.BitVecVal(4, XLEN)
    return new_rf, new_pc
