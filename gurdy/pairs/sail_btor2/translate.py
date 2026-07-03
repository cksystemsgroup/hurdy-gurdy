"""sail -> BTOR2 translator (pairs/sail-btor2).

Lowers a Sail program (a model applied to a program) into a BTOR2 transition
system, dispatching on the Sail object's ``isa`` field:

- **RISC-V** (the default, no ``isa`` key — byte-for-byte unchanged): the state
  skeleton and PC-keyed ITE dispatch are the same shape as ``riscv-btor2``, but
  each instruction's write-back datapath is lowered from the Sail-derived
  ``Expr`` execute tree (``languages/sail/rv64.EXEC``) via ``expr.lower`` —
  *not* from the hand-written per-opcode rules of ``riscv-btor2``. That
  independence is what lets the indirect RISC-V→BTOR2 route cross-check the
  direct one (PATHS.md §4-5). Scope: the ALU + control-flow + load/store slice
  (``rv64.decode``) + ECALL/EBREAK (halt); data memory is an
  ``Array bv64 bv8``. Other opcodes hard-abort with ``Unsupported``.

- **AArch64** (``isa == "aarch64"``, the additive ``0.2`` arm): an A64 Sail
  object (as ``aarch64-sail`` emits) is lowered to a BTOR2 system over
  ``aarch64-btor2``'s state space — ``pc``, ``x0``–``x30``, ``sp``, ``nzcv``
  (bv4, ``N=3,Z=2,C=1,V=0``), ``halted``, and, when the program touches memory,
  ``mem`` (an ``Array bv64 bv8``, little-endian) with the observable window
  ``m0``–``m{MEM_WINDOW-1}`` — completing the *second* AArch64→BTOR2 route.
  Decoding is the shared A64 gate (``decode_insn_v6``, one source of truth;
  out-of-scope words hard-abort), and every per-instruction datapath — the ALU
  result (incl. the 32-bit W zero-extend), the ``SUBS``/``ADDS`` NZCV packs,
  the ``B.cond`` condition predicate, and the LE load/store byte assembly — is
  lowered from the *same* Sail-derived ``Expr`` trees the Sail interpreter's
  A64 arm evaluates (``languages/sail/aarch64``) via ``expr.lower``, NOT from
  ``aarch64-btor2``'s hand-built node emission; the independence of the two
  routes is the load-bearing property. An optional ``{"reg_eq": [field, val]}``
  property (field 31 = ``sp``) lowers to a ``bad`` line, mirroring
  ``aarch64-btor2``, so ``btor2-smtlib`` can decide it along this route too.

Deterministic in the program.
"""

from __future__ import annotations

import json
from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.build import Builder
from ...languages.sail import expr
from ...languages.sail.rv64 import MASK64, decode, instruction_stream, operands

NREG = 32


def _unwrap(program: Any) -> dict:
    """Accept the sail-program dict directly, a predecessor's JSON bytes (from
    ``riscv-sail``), or a ``{"sail": ...}`` wrapper."""
    if isinstance(program, (bytes, bytearray, str)):
        text = program.decode() if isinstance(program, (bytes, bytearray)) else program
        program = json.loads(text)
    if "sail" in program:
        program = program["sail"]
    return program


def _is_ecall(instr: int) -> bool:
    return (instr & 0x7F) == 0x73 and ((instr >> 12) & 0x7) == 0 and (instr >> 20) in (0, 1)


def _uses_memory(words: list[int]) -> bool:
    return any((w & 0x7F) in (0x03, 0x23) for w in words)


def _load_nodes(b: Builder, mem: int, addr: int, n: int) -> tuple[int, int]:
    res = b.read(8, mem, addr)
    w = 8
    for i in range(1, n):
        byte = b.read(8, mem, b.op2("add", 64, addr, b.constd(64, i)))
        res = b.op2("concat", w + 8, byte, res)
        w += 8
    return res, w


def _store_nodes(b: Builder, mem: int, addr: int, value: int, n: int) -> int:
    cur = mem
    for i in range(n):
        byte = b.slice(value, 8 * i + 7, 8 * i)
        a_i = addr if i == 0 else b.op2("add", 64, addr, b.constd(64, i))
        cur = b.write(64, 8, cur, a_i, byte)
    return cur


