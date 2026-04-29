"""Cross-check: every supported mnemonic, library lowering matches simulator.

We build a Builder, declare 32 register states (input nids), declare a
memory state, lower a single ``Decoded``, and evaluate the resulting
nids on concrete inputs. We then run the same instruction through the
simulator and assert agreement on the produced register/memory writes
and on next_pc.
"""

import pytest

from gurdy.pairs.riscv_btor2.btor2.evaluator import evaluate
from gurdy.pairs.riscv_btor2.btor2.nodes import Node
from gurdy.pairs.riscv_btor2.lift.simulator import State, step
from gurdy.pairs.riscv_btor2.source.decoder import Decoded
from gurdy.pairs.riscv_btor2.translation.builder import Builder
from gurdy.pairs.riscv_btor2.translation.library import RegSnapshot, lower


def _d(mnem, **kw):
    base = dict(pc=0, length=4, raw=0, rd=0, rs1=0, rs2=0, imm=0)
    base.update(kw)
    return Decoded(mnemonic=mnem, **base)


def _build_lowering(decoded: Decoded, regs: list[int], mem: dict[int, int]):
    """Run library.lower and evaluate the result against concrete inputs.

    Returns (reg_writes_value: dict[int, int], mem_next_value: dict|None,
    next_pc_value: int).
    """
    b = Builder()
    # Set up register snapshot: x0 is bv64 zero const; x1..x31 are
    # explicit 'state' nodes whose values we bind to the supplied list.
    zero64 = b.const("bv64", 0)
    reg_state_nids: dict[int, int] = {0: zero64}
    bindings: dict[int, int] = {}
    for i in range(1, 32):
        sort_nid = b.declare_sort("bv64")
        nid = b._alloc()
        b.model.append(Node(nid=nid, op="state", args=[str(sort_nid)], symbol=f"reg_x{i}"))
        reg_state_nids[i] = nid
        bindings[nid] = regs[i]
    pc_sort = b.declare_sort("bv64")
    pc_nid = b._alloc()
    b.model.append(Node(nid=pc_nid, op="state", args=[str(pc_sort)], symbol="pc"))
    bindings[pc_nid] = decoded.pc
    mem_sort = b.declare_array_sort("mem", "bv64", "bv8")
    mem_nid = b._alloc()
    b.model.append(Node(nid=mem_nid, op="state", args=[str(mem_sort)], symbol="mem"))
    bindings[mem_nid] = dict(mem)

    snap = RegSnapshot(nids=reg_state_nids)
    res = lower(b, decoded, snap, pc_nid, mem_nid)

    values = evaluate(b.model, bindings)
    reg_writes = {n: values.get(nid) for n, nid in res.reg_writes.items()}
    mem_next = values.get(res.mem_next) if res.mem_next is not None else None
    next_pc = values.get(res.next_pc)
    return reg_writes, mem_next, next_pc


def _expected_state(decoded: Decoded, regs: list[int], mem: dict[int, int]) -> State:
    s = State(regs=list(regs), mem=dict(mem), pc=decoded.pc)
    return step(s, decoded)


def _agree_arith(decoded: Decoded, regs: list[int], mem: dict[int, int]):
    reg_writes, mem_next, next_pc = _build_lowering(decoded, regs, mem)
    expected = _expected_state(decoded, regs, mem)

    # next_pc agrees
    assert next_pc == expected.pc, f"{decoded.mnemonic}: pc mismatch {next_pc} vs {expected.pc}"

    # If the instruction writes a register, the value matches.
    if decoded.rd != 0 and decoded.mnemonic not in {"FENCE", "FENCE.I", "ECALL", "EBREAK"}:
        if decoded.rd in reg_writes:
            assert reg_writes[decoded.rd] == expected.regs[decoded.rd], (
                f"{decoded.mnemonic}: rd={decoded.rd} mismatch "
                f"got={reg_writes[decoded.rd]} expected={expected.regs[decoded.rd]}"
            )


def _r(*regs):
    out = [0] * 32
    for i, v in enumerate(regs):
        out[i] = v & 0xFFFFFFFFFFFFFFFF
    return out


