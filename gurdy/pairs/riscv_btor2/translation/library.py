"""Per-instruction BTOR2 library.

One entry per supported mnemonic. Each function takes:

- ``b``: a ``Builder`` for emitting BTOR2 nodes
- ``regs``: a ``RegSnapshot`` exposing nids for the current value of
  every general register (with ``x0`` pinned to the bv64 zero const)
- ``mem``: the nid of the current memory state (a bv64-indexed bv8
  array)
- ``decoded``: the ``Decoded`` instruction (mnemonic + operands)

It returns a :class:`LoweringResult` describing the next-state nids:

- ``reg_writes[N]``: nid that should become ``reg_x{N}`` next-cycle
  (only for the register actually written; others stay).
- ``mem_next``: the nid of the next memory state, or ``None`` if no
  store occurred.
- ``next_pc``: the nid of the next PC.

Polarity, signedness, divide-by-zero, and shift-amount masking all
follow ``SCHEMA.md``. Tests cross-check this lowering against the
concrete simulator for every supported mnemonic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gurdy.pairs.riscv_btor2.source.decoder import Decoded
from gurdy.pairs.riscv_btor2.translation.builder import Builder


XLEN_SORT = "bv64"
W32_SORT = "bv32"


@dataclass
class RegSnapshot:
    """Maps register index 0..31 to the nid of its current bv64 value.

    Index 0 must always map to the bv64 ``zero`` const nid.
    """

    nids: dict[int, int]

    def value(self, n: int) -> int:
        return self.nids[n]


@dataclass
class LoweringResult:
    reg_writes: dict[int, int] = field(default_factory=dict)
    mem_next: int | None = None
    next_pc: int = 0
    halt_next: int | None = None  # for ECALL/EBREAK; bv1 nid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _imm64(b: Builder, imm: int) -> int:
    return b.const(XLEN_SORT, imm & 0xFFFFFFFFFFFFFFFF)


def _shamt6(b: Builder, value_nid: int) -> int:
    """Slice low 6 bits and zero-extend to bv64 for shift operands."""
    six = b.slice("bv6", value_nid, 5, 0)
    return b.uext(XLEN_SORT, six, 64 - 6)


def _shamt5(b: Builder, value_nid: int) -> int:
    """Slice low 5 bits and zero-extend to bv64 for word shifts."""
    five = b.slice("bv5", value_nid, 4, 0)
    return b.uext(XLEN_SORT, five, 64 - 5)


def _sext_w(b: Builder, value_nid: int) -> int:
    """sign-extend low 32 bits of a bv64 to bv64 (for *W ops)."""
    low32 = b.slice(W32_SORT, value_nid, 31, 0)
    return b.sext(XLEN_SORT, low32, 32)


def _next_pc_seq(b: Builder, pc_nid: int, length: int) -> int:
    return b.add(XLEN_SORT, pc_nid, b.const(XLEN_SORT, length))


# ---------------------------------------------------------------------------
# Per-mnemonic
# ---------------------------------------------------------------------------


def lower(
    b: Builder,
    decoded: Decoded,
    regs: RegSnapshot,
    pc_nid: int,
    mem_nid: int,
) -> LoweringResult:
    m = decoded.mnemonic
    rs1 = regs.value(decoded.rs1)
    rs2 = regs.value(decoded.rs2)
    res = LoweringResult(next_pc=_next_pc_seq(b, pc_nid, decoded.length))

    def write(n: int, nid: int) -> None:
        if n == 0:
            return
        res.reg_writes[n] = nid

    if m == "LUI":
        write(decoded.rd, _imm64(b, decoded.imm))
    elif m == "AUIPC":
        write(decoded.rd, b.add(XLEN_SORT, pc_nid, _imm64(b, decoded.imm)))
    elif m == "JAL":
        write(decoded.rd, _next_pc_seq(b, pc_nid, decoded.length))
        res.next_pc = b.add(XLEN_SORT, pc_nid, _imm64(b, decoded.imm))
    elif m == "JALR":
        write(decoded.rd, _next_pc_seq(b, pc_nid, decoded.length))
        target = b.add(XLEN_SORT, rs1, _imm64(b, decoded.imm))
        # Mask low bit per SCHEMA.md.
        all_but1 = b.const(XLEN_SORT, 0xFFFFFFFFFFFFFFFE)
        res.next_pc = b.and_(XLEN_SORT, target, all_but1)
    elif m in {"BEQ", "BNE", "BLT", "BGE", "BLTU", "BGEU"}:
        cond = {
            "BEQ": b.eq,
            "BNE": b.neq,
            "BLT": b.slt,
            "BGE": lambda a, x: b.emit("sgte", "bv1", a, x),
            "BLTU": b.ult,
            "BGEU": lambda a, x: b.emit("ugte", "bv1", a, x),
        }[m](rs1, rs2)
        taken_pc = b.add(XLEN_SORT, pc_nid, _imm64(b, decoded.imm))
        seq_pc = _next_pc_seq(b, pc_nid, decoded.length)
        res.next_pc = b.ite(XLEN_SORT, cond, taken_pc, seq_pc)
    elif m in {"LB", "LH", "LW", "LD", "LBU", "LHU", "LWU"}:
        addr = b.add(XLEN_SORT, rs1, _imm64(b, decoded.imm))
        n_bytes = {"LB": 1, "LBU": 1, "LH": 2, "LHU": 2, "LW": 4, "LWU": 4, "LD": 8}[m]
        v_nid = _load_bytes_le(b, mem_nid, addr, n_bytes)
        # Sign/zero-extend to 64 bits. _load_bytes_le returns bv(8*n_bytes);
        # only LD (n=8) is already bv64.
        if m == "LB":
            v_nid = b.sext(XLEN_SORT, v_nid, 56)
        elif m == "LH":
            v_nid = b.sext(XLEN_SORT, v_nid, 48)
        elif m == "LW":
            v_nid = b.sext(XLEN_SORT, v_nid, 32)
        elif m == "LBU":
            v_nid = b.uext(XLEN_SORT, v_nid, 56)
        elif m == "LHU":
            v_nid = b.uext(XLEN_SORT, v_nid, 48)
        elif m == "LWU":
            v_nid = b.uext(XLEN_SORT, v_nid, 32)
        # LD: already bv64.
        write(decoded.rd, v_nid)
    elif m in {"SB", "SH", "SW", "SD"}:
        addr = b.add(XLEN_SORT, rs1, _imm64(b, decoded.imm))
        n = {"SB": 1, "SH": 2, "SW": 4, "SD": 8}[m]
        res.mem_next = _store_bytes_le(b, mem_nid, addr, rs2, n)
    elif m == "ADDI":
        write(decoded.rd, b.add(XLEN_SORT, rs1, _imm64(b, decoded.imm)))
    elif m == "SLTI":
        cond = b.slt(rs1, _imm64(b, decoded.imm))
        write(decoded.rd, b.uext(XLEN_SORT, cond, 63))
    elif m == "SLTIU":
        cond = b.ult(rs1, _imm64(b, decoded.imm))
        write(decoded.rd, b.uext(XLEN_SORT, cond, 63))
    elif m == "XORI":
        write(decoded.rd, b.xor(XLEN_SORT, rs1, _imm64(b, decoded.imm)))
    elif m == "ORI":
        write(decoded.rd, b.or_(XLEN_SORT, rs1, _imm64(b, decoded.imm)))
    elif m == "ANDI":
        write(decoded.rd, b.and_(XLEN_SORT, rs1, _imm64(b, decoded.imm)))
    elif m in {"SLLI", "SRLI", "SRAI"}:
        shamt = b.const(XLEN_SORT, decoded.imm & 0x3F)
        if m == "SLLI":
            write(decoded.rd, b.sll(XLEN_SORT, rs1, shamt))
        elif m == "SRLI":
            write(decoded.rd, b.srl(XLEN_SORT, rs1, shamt))
        else:
            write(decoded.rd, b.sra(XLEN_SORT, rs1, shamt))
    elif m == "ADDIW":
        sum_ = b.add(XLEN_SORT, rs1, _imm64(b, decoded.imm))
        write(decoded.rd, _sext_w(b, sum_))
    elif m in {"SLLIW", "SRLIW", "SRAIW"}:
        shamt = b.const(W32_SORT, decoded.imm & 0x1F)
        rs1_w = b.slice(W32_SORT, rs1, 31, 0)
        if m == "SLLIW":
            wres = b.sll(W32_SORT, rs1_w, shamt)
        elif m == "SRLIW":
            wres = b.srl(W32_SORT, rs1_w, shamt)
        else:
            wres = b.sra(W32_SORT, rs1_w, shamt)
        write(decoded.rd, b.sext(XLEN_SORT, wres, 32))
    elif m == "ADD":
        write(decoded.rd, b.add(XLEN_SORT, rs1, rs2))
    elif m == "SUB":
        write(decoded.rd, b.sub(XLEN_SORT, rs1, rs2))
    elif m == "SLL":
        write(decoded.rd, b.sll(XLEN_SORT, rs1, _shamt6(b, rs2)))
    elif m == "SLT":
        write(decoded.rd, b.uext(XLEN_SORT, b.slt(rs1, rs2), 63))
    elif m == "SLTU":
        write(decoded.rd, b.uext(XLEN_SORT, b.ult(rs1, rs2), 63))
    elif m == "XOR":
        write(decoded.rd, b.xor(XLEN_SORT, rs1, rs2))
    elif m == "SRL":
        write(decoded.rd, b.srl(XLEN_SORT, rs1, _shamt6(b, rs2)))
    elif m == "SRA":
        write(decoded.rd, b.sra(XLEN_SORT, rs1, _shamt6(b, rs2)))
    elif m == "OR":
        write(decoded.rd, b.or_(XLEN_SORT, rs1, rs2))
    elif m == "AND":
        write(decoded.rd, b.and_(XLEN_SORT, rs1, rs2))
    elif m == "ADDW":
        wres = b.add(W32_SORT, b.slice(W32_SORT, rs1, 31, 0), b.slice(W32_SORT, rs2, 31, 0))
        write(decoded.rd, b.sext(XLEN_SORT, wres, 32))
    elif m == "SUBW":
        wres = b.sub(W32_SORT, b.slice(W32_SORT, rs1, 31, 0), b.slice(W32_SORT, rs2, 31, 0))
        write(decoded.rd, b.sext(XLEN_SORT, wres, 32))
    elif m in {"SLLW", "SRLW", "SRAW"}:
        rs1_w = b.slice(W32_SORT, rs1, 31, 0)
        shamt_w = b.slice("bv5", rs2, 4, 0)
        shamt_w = b.uext(W32_SORT, shamt_w, 27)
        if m == "SLLW":
            wres = b.sll(W32_SORT, rs1_w, shamt_w)
        elif m == "SRLW":
            wres = b.srl(W32_SORT, rs1_w, shamt_w)
        else:
            wres = b.sra(W32_SORT, rs1_w, shamt_w)
        write(decoded.rd, b.sext(XLEN_SORT, wres, 32))
    # ----- M extension -----
    elif m == "MUL":
        write(decoded.rd, b.mul(XLEN_SORT, rs1, rs2))
    elif m == "MULH":
        prod = _mul128_signed(b, rs1, rs2)
        write(decoded.rd, b.slice(XLEN_SORT, prod, 127, 64))
    elif m == "MULHU":
        prod = _mul128_unsigned(b, rs1, rs2)
        write(decoded.rd, b.slice(XLEN_SORT, prod, 127, 64))
    elif m == "MULHSU":
        prod = _mul128_signed_unsigned(b, rs1, rs2)
        write(decoded.rd, b.slice(XLEN_SORT, prod, 127, 64))
    elif m in {"DIV", "DIVU", "REM", "REMU"}:
        write(decoded.rd, _div_rem_64(b, m, rs1, rs2))
    elif m in {"MULW", "DIVW", "DIVUW", "REMW", "REMUW"}:
        write(decoded.rd, _div_rem_w(b, m, rs1, rs2))
    elif m in {"FENCE", "FENCE.I"}:
        pass  # no-op
    elif m in {"ECALL", "EBREAK"}:
        res.halt_next = b.const("bv1", 1)
        res.next_pc = pc_nid  # freeze pc per SCHEMA.md
    elif m.startswith("CSRR"):
        # CSR reads return nondet at the schema level; the pipeline
        # supplies the input nid via ``mem_nid`` semantics elsewhere.
        # Library lowering has no nondet input nid handy; for the
        # baseline we write zero. The translation pipeline overlays
        # nondet substitution where needed.
        if decoded.rd != 0:
            write(decoded.rd, b.const(XLEN_SORT, 0))
    else:
        raise NotImplementedError(f"library: unsupported mnemonic {m!r}")

    return res


# ---------------------------------------------------------------------------
# Memory primitives
# ---------------------------------------------------------------------------


def _load_bytes_le(b: Builder, mem_nid: int, addr: int, n: int) -> int:
    """Load ``n`` bytes from memory and return a bv(8*n) value."""
    if n == 1:
        return b.read("bv8", mem_nid, addr)
    parts: list[int] = []
    for i in range(n):
        offset_addr = b.add(XLEN_SORT, addr, b.const(XLEN_SORT, i))
        parts.append(b.read("bv8", mem_nid, offset_addr))
    # Concatenate little-endian: byte 0 is LSB.
    target_widths = [8 * (i + 1) for i in range(n)]
    acc = parts[0]
    for i in range(1, n):
        target_w = 8 * (i + 1)
        target_sort = f"bv{target_w}"
        # acc currently bv(8*i); concat with parts[i] (high byte).
        acc = b.concat(target_sort, parts[i], acc)
    return acc


def _store_bytes_le(
    b: Builder, mem_nid: int, addr: int, value_nid: int, n: int
) -> int:
    """Write the low ``n`` bytes of ``value_nid`` to ``mem_nid``."""
    cur = mem_nid
    for i in range(n):
        offset_addr = b.add(XLEN_SORT, addr, b.const(XLEN_SORT, i))
        byte = b.slice("bv8", value_nid, 8 * i + 7, 8 * i)
        cur = b.write("mem", cur, offset_addr, byte)
    return cur


# ---------------------------------------------------------------------------
# Mul/div helpers
# ---------------------------------------------------------------------------


def _mul128_signed(b: Builder, a: int, c: int) -> int:
    a128 = b.sext("bv128", a, 64)
    c128 = b.sext("bv128", c, 64)
    return b.mul("bv128", a128, c128)


def _mul128_unsigned(b: Builder, a: int, c: int) -> int:
    a128 = b.uext("bv128", a, 64)
    c128 = b.uext("bv128", c, 64)
    return b.mul("bv128", a128, c128)


def _mul128_signed_unsigned(b: Builder, a: int, c: int) -> int:
    a128 = b.sext("bv128", a, 64)
    c128 = b.uext("bv128", c, 64)
    return b.mul("bv128", a128, c128)


def _div_rem_64(b: Builder, m: str, a: int, c: int) -> int:
    """Encode RV64M signed/unsigned div/rem with the schema-defined
    divide-by-zero and overflow tables."""

    zero = b.const(XLEN_SORT, 0)
    ones = b.ones(XLEN_SORT)
    is_zero = b.eq(c, zero)

    if m == "DIVU":
        # Quotient = ones if div0 else udiv.
        q = b.udiv(XLEN_SORT, a, c)
        return b.ite(XLEN_SORT, is_zero, ones, q)
    if m == "REMU":
        r = b.urem(XLEN_SORT, a, c)
        return b.ite(XLEN_SORT, is_zero, a, r)
    # DIV/REM (signed) with overflow case.
    intmin = b.const(XLEN_SORT, 1 << 63)
    minus1 = ones  # all-ones in bv64 = -1 signed
    is_intmin = b.eq(a, intmin)
    is_minus1 = b.eq(c, minus1)
    is_overflow = b.and_("bv1", is_intmin, is_minus1)

    if m == "DIV":
        q = b.sdiv(XLEN_SORT, a, c)
        # If overflow: q = INT_MIN. If div0: q = -1 (all-ones).
        out = b.ite(XLEN_SORT, is_overflow, intmin, q)
        return b.ite(XLEN_SORT, is_zero, ones, out)
    if m == "REM":
        r = b.srem(XLEN_SORT, a, c)
        out = b.ite(XLEN_SORT, is_overflow, zero, r)
        return b.ite(XLEN_SORT, is_zero, a, out)
    raise AssertionError("unreachable")


def _div_rem_w(b: Builder, m: str, a: int, c: int) -> int:
    """RV64M *W variants: 32-bit op, sign-extended back to 64."""
    a32 = b.slice(W32_SORT, a, 31, 0)
    c32 = b.slice(W32_SORT, c, 31, 0)

    if m == "MULW":
        prod = b.mul(W32_SORT, a32, c32)
        return b.sext(XLEN_SORT, prod, 32)

    zero32 = b.const(W32_SORT, 0)
    ones32 = b.ones(W32_SORT)
    is_zero = b.eq(c32, zero32)

    if m == "DIVUW":
        q = b.udiv(W32_SORT, a32, c32)
        out = b.ite(W32_SORT, is_zero, ones32, q)
        return b.sext(XLEN_SORT, out, 32)
    if m == "REMUW":
        r = b.urem(W32_SORT, a32, c32)
        out = b.ite(W32_SORT, is_zero, a32, r)
        return b.sext(XLEN_SORT, out, 32)

    intmin32 = b.const(W32_SORT, 1 << 31)
    minus1_32 = ones32
    is_intmin = b.eq(a32, intmin32)
    is_minus1 = b.eq(c32, minus1_32)
    is_overflow = b.and_("bv1", is_intmin, is_minus1)

    if m == "DIVW":
        q = b.sdiv(W32_SORT, a32, c32)
        out = b.ite(W32_SORT, is_overflow, intmin32, q)
        out = b.ite(W32_SORT, is_zero, ones32, out)
        return b.sext(XLEN_SORT, out, 32)
    if m == "REMW":
        r = b.srem(W32_SORT, a32, c32)
        out = b.ite(W32_SORT, is_overflow, zero32, r)
        out = b.ite(W32_SORT, is_zero, a32, out)
        return b.sext(XLEN_SORT, out, 32)
    raise AssertionError("unreachable")


SUPPORTED_MNEMONICS = (
    # I
    "LUI",
    "AUIPC",
    "JAL",
    "JALR",
    "BEQ",
    "BNE",
    "BLT",
    "BGE",
    "BLTU",
    "BGEU",
    "LB",
    "LH",
    "LW",
    "LD",
    "LBU",
    "LHU",
    "LWU",
    "SB",
    "SH",
    "SW",
    "SD",
    "ADDI",
    "SLTI",
    "SLTIU",
    "XORI",
    "ORI",
    "ANDI",
    "SLLI",
    "SRLI",
    "SRAI",
    "ADDIW",
    "SLLIW",
    "SRLIW",
    "SRAIW",
    "ADD",
    "SUB",
    "SLL",
    "SLT",
    "SLTU",
    "XOR",
    "SRL",
    "SRA",
    "OR",
    "AND",
    "ADDW",
    "SUBW",
    "SLLW",
    "SRLW",
    "SRAW",
    "FENCE",
    "FENCE.I",
    "ECALL",
    "EBREAK",
    "CSRRW",
    "CSRRS",
    "CSRRC",
    "CSRRWI",
    "CSRRSI",
    "CSRRCI",
    # M
    "MUL",
    "MULH",
    "MULHSU",
    "MULHU",
    "DIV",
    "DIVU",
    "REM",
    "REMU",
    "MULW",
    "DIVW",
    "DIVUW",
    "REMW",
    "REMUW",
)


__all__ = ["lower", "RegSnapshot", "LoweringResult", "SUPPORTED_MNEMONICS"]
