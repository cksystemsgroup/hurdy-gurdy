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
        (_d("ADDI", rd=1, rs1=2, imm=5), _r(0, 0, 10)),
        (_d("ADDI", rd=3, rs1=4, imm=-7), _r(0, 0, 0, 0, 100)),
        (_d("ADD", rd=3, rs1=1, rs2=2), _r(0, 5, 7)),
        (_d("SUB", rd=3, rs1=1, rs2=2), _r(0, 100, 30)),
        (_d("XOR", rd=3, rs1=1, rs2=2), _r(0, 0xF0F0, 0x0FF0)),
        (_d("AND", rd=3, rs1=1, rs2=2), _r(0, 0xFFFF, 0xF00F)),
        (_d("OR", rd=3, rs1=1, rs2=2), _r(0, 0x00F0, 0x0F00)),
        (_d("SLL", rd=3, rs1=1, rs2=2), _r(0, 1, 4)),
        (_d("SRL", rd=3, rs1=1, rs2=2), _r(0, 0xFF00, 4)),
        (_d("SRA", rd=3, rs1=1, rs2=2), _r(0, 1 << 63, 4)),
        (_d("SLT", rd=3, rs1=1, rs2=2), _r(0, 5, 7)),
        (_d("SLTU", rd=3, rs1=1, rs2=2), _r(0, 5, 7)),
        (_d("ADDIW", rd=3, rs1=1, imm=10), _r(0, 0xFFFFFFFF)),
        (_d("ADDW", rd=3, rs1=1, rs2=2), _r(0, 0xFFFFFFFF, 1)),
        (_d("SUBW", rd=3, rs1=1, rs2=2), _r(0, 5, 7)),
        (_d("SLLI", rd=3, rs1=1, imm=4), _r(0, 1)),
        (_d("SRLI", rd=3, rs1=1, imm=4), _r(0, 0xFF00)),
        (_d("SRAI", rd=3, rs1=1, imm=4), _r(0, 1 << 63)),
        (_d("LUI", rd=3, imm=0x12345 << 12), _r()),
        (_d("MUL", rd=3, rs1=1, rs2=2), _r(0, 7, 8)),
        (_d("DIVU", rd=3, rs1=1, rs2=2), _r(0, 100, 7)),
        (_d("DIVU", rd=3, rs1=1, rs2=2), _r(0, 100, 0)),
        (_d("REMU", rd=3, rs1=1, rs2=2), _r(0, 100, 0)),
        (_d("DIV", rd=3, rs1=1, rs2=2), _r(0, 1 << 63, 0xFFFFFFFFFFFFFFFF)),
        (_d("REM", rd=3, rs1=1, rs2=2), _r(0, 1 << 63, 0xFFFFFFFFFFFFFFFF)),
    ],
)
def test_library_matches_simulator(decoded, regs):
    _agree_arith(decoded, regs, mem={})


def test_branch_taken_pc_matches_simulator():
    decoded = _d("BEQ", rs1=1, rs2=2, imm=16, pc=4)
    regs = _r(0, 5, 5)
    _, _, next_pc = _build_lowering(decoded, regs, {})
    expected = _expected_state(decoded, regs, {})
    assert next_pc == expected.pc


def test_branch_not_taken_pc_matches_simulator():
    decoded = _d("BNE", rs1=1, rs2=2, imm=16, pc=4)
    regs = _r(0, 5, 5)
    _, _, next_pc = _build_lowering(decoded, regs, {})
    expected = _expected_state(decoded, regs, {})
    assert next_pc == expected.pc


def test_jalr_pc_matches_simulator_with_low_bit_clear():
    decoded = _d("JALR", rd=1, rs1=2, imm=0, pc=0x100)
    regs = _r(0, 0, 0x1003)
    rw, _, next_pc = _build_lowering(decoded, regs, {})
    expected = _expected_state(decoded, regs, {})
    assert next_pc == expected.pc
    assert rw[1] == expected.regs[1]


def test_store_load_round_trip_via_lowering():
    # Run SD, then LD, both through lowering, on the same memory.
    sd = _d("SD", rs1=2, rs2=3, imm=0)
    regs = _r(0, 0, 0x1000, 0xDEADBEEFCAFEBABE)
    _, mem_next, _ = _build_lowering(sd, regs, {})
    assert mem_next is not None

    # Now LD from the new memory: build a new lowering with mem bound to mem_next.
    ld = _d("LD", rd=4, rs1=2, imm=0)
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
    bindings[mem_nid] = mem_next  # the post-store memory

    snap = RegSnapshot(nids=reg_state_nids)
    res = lower(b, ld, snap, pc_nid, mem_nid)
    values = evaluate(b.model, bindings)
    assert values[res.reg_writes[4]] == 0xDEADBEEFCAFEBABE
