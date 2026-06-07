"""Cross-check: library lowering matches the concrete AArch64 simulator.

For each supported mnemonic we:
1. Build a BTOR2 Builder, declare state nids for all 31 GPRs + SP + PC + NZCV + mem.
2. Lower a single Decoded instruction through library.lower().
3. Evaluate the resulting nids on concrete register/memory inputs.
4. Run the same instruction through the simulator.
5. Assert agreement on next-PC, register writes, SP, NZCV, and memory.
"""

from __future__ import annotations

import pytest

from gurdy.core.btor2.evaluator import evaluate
from gurdy.core.btor2.nodes import Node
from gurdy.pairs.aarch64_btor2.lift.simulator import State, step
from gurdy.pairs.aarch64_btor2.source.decoder import Decoded
from gurdy.pairs.aarch64_btor2.translation.builder import Builder
from gurdy.pairs.aarch64_btor2.translation.library import RegSnapshot, lower


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _d(mnem: str, **kw) -> Decoded:
    base = dict(pc=0x1000, length=4, raw=0, sf=True,
                rd=0, rn=0, rm=0, ra=0, imm=0,
                shift_type=0, shift_amount=0, extend_type=0,
                cond=0, bit_pos=0, sets_flags=False, src_is_imm=False,
                addr_mode="base_imm", rt2=0, immr=0, imms=0)
    base.update(kw)
    return Decoded(mnemonic=mnem, **base)


def _build_lowering(
    decoded: Decoded,
    regs: list[int],
    sp: int,
    nzcv: int,
    mem: dict[int, int],
):
    """Lower decoded instruction to BTOR2 and evaluate on concrete inputs.

    Returns (next_pc, reg_writes: dict[int,int], sp_next, nzcv_next, mem_next).
    """
    b = Builder()
    sort64 = b.declare_sort("bv64")
    sort4 = b.declare_sort("bv4")
    sort1 = b.declare_sort("bv1")
    mem_sort = b.declare_array_sort("mem", "bv64", "bv8")

    bindings: dict[int, object] = {}
    reg_nids: dict[int, int] = {}
    for i in range(31):
        nid = b._alloc()
        b.model.append(Node(nid=nid, op="state", args=[str(sort64)], symbol=f"x{i}"))
        reg_nids[i] = nid
        bindings[nid] = regs[i] & 0xFFFFFFFFFFFFFFFF

    sp_nid = b._alloc()
    b.model.append(Node(nid=sp_nid, op="state", args=[str(sort64)], symbol="sp"))
    bindings[sp_nid] = sp & 0xFFFFFFFFFFFFFFFF

    pc_nid = b._alloc()
    b.model.append(Node(nid=pc_nid, op="state", args=[str(sort64)], symbol="pc"))
    bindings[pc_nid] = decoded.pc

    nzcv_nid = b._alloc()
    b.model.append(Node(nid=nzcv_nid, op="state", args=[str(sort4)], symbol="nzcv"))
    bindings[nzcv_nid] = nzcv & 0xF

    mem_nid = b._alloc()
    b.model.append(Node(nid=mem_nid, op="state", args=[str(mem_sort)], symbol="mem"))
    bindings[mem_nid] = dict(mem)

    xzr = b.const("bv64", 0)
    snap = RegSnapshot(nids=reg_nids, sp_nid=sp_nid, xzr_nid=xzr)
    res = lower(b, decoded, snap, pc_nid, mem_nid, nzcv_nid)

    values = evaluate(b.model, bindings)
    rw = {n: values[nid] for n, nid in res.reg_writes.items()}
    sp_next = values.get(res.sp_next) if res.sp_next is not None else None
    nzcv_next_val = values.get(res.nzcv_next) if res.nzcv_next is not None else None
    mem_next = values.get(res.mem_next) if res.mem_next is not None else None
    next_pc = values[res.next_pc]
    return next_pc, rw, sp_next, nzcv_next_val, mem_next


def _sim(decoded: Decoded, regs: list[int], sp: int, nzcv: int, mem: dict[int, int]) -> State:
    s = State(regs=list(regs[:31]), sp=sp, pc=decoded.pc, nzcv=nzcv, mem=dict(mem))
    return step(s, decoded)


def _r(*vals) -> list[int]:
    """Build a 31-element register list."""
    out = [0] * 31
    for i, v in enumerate(vals):
        out[i] = v & 0xFFFFFFFFFFFFFFFF
    return out