def _effect(instr: int, addr: int, length: int, b: Builder, regs: dict[int, int],
            zero64: int, mem: int | None):
    """Return (next_pc_node, {rd: value_node}, halts, mem_next_or_None)."""
    def c64(v: int) -> int:
        return b.constd(64, v & MASK64)

    fall = c64(addr + length)
    if _is_ecall(instr):
        return fall, {}, True, None
    d = decode(instr)
    if d is None:
        raise Unsupported("sail-btor2", f"opcode=0x{instr & 0x7F:02x}")

    bnd = {
        vn: ((zero64 if v == 0 else regs[v]) if k == "reg" else c64(v))
        for vn, (k, v) in operands(d, addr).items()
    }
    if d.kind == "alu":
        val = expr.lower(b, d.execute, bnd)
        return fall, ({d.rd: val} if d.rd != 0 else {}), False, None
    if d.kind == "branch":
        cond = expr.lower(b, d.cond, bnd)
        return b.ite(64, cond, c64(addr + d.offset), fall), {}, False, None
    if d.kind == "jal":
        return c64(addr + d.offset), ({d.rd: fall} if d.rd != 0 else {}), False, None
    if d.kind == "jalr":
        return expr.lower(b, d.target, bnd), ({d.rd: fall} if d.rd != 0 else {}), False, None
    if d.kind == "load":
        assert mem is not None
        raw, w = _load_nodes(b, mem, expr.lower(b, d.addr, bnd), d.nbytes)
        val = raw if w == 64 else (b.sext(64, raw, 64 - w) if d.signed else b.uext(64, raw, 64 - w))
        return fall, ({d.rd: val} if d.rd != 0 else {}), False, None
    if d.kind == "store":
        assert mem is not None
        cur = _store_nodes(b, mem, expr.lower(b, d.addr, bnd), regs[d.b_reg], d.nbytes)
        return fall, {}, False, cur
    return fall, {}, False, None   # fence


def translate(program: Any) -> bytes:
    prog = _unwrap(program)
    # Additive AArch64 arm: a Sail object tagged isa=aarch64 lowers via the A64
    # Expr semantics; the RISC-V path below is the untouched default (no isa key).
    if prog.get("isa") == "aarch64":
        return _translate_aarch64(prog)
    words = prog["words"]
    entry = int(prog.get("entry", 0))
    init_regs = {int(k): int(v) for k, v in prog.get("init_regs", {}).items()}

    b = Builder()
    pc = b.state(64, "pc")
    regs = {r: b.state(64, f"x{r}") for r in range(1, NREG)}
    halted = b.state(1, "halted")
    zero64 = b.zero(64)
    mem = b.state_array(64, 8, "mem") if _uses_memory(words) else None

    b.init(pc, b.constd(64, entry))
    for r in range(1, NREG):
        b.init(regs[r], b.constd(64, init_regs.get(r, 0) & MASK64))
    b.init(halted, b.zero(1))

    not_halted = b.op1("not", 1, halted)
    next_pc, next_regs, next_halted, next_mem = pc, dict(regs), halted, mem
    for addr, instr, length in instruction_stream(prog):
        eff_pc, writes, halts, mem_next = _effect(instr, addr, length, b, regs, zero64, mem)
        at = b.op2("eq", 1, pc, b.constd(64, addr))
        active = b.op2("and", 1, at, not_halted)
        next_pc = b.ite(64, active, eff_pc, next_pc)
        for rd, val in writes.items():
            next_regs[rd] = b.ite(64, active, val, next_regs[rd])
        if halts:
            next_halted = b.ite(1, active, b.one(1), next_halted)
        if mem_next is not None:
            next_mem = b.ite_array(64, 8, active, mem_next, next_mem)

    b.next(pc, next_pc)
    for r in range(1, NREG):
        b.next(regs[r], next_regs[r])
    b.next(halted, next_halted)
    if mem is not None:
        b.next_array(mem, next_mem)

    prop = prog.get("property")
    if prop and "reg_eq" in prop:
        reg, val = prop["reg_eq"]
        src = zero64 if reg == 0 else regs[reg]
        b.bad(b.op2("eq", 1, src, b.constd(64, int(val) & MASK64)))

    return b.to_text().encode("utf-8")


# ---------------------------------------------------------------------------
# The AArch64 arm (additive, translator 0.2): lower an ``isa=aarch64`` Sail
# object — the artifact ``aarch64-sail`` emits — to a BTOR2 transition system
# semantically equivalent to ``aarch64-btor2``'s (same state space, same
# observables incl. the m0..m{MEM_WINDOW-1} memory window and nzcv, same halt
# behavior, same reg_eq property lowering with field 31 = sp). Every
# per-instruction datapath is ``expr.lower``-ed from the Sail-derived ``Expr``
# trees of ``languages/sail/aarch64`` — the SAME trees the shared Sail
# interpreter's A64 arm evaluates — so this route's semantics derive from the
# Sail model, independently of ``aarch64-btor2``'s hand-built lowering.
# ---------------------------------------------------------------------------

_A64_BYTE = 8   # the memory element width (a byte); the array is ``Array bv64 bv8``.


