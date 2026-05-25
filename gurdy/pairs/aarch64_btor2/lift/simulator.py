"""Concrete AArch64 (A64) simulator — source-interpreter ground truth.

Architectural state:
- 31 64-bit GPRs: x0–x30. x31 is NOT a state variable; it is
  XZR (reads 0, writes discarded) in data-processing contexts and
  SP (separate state) in memory/stack contexts.
- sp: 64-bit stack pointer.
- pc: 64-bit program counter.
- nzcv: 4-bit condition flags (N=bit3, Z=bit2, C=bit1, V=bit0).
- halted: bool.
- mem: sparse byte dict {addr: byte}.

AArch64 divergences from RV64 (SCHEMA.md §14):
- SDIV/UDIV div-by-zero → 0 (RV64: -1 / 2^64-1).
- W-register results zero-extend to 64 bits (RV64 *W sign-extend).
- XZR/SP duality at register 31.
- NZCV carry: C=1 means no-borrow for SUBS (arm convention).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gurdy.pairs.aarch64_btor2.source.decoder import Decoded, decode


MASK64 = (1 << 64) - 1
MASK32 = (1 << 32) - 1
SIGN64 = 1 << 63
SIGN32 = 1 << 31


def _u64(x: int) -> int:
    return x & MASK64


def _s64(x: int) -> int:
    x &= MASK64
    return x - (1 << 64) if x & SIGN64 else x


def _u32(x: int) -> int:
    return x & MASK32


def _s32(x: int) -> int:
    x &= MASK32
    return x - (1 << 32) if x & SIGN32 else x


def _sext(value: int, width: int) -> int:
    sign = 1 << (width - 1)
    return (value ^ sign) - sign


# ---------------------------------------------------------------------------
# NZCV helpers
# ---------------------------------------------------------------------------


def _nzcv_add(lhs: int, rhs: int, sf: bool) -> tuple[int, int]:
    """Compute result and NZCV for an ADD-like operation."""
    if sf:
        width, sign_bit, ext_width = 64, SIGN64, 65
    else:
        width, sign_bit, ext_width = 32, SIGN32, 33
    mask = (1 << width) - 1
    sum65 = (lhs & mask) + (rhs & mask)
    r = sum65 & mask
    n = int(bool(r & sign_bit))
    z = int(r == 0)
    c = int(bool(sum65 >> width))
    # V: both inputs same sign, result different sign
    v = int(bool((lhs & sign_bit) == (rhs & sign_bit)) and bool((r & sign_bit) != (lhs & sign_bit)))
    return r, (n << 3) | (z << 2) | (c << 1) | v


def _nzcv_sub(lhs: int, rhs: int, sf: bool) -> tuple[int, int]:
    """Compute result and NZCV for a SUB-like operation (AArch64 carry convention)."""
    if sf:
        width, sign_bit = 64, SIGN64
    else:
        width, sign_bit = 32, SIGN32
    mask = (1 << width) - 1
    lhs &= mask
    rhs &= mask
    rhs_inv = (~rhs) & mask
    sum65 = lhs + rhs_inv + 1
    r = sum65 & mask
    n = int(bool(r & sign_bit))
    z = int(r == 0)
    c = int(bool(sum65 >> width))  # C=1 iff no borrow (lhs >= rhs unsigned)
    v = int(bool((lhs & sign_bit) != (rhs & sign_bit)) and bool((r & sign_bit) != (lhs & sign_bit)))
    return r, (n << 3) | (z << 2) | (c << 1) | v


def _nzcv_logical(r: int, sf: bool) -> int:
    """NZCV for AND/ORR/EOR/BIC/ANDS/BICS: C=0, V=0."""
    sign_bit = SIGN64 if sf else SIGN32
    mask = MASK64 if sf else MASK32
    r &= mask
    n = int(bool(r & sign_bit))
    z = int(r == 0)
    return (n << 3) | (z << 2)


def _eval_cond(cond: int, nzcv: int) -> bool:
    """Evaluate a standard A64 condition code against nzcv."""
    n = bool(nzcv & 8)
    z = bool(nzcv & 4)
    c = bool(nzcv & 2)
    v = bool(nzcv & 1)
    if cond == 0b0000: return z           # EQ
    if cond == 0b0001: return not z       # NE
    if cond == 0b0010: return c           # CS/HS
    if cond == 0b0011: return not c       # CC/LO
    if cond == 0b0100: return n           # MI
    if cond == 0b0101: return not n       # PL
    if cond == 0b0110: return v           # VS
    if cond == 0b0111: return not v       # VC
    if cond == 0b1000: return c and not z  # HI
    if cond == 0b1001: return not c or z  # LS
    if cond == 0b1010: return n == v      # GE
    if cond == 0b1011: return n != v      # LT
    if cond == 0b1100: return (not z) and (n == v)  # GT
    if cond == 0b1101: return z or (n != v)          # LE
    return True  # 0b1110 = AL


# ---------------------------------------------------------------------------
# Shift/extend helpers
# ---------------------------------------------------------------------------


def _apply_shift(val: int, shift_type: int, amount: int, sf: bool) -> int:
    mask = MASK64 if sf else MASK32
    val &= mask
    amount &= (63 if sf else 31)
    if shift_type == 0:  # LSL
        return _u64(val << amount) & mask
    if shift_type == 1:  # LSR
        return val >> amount
    if shift_type == 2:  # ASR
        width = 64 if sf else 32
        return _u64(_sext(val, width) >> amount) & mask
    if shift_type == 3:  # ROR
        if amount == 0:
            return val
        width = 64 if sf else 32
        return ((val >> amount) | (val << (width - amount))) & mask
    return val


def _apply_extend(val: int, ext_type: int, shift: int) -> int:
    """Extended-register operand: extract, sign/zero-extend, then shift left."""
    if ext_type == 0:   result = val & 0xFF            # UXTB
    elif ext_type == 1: result = val & 0xFFFF           # UXTH
    elif ext_type == 2: result = val & 0xFFFFFFFF       # UXTW
    elif ext_type == 3: result = val & MASK64            # UXTX
    elif ext_type == 4: result = _u64(_sext(val & 0xFF, 8))           # SXTB
    elif ext_type == 5: result = _u64(_sext(val & 0xFFFF, 16))        # SXTH
    elif ext_type == 6: result = _u64(_sext(val & 0xFFFFFFFF, 32))    # SXTW
    else:               result = _u64(val)                              # SXTX
    return _u64(result << shift)


# ---------------------------------------------------------------------------
# Bitfield operations (SBFM/UBFM/BFM)
# ---------------------------------------------------------------------------


def _ubfm(src: int, immr: int, imms: int, sf: bool) -> int:
    """UBFM (Unsigned Bitfield Move) per ARM DDI A-profile §C4.4."""
    width = 64 if sf else 32
    src &= (1 << width) - 1
    if imms >= immr:
        # Extract [imms:immr] and zero-extend
        nbits = imms - immr + 1
        result = (src >> immr) & ((1 << nbits) - 1)
    else:
        # ROR by immr, then zero the high bits above bit imms
        nbits = imms + 1
        rotated = ((src >> immr) | (src << (width - immr))) & ((1 << width) - 1)
        result = rotated & ((1 << nbits) - 1)
    return result & MASK64


def _sbfm(src: int, immr: int, imms: int, sf: bool) -> int:
    """SBFM (Signed Bitfield Move): same as UBFM then sign-extend."""
    width = 64 if sf else 32
    src &= (1 << width) - 1
    if imms >= immr:
        nbits = imms - immr + 1
        extracted = (src >> immr) & ((1 << nbits) - 1)
        result = _u64(_sext(extracted, nbits))
    else:
        nbits = imms + 1
        rotated = ((src >> immr) | (src << (width - immr))) & ((1 << width) - 1)
        extracted = rotated & ((1 << nbits) - 1)
        result = _u64(_sext(extracted, nbits))
    return result & MASK64


def _bfm(dst: int, src: int, immr: int, imms: int, sf: bool) -> int:
    """BFM: copy bits from src into dst."""
    width = 64 if sf else 32
    src &= (1 << width) - 1
    dst &= (1 << width) - 1
    if imms >= immr:
        # Copy [imms:immr] of src into dst at same position
        nbits = imms - immr + 1
        mask = ((1 << nbits) - 1) << immr
        result = (dst & ~mask) | ((src << immr) & mask)
    else:
        # Copy [imms:0] of src into the top of dst
        nbits = imms + 1
        src_bits = src & ((1 << nbits) - 1)
        shift = width - immr
        result = (dst & ~(((1 << nbits) - 1) << shift)) | (src_bits << shift)
    return result & MASK64


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class State:
    regs: list[int] = field(default_factory=lambda: [0] * 31)
    sp: int = 0
    pc: int = 0
    nzcv: int = 0
    halted: bool = False
    mem: dict[int, int] = field(default_factory=dict)

    def read_reg(self, n: int, sp_context: bool = False) -> int:
        """Read register. n=31 returns SP (sp_context) or 0 (XZR)."""
        if n == 31:
            return _u64(self.sp) if sp_context else 0
        return _u64(self.regs[n])

    def write_reg(self, n: int, v: int, sp_context: bool = False) -> None:
        """Write register. n=31 writes SP or discards (XZR)."""
        if n == 31:
            if sp_context:
                self.sp = _u64(v)
            # else XZR — discard
            return
        self.regs[n] = _u64(v)

    def load_byte(self, addr: int) -> int:
        return self.mem.get(_u64(addr), 0) & 0xFF

    def store_byte(self, addr: int, value: int) -> None:
        self.mem[_u64(addr)] = value & 0xFF

    def load_le(self, addr: int, n: int) -> int:
        v = 0
        for i in range(n):
            v |= self.load_byte(addr + i) << (8 * i)
        return v

    def store_le(self, addr: int, value: int, n: int) -> None:
        for i in range(n):
            self.store_byte(addr + i, (value >> (8 * i)) & 0xFF)

    def clone(self) -> "State":
        return State(
            regs=list(self.regs),
            sp=self.sp,
            pc=self.pc,
            nzcv=self.nzcv,
            halted=self.halted,
            mem=dict(self.mem),
        )


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------


def step(state: State, d: Decoded) -> State:
    """Execute one decoded instruction; returns new state."""
    s = state.clone()
    if s.halted:
        return s
    m = d.mnemonic
    pc = s.pc
    next_pc = _u64(pc + 4)
    sf = d.sf
    mask = MASK64 if sf else MASK32

    # --- helper: read a GPR in data context (XZR at 31) ---
    def xr(n: int) -> int:
        return s.read_reg(n, sp_context=False)

    # --- helper: read in SP context (SP at 31) ---
    def spr(n: int) -> int:
        return s.read_reg(n, sp_context=True)

    # --- helper: write (XZR discards) ---
    def wr(n: int, v: int) -> None:
        if sf:
            s.write_reg(n, _u64(v))
        else:
            s.write_reg(n, _u64(v & MASK32))  # W-reg: zero-extend to 64

    # --- helper: write in SP context ---
    def wsp(n: int, v: int) -> None:
        s.write_reg(n, v, sp_context=True)

    # -----------------------------------------------------------------
    # Data processing — immediate
    # -----------------------------------------------------------------

    if m in ("ADD", "ADDS", "SUB", "SUBS"):
        is_sub = m in ("SUB", "SUBS")
        # R31 is SP for immediate and extended-register forms; XZR for shifted-register
        use_sp = d.rn == 31 and (d.src_is_imm or d.addr_mode == "ext_reg")
        rn_v = spr(d.rn) if use_sp else xr(d.rn)
        if d.src_is_imm:
            rhs = _u64(d.imm) & mask
        elif d.addr_mode == "ext_reg":
            rhs = _apply_extend(xr(d.rm), d.extend_type, d.shift_amount) & mask
        else:
            rhs = _apply_shift(xr(d.rm), d.shift_type, d.shift_amount, sf) & mask
        rn_v &= mask
        if is_sub:
            r, nzcv = _nzcv_sub(rn_v, rhs, sf)
        else:
            r, nzcv = _nzcv_add(rn_v, rhs, sf)
        if d.sets_flags:
            s.nzcv = nzcv
        # Rd=31 for CMP/CMN → discard result but keep NZCV
        # Rd=31 for ADD/SUB sp-manipulation → write SP
        dest_sp = (d.rd == 31 and not d.sets_flags)
        if dest_sp:
            wsp(d.rd, r)
        else:
            wr(d.rd, r)

    elif m in ("AND", "BIC", "ORR", "ORN", "EOR", "EON", "ANDS", "BICS"):
        if d.src_is_imm:
            rhs = _u64(d.imm) & mask
        else:
            rm_v = _apply_shift(xr(d.rm), d.shift_type, d.shift_amount, sf)
            rhs = ((~rm_v) & mask) if m in ("BIC", "ORN", "EON", "BICS") else (rm_v & mask)
        rn_v = xr(d.rn) & mask
        if m in ("AND", "ANDS", "BIC", "BICS"):
            r = rn_v & rhs
        elif m in ("ORR", "ORN"):
            r = rn_v | rhs
        else:  # EOR, EON
            r = rn_v ^ rhs
        if d.sets_flags:
            s.nzcv = _nzcv_logical(r, sf)
        wr(d.rd, r)

    elif m == "MOVZ":
        wr(d.rd, (d.imm << d.shift_amount) & mask)

    elif m == "MOVK":
        old = xr(d.rd) if d.rd != 31 else 0
        old &= mask
        shift = d.shift_amount
        field_mask = (0xFFFF << shift) & mask
        wr(d.rd, (old & ~field_mask) | ((d.imm << shift) & mask))

    elif m == "MOVN":
        wr(d.rd, (~(d.imm << d.shift_amount)) & mask)

    elif m == "ADR":
        s.write_reg(d.rd, _u64(pc + d.imm))

    elif m == "ADRP":
        page_pc = pc & ~0xFFF
        s.write_reg(d.rd, _u64(page_pc + d.imm))

    # -----------------------------------------------------------------
    # Bitfield
    # -----------------------------------------------------------------

    elif m == "UBFM":
        r = _ubfm(xr(d.rn), d.immr, d.imms, sf)
        s.write_reg(d.rd, r)

    elif m == "SBFM":
        r = _sbfm(xr(d.rn), d.immr, d.imms, sf)
        s.write_reg(d.rd, r)

    elif m == "BFM":
        r = _bfm(xr(d.rd), xr(d.rn), d.immr, d.imms, sf)
        s.write_reg(d.rd, r)

    elif m == "EXTR":
        rn_v = xr(d.rn)
        rm_v = xr(d.rm)
        lsb = d.imm  # shift amount
        if sf:
            combined = ((rn_v & MASK64) << 64) | (rm_v & MASK64)
            r = (combined >> lsb) & MASK64
        else:
            combined = ((_u32(rn_v)) << 32) | _u32(rm_v)
            r = _u64((combined >> lsb) & MASK32)
        s.write_reg(d.rd, r)

    # -----------------------------------------------------------------
    # Shifts (register-operand form: mnemonic=LSL/LSR/ASR/ROR)
    # -----------------------------------------------------------------

    elif m in ("LSL", "LSR", "ASR", "ROR"):
        rn_v = xr(d.rn) & mask
        if d.rm != 0 or d.shift_type != 0 or d.shift_amount != 0:
            # Register shift: amount from Rm
            amount = xr(d.rm) & (63 if sf else 31)
            r = _apply_shift(rn_v, d.shift_type, amount, sf)
        else:
            r = rn_v  # no-op (shouldn't happen with valid decode)
        wr(d.rd, r)

    # -----------------------------------------------------------------
    # Multiply and divide
    # -----------------------------------------------------------------

    elif m == "MADD":
        rn_v = xr(d.rn) & mask
        rm_v = xr(d.rm) & mask
        ra_v = xr(d.ra) & mask
        r = _u64(ra_v + rn_v * rm_v)
        if not sf:
            r = _u64(r & MASK32)
        wr(d.rd, r)

    elif m == "MSUB":
        rn_v = xr(d.rn) & mask
        rm_v = xr(d.rm) & mask
        ra_v = xr(d.ra) & mask
        r = _u64(ra_v - (rn_v * rm_v))
        if not sf:
            r = _u64(r & MASK32)
        wr(d.rd, r)

    elif m == "SMADDL":
        rn_v = _s32(_u32(xr(d.rn)))
        rm_v = _s32(_u32(xr(d.rm)))
        ra_v = _s64(xr(d.ra))
        r = _u64(ra_v + rn_v * rm_v)
        s.write_reg(d.rd, r)

    elif m == "SMSUBL":
        rn_v = _s32(_u32(xr(d.rn)))
        rm_v = _s32(_u32(xr(d.rm)))
        ra_v = _s64(xr(d.ra))
        r = _u64(ra_v - rn_v * rm_v)
        s.write_reg(d.rd, r)

    elif m == "UMADDL":
        rn_v = _u32(xr(d.rn))
        rm_v = _u32(xr(d.rm))
        ra_v = xr(d.ra)
        r = _u64(ra_v + rn_v * rm_v)
        s.write_reg(d.rd, r)

    elif m == "UMSUBL":
        rn_v = _u32(xr(d.rn))
        rm_v = _u32(xr(d.rm))
        ra_v = xr(d.ra)
        r = _u64(ra_v - rn_v * rm_v)
        s.write_reg(d.rd, r)

    elif m == "SMULH":
        # High 64 of signed 128-bit product
        rn_v = _s64(xr(d.rn))
        rm_v = _s64(xr(d.rm))
        prod = rn_v * rm_v  # Python arbitrary precision
        r = _u64((prod >> 64) & MASK64)
        s.write_reg(d.rd, r)

    elif m == "UMULH":
        rn_v = xr(d.rn)
        rm_v = xr(d.rm)
        prod = rn_v * rm_v
        r = _u64((prod >> 64) & MASK64)
        s.write_reg(d.rd, r)

    elif m == "SDIV":
        if sf:
            rn_v = _s64(xr(d.rn))
            rm_v = _s64(xr(d.rm))
            INT_MIN = -(1 << 63)
        else:
            rn_v = _s32(_u32(xr(d.rn)))
            rm_v = _s32(_u32(xr(d.rm)))
            INT_MIN = -(1 << 31)
        if rm_v == 0:
            r = 0
        elif rn_v == INT_MIN and rm_v == -1:
            r = _u64(INT_MIN)
        else:
            # truncate toward zero
            q = -((-rn_v) // rm_v) if (rn_v < 0) ^ (rm_v < 0) and rn_v % rm_v != 0 else rn_v // rm_v
            r = _u64(q) & mask
        wr(d.rd, r)

    elif m == "UDIV":
        if sf:
            rn_v = xr(d.rn)
            rm_v = xr(d.rm)
        else:
            rn_v = _u32(xr(d.rn))
            rm_v = _u32(xr(d.rm))
        r = 0 if rm_v == 0 else (rn_v // rm_v)
        wr(d.rd, r)

    # -----------------------------------------------------------------
    # Branches
    # -----------------------------------------------------------------

    elif m == "B":
        next_pc = _u64(pc + d.imm)

    elif m == "BL":
        s.write_reg(30, _u64(pc + 4))
        next_pc = _u64(pc + d.imm)

    elif m == "BR":
        next_pc = xr(d.rn)

    elif m == "BLR":
        s.write_reg(30, _u64(pc + 4))
        next_pc = xr(d.rn)

    elif m == "RET":
        next_pc = xr(d.rn)  # default rn=30 per decoder

    elif m == "B.cond":
        if _eval_cond(d.cond, s.nzcv):
            next_pc = _u64(pc + d.imm)

    elif m == "CBZ":
        rt_v = xr(d.rd) & mask
        if rt_v == 0:
            next_pc = _u64(pc + d.imm)

    elif m == "CBNZ":
        rt_v = xr(d.rd) & mask
        if rt_v != 0:
            next_pc = _u64(pc + d.imm)

    elif m == "TBZ":
        rt_v = xr(d.rd)
        if not (rt_v >> d.bit_pos) & 1:
            next_pc = _u64(pc + d.imm)

    elif m == "TBNZ":
        rt_v = xr(d.rd)
        if (rt_v >> d.bit_pos) & 1:
            next_pc = _u64(pc + d.imm)

    # -----------------------------------------------------------------
    # Loads and Stores
    # -----------------------------------------------------------------

    elif m in ("LDR", "LDRB", "LDRH", "LDRSB", "LDRSH", "LDRSW",
               "STR", "STRB", "STRH", "LDP", "STP"):
        nbytes = {"LDR": 8 if sf else 4, "LDRB": 1, "LDRH": 2,
                  "LDRSB": 1, "LDRSH": 2, "LDRSW": 4,
                  "STR": 8 if sf else 4, "STRB": 1, "STRH": 2,
                  "LDP": 8 if sf else 4, "STP": 8 if sf else 4}.get(m, 8)

        # Compute effective address
        if d.addr_mode == "literal":
            addr = _u64(pc + d.imm)
            writeback = False
        elif d.addr_mode in ("base_imm", "base"):
            addr = _u64(spr(d.rn) + d.imm)
            writeback = False
        elif d.addr_mode == "pre":
            addr = _u64(spr(d.rn) + d.imm)
            writeback = True
            wb_val = addr
        elif d.addr_mode == "post":
            addr = spr(d.rn)
            writeback = True
            wb_val = _u64(addr + d.imm)
        elif d.addr_mode == "base_reg":
            ext = _apply_extend(xr(d.rm), d.extend_type, d.shift_amount)
            addr = _u64(spr(d.rn) + ext)
            writeback = False
        else:
            addr = spr(d.rn)
            writeback = False

        if m == "LDP":
            v0 = s.load_le(addr, nbytes)
            v1 = s.load_le(addr + nbytes, nbytes)
            if sf:
                s.write_reg(d.rd, _u64(v0))
                s.write_reg(d.rt2, _u64(v1))
            else:
                s.write_reg(d.rd, _u64(v0 & MASK32))
                s.write_reg(d.rt2, _u64(v1 & MASK32))
        elif m == "STP":
            v0 = xr(d.rd) if d.rd != 31 else 0
            v1 = xr(d.rt2) if d.rt2 != 31 else 0
            s.store_le(addr, v0, nbytes)
            s.store_le(addr + nbytes, v1, nbytes)
        elif m in ("STR", "STRB", "STRH"):
            rt_v = xr(d.rd) if d.rd != 31 else 0
            s.store_le(addr, rt_v, nbytes)
        else:  # loads
            raw = s.load_le(addr, nbytes)
            if m == "LDR":
                r = _u64(raw & (MASK64 if sf else MASK32))
            elif m == "LDRB":
                r = raw & 0xFF
            elif m == "LDRH":
                r = raw & 0xFFFF
            elif m == "LDRSB":
                raw8 = raw & 0xFF
                r = _u64(_sext(raw8, 8)) if sf else _u64(_sext(raw8, 8) & MASK32)
            elif m == "LDRSH":
                raw16 = raw & 0xFFFF
                r = _u64(_sext(raw16, 16)) if sf else _u64(_sext(raw16, 16) & MASK32)
            elif m == "LDRSW":
                r = _u64(_sext(raw & MASK32, 32))
            else:
                r = raw
            s.write_reg(d.rd, r)

        if writeback:
            wsp(d.rn, wb_val)

    # -----------------------------------------------------------------
    # Conditional select
    # -----------------------------------------------------------------

    elif m in ("CSEL", "CSINC", "CSINV", "CSNEG"):
        cond_val = _eval_cond(d.cond, s.nzcv)
        rn_v = xr(d.rn) & mask
        rm_v = xr(d.rm) & mask
        if cond_val:
            r = rn_v
        elif m == "CSEL":
            r = rm_v
        elif m == "CSINC":
            r = _u64(rm_v + 1) & mask
        elif m == "CSINV":
            r = (~rm_v) & mask
        else:  # CSNEG
            r = _u64(-_s64(rm_v)) & mask
        wr(d.rd, r)

    # -----------------------------------------------------------------
    # System / NOP
    # -----------------------------------------------------------------

    elif m == "NOP":
        pass

    elif m in ("SVC", "BRK"):
        s.halted = True
        next_pc = pc  # freeze PC on halt

    else:
        raise NotImplementedError(f"aarch64 simulator: unsupported {m!r}")

    if not s.halted:
        s.pc = next_pc
    return s


def fetch_from_memory_map(byte_map: dict[int, int]):
    """Build a fetch function that reads 4 bytes from a dict and decodes."""

    def _fetch(pc: int) -> Decoded | None:
        b0 = byte_map.get(pc)
        b1 = byte_map.get(pc + 1)
        b2 = byte_map.get(pc + 2)
        b3 = byte_map.get(pc + 3)
        if b0 is None or b1 is None or b2 is None or b3 is None:
            return None
        word = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
        return decode(word, pc)

    return _fetch


__all__ = ["State", "step", "fetch_from_memory_map"]