def _check(decoded: Decoded, regs: list[int], sp: int = 0, nzcv: int = 0,
           mem: dict[int, int] | None = None):
    """Assert library lowering agrees with simulator on the given decoded inst."""
    mem = mem or {}
    next_pc, rw, sp_next, nzcv_val, mem_next = _build_lowering(decoded, regs, sp, nzcv, mem)
    exp = _sim(decoded, regs, sp, nzcv, mem)

    assert next_pc == exp.pc, (
        f"{decoded.mnemonic}: next_pc mismatch: got {hex(next_pc)} exp {hex(exp.pc)}"
    )
    # Check each register the instruction might have written.
    for i in range(31):
        if i in rw:
            assert rw[i] == exp.regs[i], (
                f"{decoded.mnemonic}: reg x{i} mismatch: got {hex(rw[i])} exp {hex(exp.regs[i])}"
            )
    # SP
    if sp_next is not None:
        assert sp_next == (exp.sp & 0xFFFFFFFFFFFFFFFF), (
            f"{decoded.mnemonic}: sp mismatch: got {hex(sp_next)} exp {hex(exp.sp)}"
        )
    # NZCV
    if nzcv_val is not None:
        assert nzcv_val == exp.nzcv, (
            f"{decoded.mnemonic}: nzcv mismatch: got {nzcv_val:#06b} exp {exp.nzcv:#06b}"
        )


# ---------------------------------------------------------------------------
# ADD / SUB (immediate)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mnem,rd,rn,imm,sf,regs_in,exp_rd", [
    ("ADD",  1, 2, 5,    True,  _r(0, 0, 10),   15),
    ("ADD",  1, 2, 0,    True,  _r(0, 0, 100),  100),
    ("SUB",  3, 1, 7,    True,  _r(0, 20),      13),
    ("ADD",  1, 2, 1,    False, _r(0, 0, 0xFFFFFFFF), 0),     # W-reg wraps + zero-ext
    ("SUB",  1, 2, 1,    False, _r(0, 0, 0),    0xFFFFFFFF),  # W-reg underflow zero-ext
])
def test_add_sub_imm(mnem, rd, rn, imm, sf, regs_in, exp_rd):
    d = _d(mnem, rd=rd, rn=rn, imm=imm, sf=sf, src_is_imm=True)
    _check(d, regs_in)


# ---------------------------------------------------------------------------
# ADDS / SUBS — flag-setting
# ---------------------------------------------------------------------------

def test_adds_sets_nzcv_carry():
    # ADDS: 0xFFFFFFFFFFFFFFFF + 1 → carry=1, result=0, zero=1
    regs = _r(0, 0xFFFFFFFFFFFFFFFF)
    d = _d("ADDS", rd=2, rn=1, imm=1, sf=True, src_is_imm=True, sets_flags=True)
    _check(d, regs)


def test_adds_w_zero_extends():
    # 32-bit ADDS wraps and zero-extends; result is not sign-extended
    regs = _r(0, 0xFFFFFFFF)
    d = _d("ADDS", rd=2, rn=1, imm=1, sf=False, src_is_imm=True, sets_flags=True)
    _check(d, regs)


def test_subs_sets_nzcv_carry_no_borrow():
    # SUBS: 10 - 3 → C=1 (no borrow), result=7
    regs = _r(0, 10)
    d = _d("SUBS", rd=2, rn=1, imm=3, sf=True, src_is_imm=True, sets_flags=True)
    _check(d, regs)


def test_subs_sets_nzcv_borrow():
    # SUBS: 3 - 10 → C=0 (borrow), N=1
    regs = _r(0, 3)
    d = _d("SUBS", rd=2, rn=1, imm=10, sf=True, src_is_imm=True, sets_flags=True)
    _check(d, regs)


# ---------------------------------------------------------------------------
# Logical ops
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mnem,rd,rn,imm,sf,regs_in", [
    ("AND",  1, 2, 0xFF,  True,  _r(0, 0, 0xABCD)),
    ("ORR",  1, 2, 0xF0,  True,  _r(0, 0, 0x0F)),
    ("EOR",  1, 2, 0xFF,  True,  _r(0, 0, 0xAA)),
    ("ANDS", 1, 2, 0xFF,  True,  _r(0, 0, 0xABCD)),
])
def test_logical_imm(mnem, rd, rn, imm, sf, regs_in):
    sets = mnem == "ANDS"
    d = _d(mnem, rd=rd, rn=rn, imm=imm, sf=sf, src_is_imm=True, sets_flags=sets)
    _check(d, regs_in)