def _translate_aarch64(prog: dict) -> bytes:
    """Lower an A64 Sail object ``{"isa":"aarch64", "words", "entry",
    "init_regs", "init_sp", "init_nzcv", "init_mem", "property"?}`` to BTOR2."""
    # Deferred imports (mirrors the shared Sail interpreter's isa dispatch):
    # the A64 dependencies load only when an A64 Sail object actually arrives,
    # so importing this pair has the same side effects as before for every
    # existing RISC-V caller.
    from ...languages.aarch64.interp import (
        INSN_BYTES,
        LDST_BYTES,
        MEM_WINDOW,
        NREG as A64_NREG,
        OP_ADDS,
        OP_B,
        OP_BCOND,
        OP_LDR,
        OP_MOVZ,
        OP_STR,
        OP_SUBS,
        SP_DEFAULT,
        decode_insn_v6,
    )
    from ...languages.sail import aarch64 as a64

    words = [int(w) & 0xFFFF_FFFF for w in prog["words"]]
    entry = int(prog.get("entry", 0))
    init_regs = {int(k): int(v) for k, v in prog.get("init_regs", {}).items()}
    init_sp = int(prog.get("init_sp", SP_DEFAULT))     # match the interp's default
    init_nzcv = int(prog.get("init_nzcv", 0)) & 0xF
    init_mem = {int(a): int(v) & 0xFF for a, v in prog.get("init_mem", {}).items()}

    # One decode pass up front through the shared v6 gate (one source of truth
    # for the A64 encoding): any out-of-scope word hard-aborts with its typed
    # ``Unsupported`` before a single node is emitted (BENCHMARKS.md §3).
    decs = [decode_insn_v6(w) for w in words]
    uses_mem = any(d.op in (OP_LDR, OP_STR) for d in decs)

    b = Builder()
    pc = b.state(64, "pc")
    regs = {r: b.state(64, f"x{r}") for r in range(A64_NREG)}
    sp = b.state(64, "sp")
    nzcv = b.state(4, "nzcv")
    halted = b.state(1, "halted")
    # Byte-addressed LE data memory + the fixed observable window m0..m{MEM_WINDOW-1}
    # (bv8 states mirroring the array's lowest bytes — how memory reaches ``π``),
    # emitted only when the program uses LDR/STR — exactly aarch64-btor2's shape.
    mem = b.state_array(64, _A64_BYTE, "mem") if uses_mem else None
    mwin = [b.state(_A64_BYTE, f"m{i}") for i in range(MEM_WINDOW)] if uses_mem else []

    b.init(pc, b.constd(64, entry & MASK64))
    for r in range(A64_NREG):
        b.init(regs[r], b.constd(64, init_regs.get(r, 0) & MASK64))
    b.init(sp, b.constd(64, init_sp & MASK64))
    b.init(nzcv, b.constd(4, init_nzcv))
    b.init(halted, b.zero(1))
    for i in range(MEM_WINDOW):            # window mirrors the initial memory bytes
        if uses_mem:
            b.init(mwin[i], b.constd(_A64_BYTE, init_mem.get(i, 0) & 0xFF))

    not_halted = b.op1("not", 1, halted)
    next_pc = pc
    next_regs = dict(regs)
    next_sp = sp
    next_nzcv = nzcv
    next_mem = mem

    for i, dec in enumerate(decs):
        addr = entry + INSN_BYTES * i
        at = b.op2("eq", 1, pc, b.constd(64, addr & MASK64))
        active = b.op2("and", 1, at, not_halted)
        fall = b.constd(64, (addr + INSN_BYTES) & MASK64)

        if dec.op in (OP_LDR, OP_STR):
            # ea = read(Rn) + imm (base field 31 = SP; imm already scaled). The
            # LE byte assembly is the Sail-derived Expr datapath: the load value
            # is a64.LOAD_EXPR over byte vars b0..b7 bound to array reads at
            # ea..ea+7; the store bytes are a64.STORE_BYTE_EXPRS over the value.
            assert mem is not None
            base = sp if dec.rn == 31 else regs[dec.rn]
            ea = b.op2("add", 64, base, b.constd(64, dec.imm & MASK64))
            next_pc = b.ite(64, active, fall, next_pc)
            if dec.op == OP_LDR:
                byte_bnd = {}
                for j in range(LDST_BYTES):
                    a_j = ea if j == 0 else b.op2("add", 64, ea, b.constd(64, j))
                    byte_bnd[f"b{j}"] = b.read(_A64_BYTE, mem, a_j)
                loaded = expr.lower(b, a64.LOAD_EXPR, byte_bnd)
                if dec.rd != 31:           # Rt == 31 is XZR: the load is discarded
                    next_regs[dec.rd] = b.ite(64, active, loaded, next_regs[dec.rd])
            else:                          # OP_STR (Rt == 31 is XZR: stores 0)
                value = b.constd(64, 0) if dec.rd == 31 else regs[dec.rd]
                cur = mem
                for j in range(LDST_BYTES):
                    byte = expr.lower(b, a64.STORE_BYTE_EXPRS[j], {"v": value})
                    a_j = ea if j == 0 else b.op2("add", 64, ea, b.constd(64, j))
                    cur = b.write(64, _A64_BYTE, cur, a_j, byte)
                next_mem = b.ite_array(64, _A64_BYTE, active, cur, next_mem)
            continue                        # LDR/STR write no flags

        if dec.op == OP_BCOND:
            # pc := ite(cond(NZCV), a+offset, a+4); the predicate is the Sail
            # Expr tree over the packed bv4 nzcv state.
            taken = b.constd(64, (addr + dec.offset) & MASK64)
            cond = expr.lower(b, a64.cond_expr(dec.cond), {"nzcv": nzcv})
            next_pc = b.ite(64, active, b.ite(64, cond, taken, fall), next_pc)
            continue                        # B.cond writes neither regs nor flags

        if dec.op == OP_B:
            # Unconditional: pc := a + offset. BL also links x30 := a + 4.
            taken = b.constd(64, (addr + dec.offset) & MASK64)
            next_pc = b.ite(64, active, taken, next_pc)
            if dec.link:
                next_regs[30] = b.ite(64, active, fall, next_regs[30])
            continue                        # B/BL write no flags

        # ALU / flag-set immediate ops (X or W): the value written to Rd and the
        # NZCV pack are the Sail Expr trees over "a" = read(Rn) — the 32-bit W
        # slice/zext and the flag widths live inside the trees themselves.
        bnd = {"a": sp if dec.rn == 31 else regs[dec.rn]}   # source field 31 = SP
        result = expr.lower(b, a64.exec_expr(dec), bnd)
        next_pc = b.ite(64, active, fall, next_pc)
        # Destination: ADD/SUB field 31 => sp; MOVZ/SUBS/ADDS field 31 => XZR
        # (write discarded — the CMP/CMN forms).
        rd_is_xzr = dec.rd == 31 and dec.op in (OP_MOVZ, OP_SUBS, OP_ADDS)
        if dec.rd == 31 and not rd_is_xzr:
            next_sp = b.ite(64, active, result, next_sp)
        elif dec.rd != 31:
            next_regs[dec.rd] = b.ite(64, active, result, next_regs[dec.rd])
        if dec.op == OP_SUBS:
            flags = expr.lower(b, a64.subs_nzcv_expr(dec), bnd)
            next_nzcv = b.ite(4, active, flags, next_nzcv)
        elif dec.op == OP_ADDS:
            flags = expr.lower(b, a64.adds_nzcv_expr(dec), bnd)
            next_nzcv = b.ite(4, active, flags, next_nzcv)

    # When pc leaves the code region the machine halts (mirrors the Sail A64
    # arm's off-the-end halt and aarch64-btor2's lowering of it).
    lo = b.constd(64, entry & MASK64)
    hi = b.constd(64, (entry + INSN_BYTES * len(words)) & MASK64)
    in_code = b.op2("and", 1, b.op2("ugte", 1, pc, lo), b.op2("ult", 1, pc, hi))
    off_end = b.op2("and", 1, b.op1("not", 1, in_code), not_halted)
    next_halted = b.ite(1, off_end, b.one(1), halted)

    b.next(pc, next_pc)
    for r in range(A64_NREG):
        b.next(regs[r], next_regs[r])
    b.next(sp, next_sp)
    b.next(nzcv, next_nzcv)
    b.next(halted, next_halted)
    if uses_mem:
        assert next_mem is not None
        b.next_array(mem, next_mem)
        # Each window byte tracks the post-step memory array at its fixed
        # address, carrying the memory observable into ``π``.
        for i in range(MEM_WINDOW):
            b.next(mwin[i], b.read(_A64_BYTE, next_mem, b.constd(64, i)))

    # Optional reachability property -> a `bad`, so btor2-smtlib can decide the
    # question along this route too. Same shape as aarch64-btor2's: field 31 = sp.
    prop = prog.get("property")
    if prop and "reg_eq" in prop:
        field_no, val = prop["reg_eq"]
        node = sp if int(field_no) == 31 else regs[int(field_no)]
        b.bad(b.op2("eq", 1, node, b.constd(64, int(val) & MASK64)))

    return b.to_text().encode("utf-8")