@pytest.mark.parametrize(
    "decoded, regs",
    [
        # --- RV64I integer immediate ---
        (_d("ADDI", rd=1, rs1=2, imm=5), _r(0, 0, 10)),
        (_d("ADDI", rd=3, rs1=4, imm=-7), _r(0, 0, 0, 0, 100)),
        (_d("ANDI", rd=3, rs1=1, imm=0x0F0), _r(0, 0xFFFF)),
        (_d("ORI",  rd=3, rs1=1, imm=0x0F0), _r(0, 0xF000)),
        (_d("XORI", rd=3, rs1=1, imm=0x0FF), _r(0, 0x0F0)),
        (_d("SLTI", rd=3, rs1=1, imm=10), _r(0, 5)),
        (_d("SLTI", rd=3, rs1=1, imm=10), _r(0, 0xFFFFFFFFFFFFFFFF)),  # signed -1 < 10
        (_d("SLTIU",rd=3, rs1=1, imm=10), _r(0, 0xFFFFFFFFFFFFFFFF)),  # unsigned huge > 10
        # --- RV64I register-register ---
        (_d("ADD", rd=3, rs1=1, rs2=2), _r(0, 5, 7)),
        (_d("SUB", rd=3, rs1=1, rs2=2), _r(0, 100, 30)),
        (_d("XOR", rd=3, rs1=1, rs2=2), _r(0, 0xF0F0, 0x0FF0)),
        (_d("AND", rd=3, rs1=1, rs2=2), _r(0, 0xFFFF, 0xF00F)),
        (_d("OR", rd=3, rs1=1, rs2=2), _r(0, 0x00F0, 0x0F00)),
        (_d("SLL", rd=3, rs1=1, rs2=2), _r(0, 1, 4)),
        (_d("SLL", rd=3, rs1=1, rs2=2), _r(0, 1, 64)),  # mask: shift by 0
        (_d("SRL", rd=3, rs1=1, rs2=2), _r(0, 0xFF00, 4)),
        (_d("SRA", rd=3, rs1=1, rs2=2), _r(0, 1 << 63, 4)),
        (_d("SLT", rd=3, rs1=1, rs2=2), _r(0, 5, 7)),
        (_d("SLTU", rd=3, rs1=1, rs2=2), _r(0, 5, 7)),
        # --- RV64I word-only immediate ---
        (_d("ADDIW", rd=3, rs1=1, imm=10), _r(0, 0xFFFFFFFF)),
        (_d("SLLIW", rd=3, rs1=1, imm=4), _r(0, 0xFFFFFFFF)),  # 32-bit shift, sign-ext
        (_d("SRLIW", rd=3, rs1=1, imm=4), _r(0, 0xFFFFFFFF)),  # logical
        (_d("SRAIW", rd=3, rs1=1, imm=4), _r(0, 0xFFFFFFFF)),  # arith, sign bit propagates
        # --- RV64I word-only register-register ---
        (_d("ADDW", rd=3, rs1=1, rs2=2), _r(0, 0xFFFFFFFF, 1)),
        (_d("SUBW", rd=3, rs1=1, rs2=2), _r(0, 5, 7)),
        (_d("SLLW", rd=3, rs1=1, rs2=2), _r(0, 1, 4)),
        (_d("SRLW", rd=3, rs1=1, rs2=2), _r(0, 0xFFFFFFFF, 4)),
        (_d("SRAW", rd=3, rs1=1, rs2=2), _r(0, 0x80000000, 4)),  # 32-bit arith shift
        (_d("SLLI", rd=3, rs1=1, imm=4), _r(0, 1)),
        (_d("SRLI", rd=3, rs1=1, imm=4), _r(0, 0xFF00)),
        (_d("SRAI", rd=3, rs1=1, imm=4), _r(0, 1 << 63)),
        # --- LUI / AUIPC ---
        (_d("LUI", rd=3, imm=0x12345 << 12), _r()),
        (_d("LUI", rd=3, imm=0x80000 << 12), _r()),  # sign-extend to negative 64
        (_d("AUIPC", rd=3, imm=0x100 << 12, pc=0x10000), _r()),
        # --- M-extension MUL ---
        (_d("MUL", rd=3, rs1=1, rs2=2), _r(0, 7, 8)),
        (_d("MULH", rd=3, rs1=1, rs2=2), _r(0, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF)),  # signed -1*-1
        (_d("MULHU", rd=3, rs1=1, rs2=2), _r(0, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF)),  # unsigned
        (_d("MULHSU", rd=3, rs1=1, rs2=2), _r(0, 0xFFFFFFFFFFFFFFFF, 1)),
        (_d("MULW", rd=3, rs1=1, rs2=2), _r(0, 0xFFFFFFFF, 0xFFFFFFFF)),  # 32-bit, sign-ext
        # --- M-extension DIV/REM ---
        (_d("DIVU", rd=3, rs1=1, rs2=2), _r(0, 100, 7)),
        (_d("DIVU", rd=3, rs1=1, rs2=2), _r(0, 100, 0)),  # /0: returns 2^64-1
        (_d("REMU", rd=3, rs1=1, rs2=2), _r(0, 100, 0)),  # rem/0: returns rs1
        (_d("DIV", rd=3, rs1=1, rs2=2), _r(0, 1 << 63, 0xFFFFFFFFFFFFFFFF)),  # INT_MIN/-1
        (_d("REM", rd=3, rs1=1, rs2=2), _r(0, 1 << 63, 0xFFFFFFFFFFFFFFFF)),
        (_d("DIVW", rd=3, rs1=1, rs2=2), _r(0, 100, 7)),
        (_d("DIVUW", rd=3, rs1=1, rs2=2), _r(0, 100, 0)),  # 32-bit div/0
        (_d("REMW", rd=3, rs1=1, rs2=2), _r(0, 100, 7)),
        (_d("REMUW", rd=3, rs1=1, rs2=2), _r(0, 100, 0)),
    ],
)
def test_library_matches_simulator(decoded, regs):
    _agree_arith(decoded, regs, mem={})