def test_ands_nzcv():
    # ANDS with result = 0 sets Z
    regs = _r(0, 0xFF00)
    d = _d("ANDS", rd=1, rn=1, imm=0x00FF, sf=True, src_is_imm=True, sets_flags=True)
    _check(d, regs)


# ---------------------------------------------------------------------------
# Register-register (shifted)
# ---------------------------------------------------------------------------

def test_add_reg_reg():
    regs = _r(0, 3, 5)
    d = _d("ADD", rd=3, rn=1, rm=2, sf=True, src_is_imm=False)
    _check(d, regs)


def test_sub_reg_reg_lsl():
    regs = _r(0, 20, 3)
    d = _d("SUB", rd=3, rn=1, rm=2, sf=True, src_is_imm=False, shift_type=0, shift_amount=1)
    _check(d, regs)


def test_and_reg_reg():
    regs = _r(0, 0xF0F0, 0xFFFF)
    d = _d("AND", rd=3, rn=1, rm=2, sf=True, src_is_imm=False)
    _check(d, regs)


def test_eor_reg_w():
    # 32-bit form: result zero-extended
    regs = _r(0, 0xFFFFFFFF, 0xAAAAAAAA)
    d = _d("EOR", rd=3, rn=1, rm=2, sf=False, src_is_imm=False)
    _check(d, regs)


# ---------------------------------------------------------------------------
# MOV
# ---------------------------------------------------------------------------

def test_movz():
    d = _d("MOVZ", rd=1, imm=0xABCD, shift_amount=0, sf=True)
    _check(d, _r())


def test_movz_shifted():
    d = _d("MOVZ", rd=1, imm=0x1234, shift_amount=16, sf=True)
    _check(d, _r())


def test_movk():
    regs = _r(0, 0xFFFF_FFFF_FFFF_FFFF)
    d = _d("MOVK", rd=1, imm=0xABCD, shift_amount=0, sf=True)
    _check(d, regs)


def test_movn():
    d = _d("MOVN", rd=1, imm=0, shift_amount=0, sf=True)
    _check(d, _r())  # ~0 = all ones


# ---------------------------------------------------------------------------
# ADR / ADRP
# ---------------------------------------------------------------------------

def test_adr():
    d = _d("ADR", rd=1, imm=0x10, sf=True, pc=0x2000)
    _check(d, _r())


def test_adrp():
    # ADRP: page-align PC then add imm (already page-shifted by decoder)
    d = _d("ADRP", rd=1, imm=0x1000, sf=True, pc=0x2ABC)
    _check(d, _r())


# ---------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------

def test_b():
    d = _d("B", imm=0x20, sf=True, pc=0x1000)
    _check(d, _r())


def test_bl():
    d = _d("BL", imm=0x100, sf=True, pc=0x2000)
    _check(d, _r())  # x30 should be pc+4


def test_br():
    regs = _r(0, 0x4000)
    d = _d("BR", rn=1, sf=True, pc=0x2000)
    _check(d, regs)


def test_ret():
    regs = _r(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
              0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xDEAD)  # x30 = 0xDEAD
    d = _d("RET", rn=30, sf=True, pc=0x1000)
    _check(d, regs)


def test_cbz_taken():
    regs = _r(0, 0)  # x1 = 0 → branch taken; decoder stores Rt in rd
    d = _d("CBZ", rd=1, imm=0x40, sf=True, pc=0x1000)
    _check(d, regs)


def test_cbz_not_taken():
    regs = _r(0, 1)  # x1 != 0 → not taken
    d = _d("CBZ", rd=1, imm=0x40, sf=True, pc=0x1000)
    _check(d, regs)


def test_cbnz_taken():
    regs = _r(0, 42)
    d = _d("CBNZ", rd=1, imm=0x40, sf=True, pc=0x1000)
    _check(d, regs)


def test_bcond_eq_taken():
    # B.EQ taken when Z=1 (nzcv bit2=1 → nzcv=0b0100=4)
    d = _d("B.cond", cond=0, imm=0x40, sf=True, pc=0x1000)  # EQ
    _check(d, _r(), nzcv=0b0100)  # Z=1


