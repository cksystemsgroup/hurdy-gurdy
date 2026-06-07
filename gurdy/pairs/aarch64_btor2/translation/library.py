"""Per-instruction BTOR2 library for AArch64 A64.

One entry per supported mnemonic in ``lower()``. Returns a
:class:`LoweringResult` describing next-state nids. Cross-checked
against the concrete simulator (tests/pairs/aarch64_btor2/).

AArch64 divergences from riscv_btor2:
- 31 GPRs (x0–x30); reg 31 is XZR (DP context) or SP (memory context).
- W-register results zero-extend (not sign-extend).
- SDIV/UDIV div-by-zero → 0.
- NZCV 4-bit flags state updated by *S variants (ADDS, SUBS, ANDS).
- B.cond / CSEL etc. read NZCV via evaluate_condition().
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gurdy.pairs.aarch64_btor2.source.decoder import Decoded
from gurdy.pairs.aarch64_btor2.translation.builder import Builder


XLEN_SORT = "bv64"
W32_SORT = "bv32"
BV1 = "bv1"
BV4 = "bv4"  # NZCV


@dataclass
class RegSnapshot:
    """Maps register indices 0–30 to the nid of their current bv64 value.

    Register 31 is XZR (zero) in data-processing contexts and SP in
    memory/base-register contexts. ``xr()`` returns the XZR value;
    ``spr()`` returns the SP state.
    """

    nids: dict[int, int]
    sp_nid: int
    xzr_nid: int  # bv64 zero const

    def xr(self, n: int) -> int:
        """Data-processing read: reg 31 = XZR (zero)."""
        return self.xzr_nid if n == 31 else self.nids[n]

    def spr(self, n: int) -> int:
        """SP-context read: reg 31 = SP."""
        return self.sp_nid if n == 31 else self.nids[n]


@dataclass
class LoweringResult:
    reg_writes: dict[int, int] = field(default_factory=dict)
    """reg 0–30 → next-value nid."""
    sp_next: int | None = None
    """next SP nid, or None if unchanged."""
    nzcv_next: int | None = None
    """next NZCV nid (bv4), or None if unchanged."""
    mem_next: int | None = None
    """next mem nid, or None if no store."""
    next_pc: int = 0
    halt_next: int | None = None
    """bv1 nid set to 1 on SVC/BRK, None otherwise."""
    branch_cond: int | None = None
    """bv1 nid for the branch predicate (B.cond / CBZ / CBNZ / TBZ / TBNZ)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _imm64(b: Builder, imm: int) -> int:
    return b.const(XLEN_SORT, imm & 0xFFFFFFFFFFFFFFFF)


def _next_pc_seq(b: Builder, pc_nid: int) -> int:
    return b.add(XLEN_SORT, pc_nid, b.const(XLEN_SORT, 4))


def _load_bytes_le(b: Builder, mem_nid: int, addr_nid: int, n: int) -> int:
    if n == 1:
        return b.read("bv8", mem_nid, addr_nid)
    parts = []
    for i in range(n):
        off = b.add(XLEN_SORT, addr_nid, b.const(XLEN_SORT, i))
        parts.append(b.read("bv8", mem_nid, off))
    acc = parts[0]
    for i in range(1, n):
        acc = b.concat(f"bv{8*(i+1)}", parts[i], acc)
    return acc


def _store_bytes_le(b: Builder, mem_nid: int, addr_nid: int, value_nid: int, n: int) -> int:
    cur = mem_nid
    for i in range(n):
        off = b.add(XLEN_SORT, addr_nid, b.const(XLEN_SORT, i))
        byte = b.slice("bv8", value_nid, 8*i+7, 8*i)
        cur = b.write("mem", cur, off, byte)
    return cur


def _apply_shift(b: Builder, val_nid: int, shift_type: int, amount: int, sf: bool) -> int:
    """Apply a fixed-amount shift (used for shifted-register DP operands)."""
    sort = XLEN_SORT if sf else W32_SORT
    width = 64 if sf else 32
    if amount == 0:
        return val_nid
    amt = b.const(sort, amount & (63 if sf else 31))
    if shift_type == 0:   # LSL
        return b.sll(sort, val_nid, amt)
    elif shift_type == 1: # LSR
        return b.srl(sort, val_nid, amt)
    elif shift_type == 2: # ASR
        return b.sra(sort, val_nid, amt)
    else:                 # ROR: concat(val[amount-1:0], val[width-1:amount])
        lo = b.slice(f"bv{amount}", val_nid, amount-1, 0)
        hi = b.slice(f"bv{width-amount}", val_nid, width-1, amount)
        return b.concat(sort, lo, hi)


def _apply_extend(b: Builder, val_nid: int, ext_type: int, shift: int) -> int:
    """Apply an extend-and-shift for extended-register addressing (§5.5)."""
    if ext_type == 0:    # UXTB
        v = b.uext(XLEN_SORT, b.slice("bv8", val_nid, 7, 0), 56)
    elif ext_type == 1:  # UXTH
        v = b.uext(XLEN_SORT, b.slice("bv16", val_nid, 15, 0), 48)
    elif ext_type == 2:  # UXTW
        v = b.uext(XLEN_SORT, b.slice(W32_SORT, val_nid, 31, 0), 32)
    elif ext_type == 3:  # UXTX (no-op extend)
        v = val_nid
    elif ext_type == 4:  # SXTB
        v = b.sext(XLEN_SORT, b.slice("bv8", val_nid, 7, 0), 56)
    elif ext_type == 5:  # SXTH
        v = b.sext(XLEN_SORT, b.slice("bv16", val_nid, 15, 0), 48)
    elif ext_type == 6:  # SXTW
        v = b.sext(XLEN_SORT, b.slice(W32_SORT, val_nid, 31, 0), 32)
    else:                # SXTX (sign-extend 64 = no-op)
        v = val_nid
    if shift:
        v = b.sll(XLEN_SORT, v, b.const(XLEN_SORT, shift))
    return v


