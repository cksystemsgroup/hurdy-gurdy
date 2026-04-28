from gurdy.pairs.riscv_btor2.lift.simulator import State, fetch_from_memory_map, simulate, step
from gurdy.pairs.riscv_btor2.source.decoder import Decoded


def _d(mnem, **kw):
    base = dict(pc=0, length=4, raw=0, rd=0, rs1=0, rs2=0, imm=0)
    base.update(kw)
    return Decoded(mnemonic=mnem, **base)


def test_addi_basic():
    s = State()
    s = step(s, _d("ADDI", rd=1, rs1=0, imm=5))
    assert s.regs[1] == 5
    assert s.pc == 4


def test_addi_negative_immediate_two_complement():
    s = State()
    s = step(s, _d("ADDI", rd=1, rs1=0, imm=-1))
    assert s.regs[1] == 0xFFFFFFFFFFFFFFFF


def test_x0_writes_dropped():
    s = State()
    s = step(s, _d("ADDI", rd=0, rs1=0, imm=42))
    assert s.regs[0] == 0


def test_branch_taken_and_not_taken():
    s = State(regs=[0, 5, 5] + [0] * 29)
    taken = step(s, _d("BEQ", rs1=1, rs2=2, imm=16))
    assert taken.pc == 16
    s2 = State(regs=[0, 5, 6] + [0] * 29)
    not_taken = step(s2, _d("BEQ", rs1=1, rs2=2, imm=16))
    assert not_taken.pc == 4


def test_jalr_clears_low_bit():
    s = State(regs=[0, 0, 0x1003] + [0] * 29)
    s = step(s, _d("JALR", rd=1, rs1=2, imm=0))
    assert s.pc == 0x1002
    assert s.regs[1] == 4  # link


def test_load_store_round_trip():
    # SD then LD.
    s = State(regs=[0, 0, 0x1000, 0xDEADBEEFCAFEBABE] + [0] * 28)
    s = step(s, _d("SD", rs1=2, rs2=3, imm=0))
    s2 = step(s, _d("LD", rd=4, rs1=2, imm=0))
    assert s2.regs[4] == 0xDEADBEEFCAFEBABE


def test_lb_sign_extend():
    s = State(regs=[0, 0, 0x1000] + [0] * 29, mem={0x1000: 0xFF})
    s = step(s, _d("LB", rd=1, rs1=2, imm=0))
    assert s.regs[1] == 0xFFFFFFFFFFFFFFFF


def test_lbu_zero_extend():
    s = State(regs=[0, 0, 0x1000] + [0] * 29, mem={0x1000: 0xFF})
    s = step(s, _d("LBU", rd=1, rs1=2, imm=0))
    assert s.regs[1] == 0xFF


def test_div_by_zero_returns_minus1():
    s = State(regs=[0, 5, 0] + [0] * 29)
    s = step(s, _d("DIV", rd=3, rs1=1, rs2=2))
    assert s.regs[3] == 0xFFFFFFFFFFFFFFFF


def test_signed_overflow_div():
    s = State(regs=[0, 1 << 63, 0xFFFFFFFFFFFFFFFF] + [0] * 29)
    s = step(s, _d("DIV", rd=3, rs1=1, rs2=2))
    assert s.regs[3] == 1 << 63


def test_remu_returns_dividend_when_divisor_zero():
    s = State(regs=[0, 7, 0] + [0] * 29)
    s = step(s, _d("REMU", rd=3, rs1=1, rs2=2))
    assert s.regs[3] == 7


def test_simulate_runs_two_instructions_then_halts_on_ecall():
    # 0: addi a0, x0, 1
    # 4: addi a0, a0, 1
    # 8: ecall
    bytemap = {}
    for pc, word in [(0, 0x00100513), (4, 0x00150513), (8, 0x00000073)]:
        for i in range(4):
            bytemap[pc + i] = (word >> (8 * i)) & 0xFF
    fetch = fetch_from_memory_map(bytemap)
    s, trace = simulate(State(), fetch)
    assert s.halted
    assert s.regs[10] == 2
    assert [d.mnemonic for d in trace] == ["ADDI", "ADDI", "ECALL"]