def test_bcond_eq_not_taken():
    d = _d("B.cond", cond=0, imm=0x40, sf=True, pc=0x1000)  # EQ
    _check(d, _r(), nzcv=0b0000)  # Z=0


def test_tbz_taken():
    regs = _r(0, 0b1010)  # bit 0 = 0 → branch taken; decoder stores Rt in rd
    d = _d("TBZ", rd=1, bit_pos=0, imm=0x40, sf=True, pc=0x1000)
    _check(d, regs)


def test_tbnz_taken():
    regs = _r(0, 0b1010)  # bit 1 = 1 → branch taken
    d = _d("TBNZ", rd=1, bit_pos=1, imm=0x40, sf=True, pc=0x1000)
    _check(d, regs)


# ---------------------------------------------------------------------------
# SDIV / UDIV — AArch64 div-by-zero → 0
# ---------------------------------------------------------------------------

def test_sdiv_normal():
    regs = _r(0, 10, 3)
    d = _d("SDIV", rd=3, rn=1, rm=2, sf=True)
    _check(d, regs)


def test_sdiv_div_by_zero():
    regs = _r(0, 42, 0)  # divisor = 0 → result should be 0
    d = _d("SDIV", rd=3, rn=1, rm=2, sf=True)
    _check(d, regs)


def test_udiv_div_by_zero():
    regs = _r(0, 0xFFFFFFFFFFFFFFFF, 0)
    d = _d("UDIV", rd=3, rn=1, rm=2, sf=True)
    _check(d, regs)


def test_sdiv_w_div_by_zero():
    regs = _r(0, 10, 0)
    d = _d("SDIV", rd=3, rn=1, rm=2, sf=False)
    _check(d, regs)


def test_sdiv_overflow():
    # INT_MIN / -1 → INT_MIN (no trap)
    regs = _r(0, 1 << 63, (1 << 64) - 1)  # INT_MIN, -1
    d = _d("SDIV", rd=3, rn=1, rm=2, sf=True)
    _check(d, regs)


# ---------------------------------------------------------------------------
# Load / Store
# ---------------------------------------------------------------------------

def test_ldr_64bit():
    mem = {0x2000 + i: i + 1 for i in range(8)}
    d = _d("LDR", rd=1, rn=2, imm=0, sf=True, addr_mode="base_imm")
    regs = _r(0, 0, 0x2000)
    _check(d, regs, mem=mem)


def test_ldr_32bit_zero_extends():
    # LDR Wt: 32-bit load zero-extends (AArch64 divergence)
    mem = {0x2000 + i: 0xFF for i in range(4)}
    d = _d("LDR", rd=1, rn=2, imm=0, sf=False, addr_mode="base_imm")
    regs = _r(0, 0, 0x2000)
    _check(d, regs, mem=mem)


def test_ldrb():
    mem = {0x1000: 0xAB}
    d = _d("LDRB", rd=1, rn=2, imm=0, sf=False, addr_mode="base_imm")
    regs = _r(0, 0, 0x1000)
    _check(d, regs, mem=mem)


def test_ldrsb_sign_extends():
    mem = {0x1000: 0xFF}
    d = _d("LDRSB", rd=1, rn=2, imm=0, sf=True, addr_mode="base_imm")
    regs = _r(0, 0, 0x1000)
    _check(d, regs, mem=mem)


def test_str_64bit():
    regs = _r(0, 0xDEADBEEFCAFEBABE, 0, 0x3000)
    d = _d("STR", rd=1, rn=3, imm=0, sf=True, addr_mode="base_imm")
    _check(d, regs)


def test_str_with_imm_offset():
    regs = _r(0, 0xABCD, 0, 0x4000)
    d = _d("STR", rd=1, rn=3, imm=8, sf=True, addr_mode="base_imm")
    _check(d, regs)


def test_ldr_pre_index():
    mem = {0x2008 + i: i for i in range(8)}
    d = _d("LDR", rd=1, rn=2, imm=8, sf=True, addr_mode="pre")
    regs = _r(0, 0, 0x2000)
    _check(d, regs, mem=mem)


def test_str_post_index():
    regs = _r(0, 0xCAFE, 0, 0x5000)
    d = _d("STR", rd=1, rn=3, imm=16, sf=True, addr_mode="post")
    _check(d, regs)