def _nzcv_add(b: Builder, lhs_nid: int, rhs_nid: int, sf: bool) -> tuple[int, int]:
    """Compute result and NZCV for an ADD-like (ADDS/CMN) operation.

    Returns (result_nid bv64, nzcv_nid bv4).
    """
    if sf:
        lhs = lhs_nid
        rhs = rhs_nid
        lhs_ext = b.uext("bv65", lhs, 1)
        rhs_ext = b.uext("bv65", rhs, 1)
        sum_ext = b.add("bv65", lhs_ext, rhs_ext)
        r = b.slice(XLEN_SORT, sum_ext, 63, 0)
        N = b.slice(BV1, r, 63, 63)
        Z = b.eq(r, b.const(XLEN_SORT, 0))
        C = b.slice(BV1, sum_ext, 64, 64)
        lhs_msb = b.slice(BV1, lhs, 63, 63)
        rhs_msb = b.slice(BV1, rhs, 63, 63)
        same_sign = b.eq(lhs_msb, rhs_msb)
        flipped = b.neq(N, lhs_msb)
        V = b.and_(BV1, same_sign, flipped)
        nzcv = _pack_nzcv(b, N, Z, C, V)
        return r, nzcv
    else:
        lhs = b.slice(W32_SORT, lhs_nid, 31, 0)
        rhs = b.slice(W32_SORT, rhs_nid, 31, 0)
        lhs_ext = b.uext("bv33", lhs, 1)
        rhs_ext = b.uext("bv33", rhs, 1)
        sum_ext = b.add("bv33", lhs_ext, rhs_ext)
        r32 = b.slice(W32_SORT, sum_ext, 31, 0)
        N = b.slice(BV1, r32, 31, 31)
        Z = b.eq(r32, b.const(W32_SORT, 0))
        C = b.slice(BV1, sum_ext, 32, 32)
        lhs_msb = b.slice(BV1, lhs, 31, 31)
        rhs_msb = b.slice(BV1, rhs, 31, 31)
        same_sign = b.eq(lhs_msb, rhs_msb)
        flipped = b.neq(N, lhs_msb)
        V = b.and_(BV1, same_sign, flipped)
        nzcv = _pack_nzcv(b, N, Z, C, V)
        r = b.uext(XLEN_SORT, r32, 32)  # W-reg results zero-extend
        return r, nzcv


def _nzcv_sub(b: Builder, lhs_nid: int, rhs_nid: int, sf: bool) -> tuple[int, int]:
    """Compute result and NZCV for a SUB-like (SUBS/CMP) operation.

    AArch64 carry convention: C=1 means no-borrow (lhs >= rhs unsigned).
    """
    if sf:
        lhs = lhs_nid
        rhs = rhs_nid
        rhs_inv = b.not_(XLEN_SORT, rhs)
        lhs_ext = b.uext("bv65", lhs, 1)
        rhs_inv_ext = b.uext("bv65", rhs_inv, 1)
        one65 = b.const("bv65", 1)
        sum_ext = b.add("bv65", b.add("bv65", lhs_ext, rhs_inv_ext), one65)
        r = b.slice(XLEN_SORT, sum_ext, 63, 0)
        N = b.slice(BV1, r, 63, 63)
        Z = b.eq(r, b.const(XLEN_SORT, 0))
        C = b.slice(BV1, sum_ext, 64, 64)
        lhs_msb = b.slice(BV1, lhs, 63, 63)
        rhs_msb = b.slice(BV1, rhs, 63, 63)
        diff_sign = b.neq(lhs_msb, rhs_msb)
        flipped = b.neq(N, lhs_msb)
        V = b.and_(BV1, diff_sign, flipped)
        nzcv = _pack_nzcv(b, N, Z, C, V)
        return r, nzcv
    else:
        lhs = b.slice(W32_SORT, lhs_nid, 31, 0)
        rhs = b.slice(W32_SORT, rhs_nid, 31, 0)
        rhs_inv = b.not_(W32_SORT, rhs)
        lhs_ext = b.uext("bv33", lhs, 1)
        rhs_inv_ext = b.uext("bv33", rhs_inv, 1)
        one33 = b.const("bv33", 1)
        sum_ext = b.add("bv33", b.add("bv33", lhs_ext, rhs_inv_ext), one33)
        r32 = b.slice(W32_SORT, sum_ext, 31, 0)
        N = b.slice(BV1, r32, 31, 31)
        Z = b.eq(r32, b.const(W32_SORT, 0))
        C = b.slice(BV1, sum_ext, 32, 32)
        lhs_msb = b.slice(BV1, lhs, 31, 31)
        rhs_msb = b.slice(BV1, rhs, 31, 31)
        diff_sign = b.neq(lhs_msb, rhs_msb)
        flipped = b.neq(N, lhs_msb)
        V = b.and_(BV1, diff_sign, flipped)
        nzcv = _pack_nzcv(b, N, Z, C, V)
        r = b.uext(XLEN_SORT, r32, 32)
        return r, nzcv


def _nzcv_logical(b: Builder, result_nid: int, sf: bool) -> int:
    """Compute NZCV for logical flag-setting ops (ANDS/TST). C=V=0."""
    if sf:
        N = b.slice(BV1, result_nid, 63, 63)
        Z = b.eq(result_nid, b.const(XLEN_SORT, 0))
    else:
        r32 = b.slice(W32_SORT, result_nid, 31, 0)
        N = b.slice(BV1, r32, 31, 31)
        Z = b.eq(r32, b.const(W32_SORT, 0))
    C = b.const(BV1, 0)
    V = b.const(BV1, 0)
    return _pack_nzcv(b, N, Z, C, V)


def _pack_nzcv(b: Builder, N: int, Z: int, C: int, V: int) -> int:
    """Pack four bv1 flags into a bv4 NZCV value (N=bit3, Z=bit2, C=bit1, V=bit0)."""
    cv = b.concat("bv2", C, V)
    zcv = b.concat("bv3", Z, cv)
    return b.concat(BV4, N, zcv)