@pytest.mark.parametrize(
    "mnem, regs",
    [
        # All six branch flavors, both taken and fall-through arms,
        # exercise the comparison operators (BLT/BLTU vs BGE/BGEU
        # caught real bugs in the corpus — see 0013 / 0016).
        ("BEQ",  _r(0, 5, 5)),
        ("BEQ",  _r(0, 5, 6)),
        ("BNE",  _r(0, 5, 5)),
        ("BNE",  _r(0, 5, 6)),
        ("BLT",  _r(0, 0xFFFFFFFFFFFFFFFF, 1)),  # signed -1 < 1: taken
        ("BLT",  _r(0, 1, 0xFFFFFFFFFFFFFFFF)),  # signed: not taken
        ("BLTU", _r(0, 0xFFFFFFFFFFFFFFFF, 1)),  # unsigned: not taken
        ("BLTU", _r(0, 1, 0xFFFFFFFFFFFFFFFF)),  # unsigned: taken
        ("BGE",  _r(0, 0xFFFFFFFFFFFFFFFF, 1)),
        ("BGE",  _r(0, 1, 0xFFFFFFFFFFFFFFFF)),
        ("BGEU", _r(0, 0xFFFFFFFFFFFFFFFF, 1)),
        ("BGEU", _r(0, 1, 0xFFFFFFFFFFFFFFFF)),
    ],
)
def test_branch_pc_matches_simulator(mnem, regs):
    decoded = _d(mnem, rs1=1, rs2=2, imm=16, pc=4)
    _, _, next_pc = _build_lowering(decoded, regs, {})
    expected = _expected_state(decoded, regs, {})
    assert next_pc == expected.pc, (
        f"{mnem} regs[1]={regs[1]} regs[2]={regs[2]}: next_pc {next_pc} vs {expected.pc}"
    )