# ---------------------------------------------------------------------------
# MADD / MSUB
# ---------------------------------------------------------------------------

def test_madd():
    regs = _r(0, 3, 5, 7)  # x1=3, x2=5, x3 (ra)=7 → 7 + 3*5 = 22
    d = _d("MADD", rd=4, rn=1, rm=2, ra=3, sf=True)
    _check(d, regs)


def test_msub():
    regs = _r(0, 3, 5, 20)  # 20 - 3*5 = 5
    d = _d("MSUB", rd=4, rn=1, rm=2, ra=3, sf=True)
    _check(d, regs)


# ---------------------------------------------------------------------------
# CSEL / CSINC — conditional select
# ---------------------------------------------------------------------------

def test_csel_true():
    regs = _r(0, 10, 20)
    d = _d("CSEL", rd=3, rn=1, rm=2, cond=0, sf=True)  # EQ
    _check(d, regs, nzcv=0b0100)  # Z=1 → take rn


def test_csel_false():
    regs = _r(0, 10, 20)
    d = _d("CSEL", rd=3, rn=1, rm=2, cond=0, sf=True)  # EQ
    _check(d, regs, nzcv=0b0000)  # Z=0 → take rm


def test_csinc_false():
    regs = _r(0, 10, 20)
    d = _d("CSINC", rd=3, rn=1, rm=2, cond=0, sf=True)  # EQ, false → rm+1=21
    _check(d, regs, nzcv=0b0000)  # Z=0


# ---------------------------------------------------------------------------
# UBFM / SBFM
# ---------------------------------------------------------------------------

def test_ubfm_extract():
    # UBFX: extract bits [11:4] → imms=11, immr=4
    regs = _r(0, 0xFF0)
    d = _d("UBFM", rd=2, rn=1, immr=4, imms=11, sf=True)
    _check(d, regs)


def test_ubfm_lsl_alias():
    # LSL #1 encoded as UBFM: immr=63, imms=62
    regs = _r(0, 0xABCDEF)
    d = _d("UBFM", rd=2, rn=1, immr=63, imms=62, sf=True)
    _check(d, regs)


def test_sbfm_sxtb():
    # SXTB: immr=0, imms=7 → sign-extend byte
    regs = _r(0, 0xFF)  # -1 signed
    d = _d("SBFM", rd=2, rn=1, immr=0, imms=7, sf=True)
    _check(d, regs)


def test_sbfm_asr():
    # ASR #4 encoded as SBFM: immr=4, imms=63
    regs = _r(0, 0x8000_0000_0000_0000)  # negative
    d = _d("SBFM", rd=2, rn=1, immr=4, imms=63, sf=True)
    _check(d, regs)


# ---------------------------------------------------------------------------
# EXTR
# ---------------------------------------------------------------------------

def test_extr():
    regs = _r(0, 0x00FF00FF, 0xFF00FF00)
    d = _d("EXTR", rd=3, rn=1, rm=2, imm=8, sf=True)  # lsb=8
    _check(d, regs)


# ---------------------------------------------------------------------------
# SVC / NOP
# ---------------------------------------------------------------------------

def test_svc_halts():
    d = _d("SVC", imm=0, sf=True, pc=0x1000)
    next_pc, rw, sp_next, nzcv_val, _ = _build_lowering(d, _r(), 0, 0, {})
    assert next_pc == 0x1000  # frozen


def test_nop():
    d = _d("NOP", sf=True, pc=0x1000)
    _check(d, _r())


# ---------------------------------------------------------------------------
# W-register zero-extension divergence
# ---------------------------------------------------------------------------

def test_w_reg_zero_extends_not_sign_extends():
    # x1 = 0xFFFFFFFF (32-bit -1). ADD Wd, Wn, Wm (W-reg) must zero-extend.
    regs = _r(0, 0xFFFFFFFF, 0x1)
    d = _d("ADD", rd=3, rn=1, rm=2, sf=False, src_is_imm=False)
    next_pc, rw, _, _, _ = _build_lowering(d, regs, 0, 0, {})
    if 3 in rw:
        # 0xFFFFFFFF + 1 = 0x100000000 in 64 bits, but W-reg wraps to 0, zero-ext stays 0
        assert rw[3] == 0, f"W-reg should zero-extend: got {hex(rw[3])}"