def evaluate_condition(b: Builder, cond: int, nzcv_nid: int) -> int:
    """Evaluate A64 condition code (4-bit) against NZCV state → bv1."""
    N = b.slice(BV1, nzcv_nid, 3, 3)
    Z = b.slice(BV1, nzcv_nid, 2, 2)
    C = b.slice(BV1, nzcv_nid, 1, 1)
    V = b.slice(BV1, nzcv_nid, 0, 0)
    c = cond & 0xF
    if c == 0:   # EQ: Z
        return Z
    elif c == 1: # NE: !Z
        return b.not_(BV1, Z)
    elif c == 2: # CS/HS: C
        return C
    elif c == 3: # CC/LO: !C
        return b.not_(BV1, C)
    elif c == 4: # MI: N
        return N
    elif c == 5: # PL: !N
        return b.not_(BV1, N)
    elif c == 6: # VS: V
        return V
    elif c == 7: # VC: !V
        return b.not_(BV1, V)
    elif c == 8: # HI: C & !Z
        return b.and_(BV1, C, b.not_(BV1, Z))
    elif c == 9: # LS: !C | Z
        return b.or_(BV1, b.not_(BV1, C), Z)
    elif c == 10: # GE: N == V
        return b.eq(N, V)
    elif c == 11: # LT: N != V
        return b.neq(N, V)
    elif c == 12: # GT: !Z & (N == V)
        return b.and_(BV1, b.not_(BV1, Z), b.eq(N, V))
    elif c == 13: # LE: Z | (N != V)
        return b.or_(BV1, Z, b.neq(N, V))
    else:        # AL / NV: always true
        return b.const(BV1, 1)


def _sdiv_a64(b: Builder, a_nid: int, c_nid: int, sf: bool) -> int:
    """AArch64 signed divide: div-by-zero → 0, INT_MIN/-1 → INT_MIN."""
    if sf:
        zero = b.const(XLEN_SORT, 0)
        intmin = b.const(XLEN_SORT, 1 << 63)
        minus1 = b.ones(XLEN_SORT)
        is_zero = b.eq(c_nid, zero)
        is_intmin = b.eq(a_nid, intmin)
        is_minus1 = b.eq(c_nid, minus1)
        is_overflow = b.and_(BV1, is_intmin, is_minus1)
        q = b.sdiv(XLEN_SORT, a_nid, c_nid)
        out = b.ite(XLEN_SORT, is_overflow, intmin, q)
        return b.ite(XLEN_SORT, is_zero, zero, out)
    else:
        a32 = b.slice(W32_SORT, a_nid, 31, 0)
        c32 = b.slice(W32_SORT, c_nid, 31, 0)
        zero32 = b.const(W32_SORT, 0)
        intmin32 = b.const(W32_SORT, 1 << 31)
        minus1_32 = b.ones(W32_SORT)
        is_zero = b.eq(c32, zero32)
        is_intmin = b.eq(a32, intmin32)
        is_minus1 = b.eq(c32, minus1_32)
        is_overflow = b.and_(BV1, is_intmin, is_minus1)
        q = b.sdiv(W32_SORT, a32, c32)
        out = b.ite(W32_SORT, is_overflow, intmin32, q)
        out = b.ite(W32_SORT, is_zero, zero32, out)
        return b.uext(XLEN_SORT, out, 32)  # zero-extend (AArch64 W-reg)


def _udiv_a64(b: Builder, a_nid: int, c_nid: int, sf: bool) -> int:
    """AArch64 unsigned divide: div-by-zero → 0."""
    if sf:
        zero = b.const(XLEN_SORT, 0)
        is_zero = b.eq(c_nid, zero)
        q = b.udiv(XLEN_SORT, a_nid, c_nid)
        return b.ite(XLEN_SORT, is_zero, zero, q)
    else:
        a32 = b.slice(W32_SORT, a_nid, 31, 0)
        c32 = b.slice(W32_SORT, c_nid, 31, 0)
        zero32 = b.const(W32_SORT, 0)
        is_zero = b.eq(c32, zero32)
        q = b.udiv(W32_SORT, a32, c32)
        out = b.ite(W32_SORT, is_zero, zero32, q)
        return b.uext(XLEN_SORT, out, 32)


def _ubfm(b: Builder, src: int, immr: int, imms: int, sf: bool) -> int:
    """UBFM: unsigned bitfield move → bv64 result."""
    width = 64 if sf else 32
    if sf:
        result_sort = XLEN_SORT
    else:
        result_sort = W32_SORT
        src = b.slice(W32_SORT, src, 31, 0)

    if imms >= immr:
        nbits = imms - immr + 1
        field = b.slice(f"bv{nbits}", src, imms, immr)
        r = b.uext(result_sort, field, width - nbits) if nbits < width else field
    else:
        nbits = imms + 1
        field = b.slice(f"bv{nbits}", src, imms, 0)
        bits_below = width - immr
        bits_above = immr - imms - 1
        if bits_below > 0:
            mid = b.concat(f"bv{nbits+bits_below}", field, b.const(f"bv{bits_below}", 0))
        else:
            mid = field
        if bits_above > 0:
            r = b.uext(result_sort, mid, bits_above)
        else:
            r = mid

    if not sf:
        r = b.uext(XLEN_SORT, r, 32)
    return r


def _sbfm(b: Builder, src: int, immr: int, imms: int, sf: bool) -> int:
    """SBFM: signed bitfield move → bv64 result."""
    width = 64 if sf else 32
    if sf:
        result_sort = XLEN_SORT
    else:
        result_sort = W32_SORT
        src = b.slice(W32_SORT, src, 31, 0)

    if imms >= immr:
        nbits = imms - immr + 1
        field = b.slice(f"bv{nbits}", src, imms, immr)
        r = b.sext(result_sort, field, width - nbits) if nbits < width else field
    else:
        nbits = imms + 1
        field = b.slice(f"bv{nbits}", src, imms, 0)
        bits_below = width - immr
        bits_above = immr - imms - 1
        if bits_below > 0:
            mid = b.concat(f"bv{nbits+bits_below}", field, b.const(f"bv{bits_below}", 0))
        else:
            mid = field
        # Sign-extend the upper portion from the sign of the extracted field.
        sign = b.slice(BV1, src, imms, imms)
        if bits_above > 0:
            sign_fill = b.sext(f"bv{bits_above}", sign, bits_above - 1)
            r = b.concat(result_sort, sign_fill, mid)
        else:
            r = mid

    if not sf:
        r = b.uext(XLEN_SORT, r, 32)
    return r