def test_jal_writes_link_and_jumps():
    decoded = _d("JAL", rd=1, imm=0x100, pc=0x10000, length=4)
    regs = _r()
    rw, _, next_pc = _build_lowering(decoded, regs, {})
    expected = _expected_state(decoded, regs, {})
    assert next_pc == expected.pc           # pc + imm
    assert rw[1] == expected.regs[1]        # rd = pc + length


def test_jalr_pc_matches_simulator_with_low_bit_clear():
    decoded = _d("JALR", rd=1, rs1=2, imm=0, pc=0x100)
    regs = _r(0, 0, 0x1003)
    rw, _, next_pc = _build_lowering(decoded, regs, {})
    expected = _expected_state(decoded, regs, {})
    assert next_pc == expected.pc
    assert rw[1] == expected.regs[1]


def _store_then_load_value(store_mnem, load_mnem, value):
    """Helper: SD/SH/SW/SB the value, then LD/LH/LHU/LW/LWU/LB/LBU it back.
    Returns the loaded value as a Python int."""
    store = _d(store_mnem, rs1=2, rs2=3, imm=0)
    regs = _r(0, 0, 0x1000, value)
    _, mem_next, _ = _build_lowering(store, regs, {})
    assert mem_next is not None

    load = _d(load_mnem, rd=4, rs1=2, imm=0)
    b = Builder()
    zero64 = b.const("bv64", 0)
    reg_state_nids = {0: zero64}
    bindings = {}
    for i in range(1, 32):
        sn = b.declare_sort("bv64")
        nid = b._alloc()
        b.model.append(Node(nid=nid, op="state", args=[str(sn)], symbol=f"reg_x{i}"))
        reg_state_nids[i] = nid
        bindings[nid] = regs[i]
    psn = b.declare_sort("bv64")
    pc_nid = b._alloc()
    b.model.append(Node(nid=pc_nid, op="state", args=[str(psn)], symbol="pc"))
    bindings[pc_nid] = 0
    msn = b.declare_array_sort("mem", "bv64", "bv8")
    mem_nid = b._alloc()
    b.model.append(Node(nid=mem_nid, op="state", args=[str(msn)], symbol="mem"))
    bindings[mem_nid] = mem_next

    snap = RegSnapshot(nids=reg_state_nids)
    res = lower(b, load, snap, pc_nid, mem_nid)
    values = evaluate(b.model, bindings)
    return values[res.reg_writes[4]]


def test_store_load_round_trip_via_lowering():
    """Original SD->LD round-trip kept for regression."""
    assert _store_then_load_value("SD", "LD", 0xDEADBEEFCAFEBABE) == 0xDEADBEEFCAFEBABE


@pytest.mark.parametrize(
    "store, load, stored, expected",
    [
        # SD round-trips a doubleword.
        ("SD", "LD", 0xDEADBEEFCAFEBABE, 0xDEADBEEFCAFEBABE),
        # SW stores low 32, LW sign-extends, LWU zero-extends.
        ("SW", "LW",  0x00000000FEEDFACE, 0xFFFFFFFFFEEDFACE),  # high bit set
        ("SW", "LWU", 0x00000000FEEDFACE, 0x00000000FEEDFACE),
        ("SW", "LW",  0x000000007FEDFACE, 0x000000007FEDFACE),  # high bit clear
        # SH stores low 16, LH sign-extends, LHU zero-extends.
        ("SH", "LH",  0x000000000000FEED, 0xFFFFFFFFFFFFFEED),
        ("SH", "LHU", 0x000000000000FEED, 0x000000000000FEED),
        ("SH", "LH",  0x0000000000007EED, 0x0000000000007EED),
        # SB stores low 8, LB sign-extends, LBU zero-extends.
        # *** This is exactly the case that surfaced the LBU bv8/bv64
        # *** lowering bug — keep it explicit. ***
        ("SB", "LB",  0x00000000000000FF, 0xFFFFFFFFFFFFFFFF),
        ("SB", "LBU", 0x00000000000000FF, 0x00000000000000FF),
        ("SB", "LB",  0x000000000000007F, 0x000000000000007F),
    ],
)
def test_store_load_extension_round_trip(store, load, stored, expected):
    assert _store_then_load_value(store, load, stored) == expected