def _bfm(b: Builder, dst: int, src: int, immr: int, imms: int, sf: bool) -> int:
    """BFM: bitfield move (insert/copy into destination) → bv64 result."""
    width = 64 if sf else 32
    result_sort = XLEN_SORT if sf else W32_SORT
    if not sf:
        dst = b.slice(W32_SORT, dst, 31, 0)
        src = b.slice(W32_SORT, src, 31, 0)

    if imms >= immr:
        nbits = imms - immr + 1
        field = b.slice(f"bv{nbits}", src, imms, immr)
        # Build a mask: 1s at bits [imms:immr]
        mask_int = ((1 << nbits) - 1) << immr
        mask_nid = b.const(result_sort, mask_int & ((1 << width) - 1))
        not_mask = b.not_(result_sort, mask_nid)
        # Place field at position immr
        if immr > 0:
            field_placed = b.concat(result_sort,
                                    b.concat(f"bv{width-immr}",
                                             b.const(f"bv{width-immr-nbits}", 0) if width-immr-nbits > 0
                                             else field,
                                             field) if width-immr-nbits > 0 else
                                    b.concat(f"bv{width-immr}", b.const(f"bv{width-immr-nbits}", 0) if width-immr-nbits > 0 else field, field),
                                    b.const(f"bv{immr}", 0))
            # Simpler: shift field left by immr, then mask
            shifted = b.sll(result_sort, b.uext(result_sort, field, width - nbits), b.const(result_sort, immr))
        else:
            shifted = b.uext(result_sort, field, width - nbits)
        r = b.or_(result_sort, b.and_(result_sort, dst, not_mask), b.and_(result_sort, shifted, mask_nid))
    else:
        # Copy src[imms:0] into dst at bit position width-immr
        nbits = imms + 1
        field = b.slice(f"bv{nbits}", src, imms, 0)
        bits_below = width - immr
        # The field occupies bits [bits_below+nbits-1 : bits_below] in dst
        top = bits_below + nbits - 1
        bottom = bits_below
        mask_int = ((1 << nbits) - 1) << bottom
        mask_nid = b.const(result_sort, mask_int & ((1 << width) - 1))
        not_mask = b.not_(result_sort, mask_nid)
        if bits_below > 0:
            shifted = b.concat(result_sort,
                               b.concat(f"bv{nbits+bits_below}",
                                        field,
                                        b.const(f"bv{bits_below}", 0)),
                               b.const(f"bv{width-nbits-bits_below}", 0)) if width-nbits-bits_below > 0 else \
                      b.concat(result_sort, field, b.const(f"bv{bits_below}", 0))
        else:
            shifted = b.uext(result_sort, field, width - nbits) if width-nbits > 0 else field
        r = b.or_(result_sort, b.and_(result_sort, dst, not_mask), b.and_(result_sort, shifted, mask_nid))

    if not sf:
        r = b.uext(XLEN_SORT, r, 32)
    return r


def _compute_addr(b: Builder, snap: RegSnapshot, d: Decoded) -> tuple[int, int | None, int | None]:
    """Compute effective address from addressing mode.

    Returns (addr_nid, wb_val_nid, writeback_reg):
    - addr_nid: the effective address (bv64)
    - wb_val_nid: the write-back value for Rn (or None if no writeback)
    - writeback_reg: the register index to update (or None)
    """
    rn_base = snap.spr(d.rn)
    if d.addr_mode in ("base", "base_imm"):
        addr = b.add(XLEN_SORT, rn_base, _imm64(b, d.imm))
        return addr, None, None
    elif d.addr_mode == "pre":
        addr = b.add(XLEN_SORT, rn_base, _imm64(b, d.imm))
        return addr, addr, d.rn
    elif d.addr_mode == "post":
        addr = rn_base
        wb = b.add(XLEN_SORT, rn_base, _imm64(b, d.imm))
        return addr, wb, d.rn
    elif d.addr_mode in ("base_reg", "ext_reg"):
        ext = _apply_extend(b, snap.xr(d.rm), d.extend_type, d.shift_amount)
        addr = b.add(XLEN_SORT, rn_base, ext)
        return addr, None, None
    elif d.addr_mode == "literal":
        # PC-relative: imm already encodes the offset
        addr = _imm64(b, d.imm)  # absolute address pre-computed by decoder
        return addr, None, None
    else:
        # Fallback: treat as base (rn + 0)
        return rn_base, None, None


def _writeback(res: LoweringResult, wb_reg: int | None, wb_nid: int | None, snap: RegSnapshot) -> None:
    if wb_reg is None or wb_nid is None:
        return
    if wb_reg == 31:
        res.sp_next = wb_nid
    else:
        res.reg_writes[wb_reg] = wb_nid


# ---------------------------------------------------------------------------
# Top-level lower()
# ---------------------------------------------------------------------------


def lower(
    b: Builder,
    decoded: Decoded,
    regs: RegSnapshot,
    pc_nid: int,
    mem_nid: int,
    nzcv_nid: int,
) -> LoweringResult:
    """Lower one decoded A64 instruction to BTOR2 next-state expressions."""
    m = decoded.mnemonic
    sf = decoded.sf
    res = LoweringResult(next_pc=_next_pc_seq(b, pc_nid))
    mask = (1 << 64) - 1 if sf else (1 << 32) - 1

    def write(n: int, nid: int) -> None:
        """Write to destination: discards XZR (n==31 for DP context)."""
        if n == 31:
            return
        res.reg_writes[n] = nid

    def write_sp(n: int, nid: int) -> None:
        """Write to SP if n==31, else normal register write."""
        if n == 31:
            res.sp_next = nid
        else:
            res.reg_writes[n] = nid

    # -----------------------------------------------------------------------
    # Determine Rn operand with proper SP context for ADD/SUB variants
    # -----------------------------------------------------------------------
    is_sub = m in ("SUB", "SUBS", "CMP")

    if m in ("ADD", "SUB", "ADDS", "SUBS", "CMN", "CMP"):
        use_sp = decoded.rn == 31 and (decoded.src_is_imm or decoded.addr_mode == "ext_reg")
        rn_v = regs.spr(decoded.rn) if use_sp else regs.xr(decoded.rn)
        if decoded.src_is_imm:
            rhs = _imm64(b, decoded.imm)
            if not sf:
                rhs = b.uext(XLEN_SORT, b.const(W32_SORT, decoded.imm & 0xFFFFFFFF), 32)
                rhs = b.slice(XLEN_SORT, rhs, 63, 0)
        elif decoded.addr_mode == "ext_reg":
            rhs = _apply_extend(b, regs.xr(decoded.rm), decoded.extend_type, decoded.shift_amount)
        else:
            rhs = _apply_shift(b, regs.xr(decoded.rm), decoded.shift_type, decoded.shift_amount, sf)
            if not sf:
                rhs = b.uext(XLEN_SORT, b.slice(W32_SORT, rhs, 31, 0), 32)
        if not sf:
            rn_v_used = b.uext(XLEN_SORT, b.slice(W32_SORT, rn_v, 31, 0), 32)
        else:
            rn_v_used = rn_v

        if is_sub or m == "CMP":
            r, nzcv_new = _nzcv_sub(b, rn_v_used, rhs, sf)
        else:
            r, nzcv_new = _nzcv_add(b, rn_v_used, rhs, sf)

        if decoded.sets_flags:
            res.nzcv_next = nzcv_new
        if m not in ("CMP", "CMN"):  # CMP/CMN discard result (rd=31 as XZR)
            dest_sp = decoded.rd == 31 and not decoded.sets_flags
            if dest_sp:
                res.sp_next = r
            else:
                write(decoded.rd, r)

    # -----------------------------------------------------------------------
    elif m in ("AND", "BIC", "ORR", "ORN", "EOR", "EON", "ANDS", "BICS"):
        rn_v = regs.xr(decoded.rn)
        if decoded.src_is_imm:
            rhs = _imm64(b, decoded.imm)
        else:
            rhs = _apply_shift(b, regs.xr(decoded.rm), decoded.shift_type, decoded.shift_amount, sf)
        # NOT variants
        if m in ("BIC", "ORN", "EON", "BICS"):
            if sf:
                rhs = b.not_(XLEN_SORT, rhs)
            else:
                rhs = b.uext(XLEN_SORT, b.not_(W32_SORT, b.slice(W32_SORT, rhs, 31, 0)), 32)
        if sf:
            if m in ("AND", "ANDS", "BIC", "BICS"):
                r = b.and_(XLEN_SORT, rn_v, rhs)
            elif m in ("ORR", "ORN"):
                r = b.or_(XLEN_SORT, rn_v, rhs)
            else:
                r = b.xor(XLEN_SORT, rn_v, rhs)
        else:
            rn32 = b.slice(W32_SORT, rn_v, 31, 0)
            rhs32 = b.slice(W32_SORT, rhs, 31, 0)
            if m in ("AND", "ANDS", "BIC", "BICS"):
                r32 = b.and_(W32_SORT, rn32, rhs32)
            elif m in ("ORR", "ORN"):
                r32 = b.or_(W32_SORT, rn32, rhs32)
            else:
                r32 = b.xor(W32_SORT, rn32, rhs32)
            r = b.uext(XLEN_SORT, r32, 32)
        if decoded.sets_flags or m in ("ANDS", "BICS"):
            res.nzcv_next = _nzcv_logical(b, r, sf)
        if m not in ("TST",):  # TST aliases to ANDS Xzr
            write(decoded.rd, r)

    # -----------------------------------------------------------------------
    elif m == "MOVZ":
        val = b.const(XLEN_SORT, (decoded.imm << decoded.shift_amount) & ((1 << 64) - 1))
        write(decoded.rd, val)

    elif m == "MOVK":
        old = regs.xr(decoded.rd)  # reg31 = XZR = 0
        shift = decoded.shift_amount
        fmask = (0xFFFF << shift) & ((1 << 64) - 1)
        val = b.or_(XLEN_SORT,
                    b.and_(XLEN_SORT, old, b.not_(XLEN_SORT, b.const(XLEN_SORT, fmask))),
                    b.const(XLEN_SORT, (decoded.imm << shift) & ((1 << 64) - 1)))
        write(decoded.rd, val)

    elif m == "MOVN":
        val = b.not_(XLEN_SORT, b.const(XLEN_SORT, (decoded.imm << decoded.shift_amount) & ((1 << 64) - 1)))
        write(decoded.rd, val)

    # -----------------------------------------------------------------------
    elif m == "ADR":
        # imm is the signed 21-bit offset; pc + imm
        r = b.add(XLEN_SORT, pc_nid, _imm64(b, decoded.imm))
        write(decoded.rd, r)

    elif m == "ADRP":
        # imm already encodes the page-aligned offset (immhi:immlo << 12, sext 33)
        page_pc = b.and_(XLEN_SORT, pc_nid, b.not_(XLEN_SORT, b.const(XLEN_SORT, 0xFFF)))
        r = b.add(XLEN_SORT, page_pc, _imm64(b, decoded.imm))
        write(decoded.rd, r)

    # -----------------------------------------------------------------------
    elif m == "UBFM":
        r = _ubfm(b, regs.xr(decoded.rn), decoded.immr, decoded.imms, sf)
        write(decoded.rd, r)

    elif m == "SBFM":
        r = _sbfm(b, regs.xr(decoded.rn), decoded.immr, decoded.imms, sf)
        write(decoded.rd, r)

    elif m == "BFM":
        r = _bfm(b, regs.xr(decoded.rd), regs.xr(decoded.rn), decoded.immr, decoded.imms, sf)
        write(decoded.rd, r)

    elif m == "EXTR":
        rn_v = regs.xr(decoded.rn)
        rm_v = regs.xr(decoded.rm)
        lsb = decoded.imm  # shift amount stored in imm by decoder
        if sf:
            combined = b.concat("bv128", rn_v, rm_v)
            r = b.slice(XLEN_SORT, combined, lsb + 63, lsb)
        else:
            rn32 = b.slice(W32_SORT, rn_v, 31, 0)
            rm32 = b.slice(W32_SORT, rm_v, 31, 0)
            combined = b.concat("bv64", rn32, rm32)
            r32 = b.slice(W32_SORT, combined, lsb + 31, lsb)
            r = b.uext(XLEN_SORT, r32, 32)
        write(decoded.rd, r)

    # -----------------------------------------------------------------------
    elif m in ("LSL", "LSR", "ASR", "ROR"):
        # Register-operand shift forms
        rn_v = regs.xr(decoded.rn)
        if sf:
            amount = b.slice("bv6", regs.xr(decoded.rm), 5, 0)
            amount64 = b.uext(XLEN_SORT, amount, 58)
            if m == "LSL":
                r = b.sll(XLEN_SORT, rn_v, amount64)
            elif m == "LSR":
                r = b.srl(XLEN_SORT, rn_v, amount64)
            elif m == "ASR":
                r = b.sra(XLEN_SORT, rn_v, amount64)
            else:  # ROR
                lo = b.srl(XLEN_SORT, rn_v, amount64)
                neg_amt = b.sub(XLEN_SORT, b.const(XLEN_SORT, 64), amount64)
                hi = b.sll(XLEN_SORT, rn_v, neg_amt)
                r = b.or_(XLEN_SORT, lo, hi)
        else:
            rn32 = b.slice(W32_SORT, rn_v, 31, 0)
            amount = b.slice("bv5", regs.xr(decoded.rm), 4, 0)
            amount32 = b.uext(W32_SORT, amount, 27)
            if m == "LSL":
                r32 = b.sll(W32_SORT, rn32, amount32)
            elif m == "LSR":
                r32 = b.srl(W32_SORT, rn32, amount32)
            elif m == "ASR":
                r32 = b.sra(W32_SORT, rn32, amount32)
            else:  # ROR
                lo = b.srl(W32_SORT, rn32, amount32)
                neg_amt = b.sub(W32_SORT, b.const(W32_SORT, 32), amount32)
                hi = b.sll(W32_SORT, rn32, neg_amt)
                r32 = b.or_(W32_SORT, lo, hi)
            r = b.uext(XLEN_SORT, r32, 32)
        write(decoded.rd, r)

    # -----------------------------------------------------------------------
    elif m == "MADD":
        rn_v = regs.xr(decoded.rn)
        rm_v = regs.xr(decoded.rm)
        ra_v = regs.xr(decoded.ra)
        if sf:
            r = b.add(XLEN_SORT, ra_v, b.mul(XLEN_SORT, rn_v, rm_v))
        else:
            rn32 = b.slice(W32_SORT, rn_v, 31, 0)
            rm32 = b.slice(W32_SORT, rm_v, 31, 0)
            ra32 = b.slice(W32_SORT, ra_v, 31, 0)
            r = b.uext(XLEN_SORT, b.add(W32_SORT, ra32, b.mul(W32_SORT, rn32, rm32)), 32)
        write(decoded.rd, r)

    elif m == "MSUB":
        rn_v = regs.xr(decoded.rn)
        rm_v = regs.xr(decoded.rm)
        ra_v = regs.xr(decoded.ra)
        if sf:
            r = b.sub(XLEN_SORT, ra_v, b.mul(XLEN_SORT, rn_v, rm_v))
        else:
            rn32 = b.slice(W32_SORT, rn_v, 31, 0)
            rm32 = b.slice(W32_SORT, rm_v, 31, 0)
            ra32 = b.slice(W32_SORT, ra_v, 31, 0)
            r = b.uext(XLEN_SORT, b.sub(W32_SORT, ra32, b.mul(W32_SORT, rn32, rm32)), 32)
        write(decoded.rd, r)

    elif m == "SMADDL":
        rn32 = b.sext(XLEN_SORT, b.slice(W32_SORT, regs.xr(decoded.rn), 31, 0), 32)
        rm32 = b.sext(XLEN_SORT, b.slice(W32_SORT, regs.xr(decoded.rm), 31, 0), 32)
        ra_v = regs.xr(decoded.ra)
        r = b.add(XLEN_SORT, ra_v, b.mul(XLEN_SORT, rn32, rm32))
        write(decoded.rd, r)

    elif m == "SMSUBL":
        rn32 = b.sext(XLEN_SORT, b.slice(W32_SORT, regs.xr(decoded.rn), 31, 0), 32)
        rm32 = b.sext(XLEN_SORT, b.slice(W32_SORT, regs.xr(decoded.rm), 31, 0), 32)
        ra_v = regs.xr(decoded.ra)
        r = b.sub(XLEN_SORT, ra_v, b.mul(XLEN_SORT, rn32, rm32))
        write(decoded.rd, r)

    elif m == "UMADDL":
        rn32 = b.uext(XLEN_SORT, b.slice(W32_SORT, regs.xr(decoded.rn), 31, 0), 32)
        rm32 = b.uext(XLEN_SORT, b.slice(W32_SORT, regs.xr(decoded.rm), 31, 0), 32)
        ra_v = regs.xr(decoded.ra)
        r = b.add(XLEN_SORT, ra_v, b.mul(XLEN_SORT, rn32, rm32))
        write(decoded.rd, r)

    elif m == "UMSUBL":
        rn32 = b.uext(XLEN_SORT, b.slice(W32_SORT, regs.xr(decoded.rn), 31, 0), 32)
        rm32 = b.uext(XLEN_SORT, b.slice(W32_SORT, regs.xr(decoded.rm), 31, 0), 32)
        ra_v = regs.xr(decoded.ra)
        r = b.sub(XLEN_SORT, ra_v, b.mul(XLEN_SORT, rn32, rm32))
        write(decoded.rd, r)

    elif m == "SMULH":
        rn_ext = b.sext("bv128", regs.xr(decoded.rn), 64)
        rm_ext = b.sext("bv128", regs.xr(decoded.rm), 64)
        prod = b.mul("bv128", rn_ext, rm_ext)
        write(decoded.rd, b.slice(XLEN_SORT, prod, 127, 64))

    elif m == "UMULH":
        rn_ext = b.uext("bv128", regs.xr(decoded.rn), 64)
        rm_ext = b.uext("bv128", regs.xr(decoded.rm), 64)
        prod = b.mul("bv128", rn_ext, rm_ext)
        write(decoded.rd, b.slice(XLEN_SORT, prod, 127, 64))

    elif m == "SDIV":
        write(decoded.rd, _sdiv_a64(b, regs.xr(decoded.rn), regs.xr(decoded.rm), sf))

    elif m == "UDIV":
        write(decoded.rd, _udiv_a64(b, regs.xr(decoded.rn), regs.xr(decoded.rm), sf))

    # -----------------------------------------------------------------------
    elif m == "CSEL":
        cond_val = evaluate_condition(b, decoded.cond, nzcv_nid)
        rn_v = regs.xr(decoded.rn)
        rm_v = regs.xr(decoded.rm)
        if not sf:
            rn_v = b.uext(XLEN_SORT, b.slice(W32_SORT, rn_v, 31, 0), 32)
            rm_v = b.uext(XLEN_SORT, b.slice(W32_SORT, rm_v, 31, 0), 32)
        write(decoded.rd, b.ite(XLEN_SORT, cond_val, rn_v, rm_v))

    elif m == "CSINC":
        cond_val = evaluate_condition(b, decoded.cond, nzcv_nid)
        rn_v = regs.xr(decoded.rn)
        rm_v = regs.xr(decoded.rm)
        if sf:
            rm_inc = b.add(XLEN_SORT, rm_v, b.const(XLEN_SORT, 1))
            write(decoded.rd, b.ite(XLEN_SORT, cond_val, rn_v, rm_inc))
        else:
            rn32 = b.uext(XLEN_SORT, b.slice(W32_SORT, rn_v, 31, 0), 32)
            rm32 = b.uext(XLEN_SORT, b.slice(W32_SORT, rm_v, 31, 0), 32)
            rm_inc = b.add(XLEN_SORT, rm32, b.const(XLEN_SORT, 1))
            write(decoded.rd, b.ite(XLEN_SORT, cond_val, rn32, rm_inc))

    elif m == "CSINV":
        cond_val = evaluate_condition(b, decoded.cond, nzcv_nid)
        rn_v = regs.xr(decoded.rn)
        rm_v = regs.xr(decoded.rm)
        if sf:
            rm_inv = b.not_(XLEN_SORT, rm_v)
            write(decoded.rd, b.ite(XLEN_SORT, cond_val, rn_v, rm_inv))
        else:
            rn32 = b.uext(XLEN_SORT, b.slice(W32_SORT, rn_v, 31, 0), 32)
            rm32 = b.uext(XLEN_SORT, b.slice(W32_SORT, rm_v, 31, 0), 32)
            rm_inv = b.not_(XLEN_SORT, rm32)
            write(decoded.rd, b.ite(XLEN_SORT, cond_val, rn32, rm_inv))

    elif m == "CSNEG":
        cond_val = evaluate_condition(b, decoded.cond, nzcv_nid)
        rn_v = regs.xr(decoded.rn)
        rm_v = regs.xr(decoded.rm)
        if sf:
            rm_neg = b.neg(XLEN_SORT, rm_v)
            write(decoded.rd, b.ite(XLEN_SORT, cond_val, rn_v, rm_neg))
        else:
            rn32 = b.uext(XLEN_SORT, b.slice(W32_SORT, rn_v, 31, 0), 32)
            rm32 = b.uext(XLEN_SORT, b.slice(W32_SORT, rm_v, 31, 0), 32)
            rm_neg = b.neg(XLEN_SORT, rm32)
            write(decoded.rd, b.ite(XLEN_SORT, cond_val, rn32, rm_neg))

    # -----------------------------------------------------------------------
    elif m == "B":
        res.next_pc = b.add(XLEN_SORT, pc_nid, _imm64(b, decoded.imm))

    elif m == "BL":
        res.reg_writes[30] = _next_pc_seq(b, pc_nid)
        res.next_pc = b.add(XLEN_SORT, pc_nid, _imm64(b, decoded.imm))

    elif m == "BR":
        res.next_pc = regs.xr(decoded.rn)

    elif m == "BLR":
        res.reg_writes[30] = _next_pc_seq(b, pc_nid)
        res.next_pc = regs.xr(decoded.rn)

    elif m == "RET":
        res.next_pc = regs.xr(decoded.rn)  # decoder sets rn=30 by default

    elif m == "B.cond":
        cond_val = evaluate_condition(b, decoded.cond, nzcv_nid)
        taken_pc = b.add(XLEN_SORT, pc_nid, _imm64(b, decoded.imm))
        res.next_pc = b.ite(XLEN_SORT, cond_val, taken_pc, _next_pc_seq(b, pc_nid))
        res.branch_cond = cond_val

    elif m == "CBZ":
        # Decoder stores the compared register in rd (not rn) for CBZ/CBNZ/TBZ/TBNZ.
        rt_v = regs.xr(decoded.rd)
        if not sf:
            rt_v = b.uext(XLEN_SORT, b.slice(W32_SORT, rt_v, 31, 0), 32)
        cond_val = b.eq(rt_v, b.const(XLEN_SORT, 0))
        taken_pc = b.add(XLEN_SORT, pc_nid, _imm64(b, decoded.imm))
        res.next_pc = b.ite(XLEN_SORT, cond_val, taken_pc, _next_pc_seq(b, pc_nid))
        res.branch_cond = cond_val

    elif m == "CBNZ":
        rt_v = regs.xr(decoded.rd)
        if not sf:
            rt_v = b.uext(XLEN_SORT, b.slice(W32_SORT, rt_v, 31, 0), 32)
        cond_val = b.neq(rt_v, b.const(XLEN_SORT, 0))
        taken_pc = b.add(XLEN_SORT, pc_nid, _imm64(b, decoded.imm))
        res.next_pc = b.ite(XLEN_SORT, cond_val, taken_pc, _next_pc_seq(b, pc_nid))
        res.branch_cond = cond_val

    elif m == "TBZ":
        rt_v = regs.xr(decoded.rd)
        bit = decoded.bit_pos
        bit_val = b.slice(BV1, rt_v, bit, bit)
        cond_val = b.eq(bit_val, b.const(BV1, 0))
        taken_pc = b.add(XLEN_SORT, pc_nid, _imm64(b, decoded.imm))
        res.next_pc = b.ite(XLEN_SORT, cond_val, taken_pc, _next_pc_seq(b, pc_nid))
        res.branch_cond = cond_val

    elif m == "TBNZ":
        rt_v = regs.xr(decoded.rd)
        bit = decoded.bit_pos
        bit_val = b.slice(BV1, rt_v, bit, bit)
        cond_val = b.neq(bit_val, b.const(BV1, 0))
        taken_pc = b.add(XLEN_SORT, pc_nid, _imm64(b, decoded.imm))
        res.next_pc = b.ite(XLEN_SORT, cond_val, taken_pc, _next_pc_seq(b, pc_nid))
        res.branch_cond = cond_val

    # -----------------------------------------------------------------------
    elif m in ("LDR", "LDRB", "LDRH", "LDRSB", "LDRSH", "LDRSW"):
        addr, wb_val, wb_reg = _compute_addr(b, regs, decoded)
        if m == "LDR":
            n = 8 if sf else 4
            raw = _load_bytes_le(b, mem_nid, addr, n)
            r = b.uext(XLEN_SORT, raw, 64 - 8*n) if n < 8 else raw  # 32-bit → zero-extend
        elif m == "LDRB":
            raw = _load_bytes_le(b, mem_nid, addr, 1)
            r = b.uext(XLEN_SORT, raw, 56)
        elif m == "LDRH":
            raw = _load_bytes_le(b, mem_nid, addr, 2)
            r = b.uext(XLEN_SORT, raw, 48)
        elif m == "LDRSB":
            raw = _load_bytes_le(b, mem_nid, addr, 1)
            if sf:
                r = b.sext(XLEN_SORT, raw, 56)
            else:
                r = b.uext(XLEN_SORT, b.sext(W32_SORT, raw, 24), 32)
        elif m == "LDRSH":
            raw = _load_bytes_le(b, mem_nid, addr, 2)
            if sf:
                r = b.sext(XLEN_SORT, raw, 48)
            else:
                r = b.uext(XLEN_SORT, b.sext(W32_SORT, raw, 16), 32)
        elif m == "LDRSW":
            raw = _load_bytes_le(b, mem_nid, addr, 4)
            r = b.sext(XLEN_SORT, raw, 32)
        else:
            raise AssertionError("unreachable")
        write(decoded.rd, r)
        _writeback(res, wb_reg, wb_val, regs)

    elif m in ("STR", "STRB", "STRH"):
        addr, wb_val, wb_reg = _compute_addr(b, regs, decoded)
        val = regs.xr(decoded.rd)  # rd = Rt (source register for stores)
        if m == "STR":
            n = 8 if sf else 4
            res.mem_next = _store_bytes_le(b, mem_nid, addr, val, n)
        elif m == "STRB":
            res.mem_next = _store_bytes_le(b, mem_nid, addr, val, 1)
        elif m == "STRH":
            res.mem_next = _store_bytes_le(b, mem_nid, addr, val, 2)
        _writeback(res, wb_reg, wb_val, regs)

    elif m == "LDP":
        addr, wb_val, wb_reg = _compute_addr(b, regs, decoded)
        n = 8 if sf else 4
        v0 = _load_bytes_le(b, mem_nid, addr, n)
        addr1 = b.add(XLEN_SORT, addr, b.const(XLEN_SORT, n))
        v1 = _load_bytes_le(b, mem_nid, addr1, n)
        if n < 8:
            v0 = b.uext(XLEN_SORT, v0, 64 - 8*n)
            v1 = b.uext(XLEN_SORT, v1, 64 - 8*n)
        write(decoded.rd, v0)   # rt1
        write(decoded.rt2, v1)  # rt2
        _writeback(res, wb_reg, wb_val, regs)

    elif m == "STP":
        addr, wb_val, wb_reg = _compute_addr(b, regs, decoded)
        n = 8 if sf else 4
        val0 = regs.xr(decoded.rd)   # rt1
        val1 = regs.xr(decoded.rt2)  # rt2
        m0 = _store_bytes_le(b, mem_nid, addr, val0, n)
        addr1 = b.add(XLEN_SORT, addr, b.const(XLEN_SORT, n))
        m1 = _store_bytes_le(b, m0, addr1, val1, n)
        res.mem_next = m1
        _writeback(res, wb_reg, wb_val, regs)

    # -----------------------------------------------------------------------
    elif m in ("SVC", "BRK"):
        res.halt_next = b.const(BV1, 1)
        res.next_pc = pc_nid  # freeze PC

    elif m == "NOP":
        pass

    else:
        raise NotImplementedError(f"library: unsupported mnemonic {m!r}")

    return res


SUPPORTED_MNEMONICS = (
    "ADD", "SUB", "ADDS", "SUBS", "CMP", "CMN",
    "AND", "BIC", "ORR", "ORN", "EOR", "EON", "ANDS", "BICS",
    "MOVZ", "MOVK", "MOVN",
    "ADR", "ADRP",
    "UBFM", "SBFM", "BFM", "EXTR",
    "LSL", "LSR", "ASR", "ROR",
    "MADD", "MSUB", "SMADDL", "SMSUBL", "UMADDL", "UMSUBL", "SMULH", "UMULH",
    "SDIV", "UDIV",
    "CSEL", "CSINC", "CSINV", "CSNEG",
    "B", "BL", "BR", "BLR", "RET",
    "B.cond", "CBZ", "CBNZ", "TBZ", "TBNZ",
    "LDR", "LDRB", "LDRH", "LDRSB", "LDRSH", "LDRSW",
    "STR", "STRB", "STRH",
    "LDP", "STP",
    "SVC", "BRK", "NOP",
)


__all__ = ["lower", "evaluate_condition", "RegSnapshot", "LoweringResult", "SUPPORTED_MNEMONICS"]
