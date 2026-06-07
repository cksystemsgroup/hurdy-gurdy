"""Hand-traced bytecode tests for the P2 concrete EVM executor.

Each test contains an explicit byte-by-byte trace of the execution, the
expected terminal state, and the expected gas consumption.  These serve
as the ground-truth oracle for the BTOR2 translator.

Gas model: SCHEMA.md §10.  Stack: SCHEMA.md §6.  Memory: §7.  Storage: §8.
"""

import pytest

from gurdy.pairs.evm_btor2.source_interp import (
    EvmContext,
    MachineState,
    StepRecord,
    compute_jumpdest_table,
    disassemble,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(hex_bytecode: str, *, gas: int = 100_000, **ctx_kwargs) -> MachineState:
    bytecode = bytes.fromhex(hex_bytecode)
    ctx = EvmContext(**ctx_kwargs) if ctx_kwargs else None
    state, _ = run(bytecode, ctx, initial_gas=gas)
    return state


def _run_shadow(hex_bytecode: str, *, gas: int = 100_000, **ctx_kwargs):
    bytecode = bytes.fromhex(hex_bytecode)
    ctx = EvmContext(**ctx_kwargs) if ctx_kwargs else None
    return run(bytecode, ctx, initial_gas=gas, shadow=True)


# ---------------------------------------------------------------------------
# Seq 1: Simple ADD — arithmetic
#
# Bytecode (hex):  60 03 60 04 01 00
#
# Trace (gas_start=100):
#   PC=0  PUSH1 0x03 → stack=[3],      gas=100-3=97
#   PC=2  PUSH1 0x04 → stack=[3,4],    gas=97-3=94
#   PC=4  ADD        → stack=[7],       gas=94-3=91
#   PC=5  STOP       → halted, trap=F
# ---------------------------------------------------------------------------


def test_seq1_add():
    state = _run("60036004 0100", gas=100)
    assert state.stack == [7]
    assert state.halted is True
    assert state.trap is False
    assert state.gas == 91  # 100 - 3 - 3 - 3


# ---------------------------------------------------------------------------
# Seq 2: MUL + SUB — multiple arithmetic ops
#
# Bytecode (hex):  60 01 60 06 60 07 02 03 00
#
# Trace (gas_start=100):
#   PC=0  PUSH1 0x01 → stack=[1],         gas=100-3=97
#   PC=2  PUSH1 0x06 → stack=[1,6],       gas=97-3=94
#   PC=4  PUSH1 0x07 → stack=[1,6,7],     gas=94-3=91
#   PC=6  MUL        → pop 7,6 → 42,      stack=[1,42],  gas=91-5=86
#   PC=7  SUB        → pop 42,1 → 42-1,   stack=[41],    gas=86-3=83
#   PC=8  STOP       → halted, trap=F
# ---------------------------------------------------------------------------


def test_seq2_mul_sub():
    state = _run("6001 6006 6007 02 03 00", gas=100)
    assert state.stack == [41]
    assert state.halted is True
    assert state.trap is False
    assert state.gas == 83  # 100 - 3 - 3 - 3 - 5 - 3


# ---------------------------------------------------------------------------
# Seq 3: JUMP + JUMPDEST — control flow skips dead code
#
# Bytecode (hex):  60 06 56 fe 60 ff 5b 60 2a 00
#   PC=0  0x60 PUSH1
#   PC=1  0x06 (imm → push 6)
#   PC=2  0x56 JUMP
#   PC=3  0xfe INVALID   ← dead code (jumped over)
#   PC=4  0x60 PUSH1     ← dead code
#   PC=5  0xff (imm)     ← inside PUSH1 at PC=4
#   PC=6  0x5b JUMPDEST  ← valid landing pad
#   PC=7  0x60 PUSH1
#   PC=8  0x2a (imm → push 42)
#   PC=9  0x00 STOP
#
# Trace (gas_start=100):
#   PUSH1 6    → stack=[6],   gas=97
#   JUMP  → dest=6, valid   gas=97-8=89
#   JUMPDEST   → pc=7,        gas=89-1=88
#   PUSH1 0x2a → stack=[42], gas=88-3=85
#   STOP       → halted, trap=F
# ---------------------------------------------------------------------------


def test_seq3_jump():
    bytecode = bytes.fromhex("60065 6fe60ff5b602a00".replace(" ", ""))
    # Unambiguous hex string:
    bytecode = bytes([0x60, 0x06, 0x56, 0xFE, 0x60, 0xFF, 0x5B, 0x60, 0x2A, 0x00])
    state, _ = run(bytecode, initial_gas=100)
    assert state.stack == [42]
    assert state.halted is True
    assert state.trap is False
    assert state.gas == 85  # 100 - 3 - 8 - 1 - 3


def test_seq3_jumpdest_table():
    """JUMPDEST at PC=6 must be valid; byte 0x5b inside PUSH1 immediate must not."""
    #  PC=0: PUSH1, PC=1: 0x5b (imm), PC=2: JUMPDEST, PC=3: STOP
    bytecode = bytes([0x60, 0x5B, 0x5B, 0x00])
    table = compute_jumpdest_table(bytecode)
    assert 1 not in table, "0x5b inside PUSH1 immediate must not be a JUMPDEST"
    assert 2 in table


# ---------------------------------------------------------------------------
# Seq 4: SSTORE + SLOAD — storage read/write + EIP-2929 gas
#
# Bytecode (hex):  60 42 60 00 55 60 00 54 00
#   PC=0  PUSH1 0x42 → stack=[0x42]
#   PC=2  PUSH1 0x00 → stack=[0x42, 0x00]  (0x00=TOS=slot)
#   PC=4  SSTORE     → slot=TOS=0, val=2nd=0x42; cold+orig==0+new≠orig → 20000
#   PC=5  PUSH1 0x00 → stack=[0x00]
#   PC=7  SLOAD      → slot=0, warm→100; val=0x42 → stack=[0x42]
#   PC=8  STOP
#
# Gas trace (gas_start=100_000):
#   PUSH1: 3, PUSH1: 3, SSTORE cold-set: 20000, PUSH1: 3, SLOAD warm: 100
#   Total used: 20109; remaining: 79891
# ---------------------------------------------------------------------------


def test_seq4_sstore_sload():
    bytecode = bytes([0x60, 0x42, 0x60, 0x00, 0x55, 0x60, 0x00, 0x54, 0x00])
    state, _ = run(bytecode, initial_gas=100_000)
    assert state.stack == [0x42]
    assert state.halted is True
    assert state.trap is False
    assert state.sto.get(0) == 0x42
    assert state.gas == 79_891  # 100_000 - 3 - 3 - 20_000 - 3 - 100


def test_seq4_sstore_warm_cheaper():
    """Second SSTORE to the same slot is cheaper (warm, value changed)."""
    # PUSH1 1, PUSH1 0, SSTORE, PUSH1 2, PUSH1 0, SSTORE, STOP
    bytecode = bytes([
        0x60, 0x01, 0x60, 0x00, 0x55,  # sto[0] = 1  (cold, original=0 → 20000)
        0x60, 0x02, 0x60, 0x00, 0x55,  # sto[0] = 2  (warm, new≠current, current≠original → 100)
        0x00,
    ])
    state, _ = run(bytecode, initial_gas=100_000)
    assert state.sto.get(0) == 2
    # Gas: 3+3+20000 + 3+3+100 = 20112; remaining = 100_000 - 20112 = 79888
    assert state.gas == 79_888


# ---------------------------------------------------------------------------
# Seq 5: CALLDATALOAD — reads 32 bytes of calldata as big-endian bv256
#
# Bytecode (hex):  60 00 35 00
#   PUSH1 0x00 → offset=0
#   CALLDATALOAD → reads calldata[0..31]; gas=3
#   STOP
#
# With calldata = b'\x00'*31 + b'\x01':
#   big-endian assembly of 32 bytes → value = 1
#
# Gas (start=100): PUSH1=3, CALLDATALOAD=3 → used=6, remaining=94
# ---------------------------------------------------------------------------


def test_seq5_calldataload():
    bytecode = bytes([0x60, 0x00, 0x35, 0x00])
    calldata = b"\x00" * 31 + b"\x01"
    ctx = EvmContext(calldata=calldata)
    state, _ = run(bytecode, ctx, initial_gas=100)
    assert state.stack == [1]
    assert state.halted is True
    assert state.trap is False
    assert state.gas == 94  # 100 - 3 - 3


def test_seq5_calldataload_past_end():
    """Reads past calldatasize are zero-padded (§9)."""
    bytecode = bytes([0x60, 0x00, 0x35, 0x00])
    ctx = EvmContext(calldata=b"\xAB")  # 1 byte; remaining 31 bytes are zero
    state, _ = run(bytecode, ctx, initial_gas=100)
    # big-endian: 0xAB followed by 31 zero bytes → 0xAB << 248
    expected = 0xAB << 248
    assert state.stack == [expected]


# ---------------------------------------------------------------------------
# Bonus: MSTORE + MLOAD — memory 32-byte round-trip
#
# Bytecode (hex):  60 be 60 00 52 60 00 51 00
#   PC=0  PUSH1 0xbe → stack=[0xbe]
#   PC=2  PUSH1 0x00 → stack=[0xbe, 0x00]  (0=TOS=offset)
#   PC=4  MSTORE     → mem[0..31] = big-endian(0xbe), mem_words=1; base gas=3
#   PC=5  PUSH1 0x00 → stack=[0x00]
#   PC=7  MLOAD      → reads mem[0..31] → 0xbe; base gas=3
#   PC=8  STOP
#
# Memory expansion gas: first access expands to 1 word.
#   Cmem(0)=0, Cmem(1)=1*1//512+3*1=3; delta=3 charged on MSTORE.
#   MLOAD: new_words=1 (already at HWM) → no extra expansion cost.
#
# Gas (start=100):
#   PUSH1: 3, PUSH1: 3, MSTORE (3+3 expand)=6, PUSH1: 3, MLOAD (3)=3
#   Total: 3+3+6+3+3 = 18; remaining: 82
# ---------------------------------------------------------------------------


def test_bonus_mstore_mload():
    bytecode = bytes([0x60, 0xBE, 0x60, 0x00, 0x52, 0x60, 0x00, 0x51, 0x00])
    state, _ = run(bytecode, initial_gas=100)
    assert state.stack == [0xBE]
    assert state.halted is True
    assert state.trap is False
    assert state.mem_words == 1
    assert state.gas == 82  # 100 - 3 - 3 - 6 - 3 - 3


# ---------------------------------------------------------------------------
# Trap semantics
# ---------------------------------------------------------------------------


def test_trap_invalid_jump_dest():
    """JUMP to a non-JUMPDEST sets trap=True."""
    # PUSH1 3, JUMP  → dest=3 is not a JUMPDEST (it's INVALID)
    bytecode = bytes([0x60, 0x03, 0x56, 0xFE])
    state, _ = run(bytecode, initial_gas=100)
    assert state.trap is True
    assert state.halted is True


def test_trap_stack_underflow():
    """ADD with empty stack sets trap=True before gas is charged."""
    bytecode = bytes([0x01])  # ADD with no stack
    state, _ = run(bytecode, initial_gas=100)
    assert state.trap is True
    assert state.halted is True
    assert state.gas == 100  # gas not charged on underflow


def test_trap_out_of_gas():
    """Running out of gas mid-execution sets trap=True."""
    # PUSH1 1, PUSH1 2, ADD, STOP; costs 3+3+3 = 9; give only 8
    bytecode = bytes([0x60, 0x01, 0x60, 0x02, 0x01, 0x00])
    state, _ = run(bytecode, initial_gas=8)
    assert state.trap is True
    assert state.halted is True


def test_trap_revert():
    """REVERT sets trap=True, halted=True."""
    # PUSH1 0 (len), PUSH1 0 (offset), REVERT
    bytecode = bytes([0x60, 0x00, 0x60, 0x00, 0xFD])
    state, _ = run(bytecode, initial_gas=100)
    assert state.trap is True
    assert state.halted is True
    assert state.returndata == b""


# ---------------------------------------------------------------------------
# Disassembler unit tests
# ---------------------------------------------------------------------------


def test_disasm_push_immediates():
    """PUSH1 and PUSH2 immediates are embedded in Instruction.immediate."""
    from gurdy.pairs.evm_btor2.source_interp import disassemble

    bytecode = bytes([0x60, 0xAB, 0x61, 0xCD, 0xEF, 0x00])
    instrs = disassemble(bytecode)
    assert len(instrs) == 3
    assert instrs[0].opcode == 0x60 and instrs[0].immediate == bytes([0xAB])
    assert instrs[1].opcode == 0x61 and instrs[1].immediate == bytes([0xCD, 0xEF])
    assert instrs[2].opcode == 0x00 and instrs[2].immediate == b""


def test_disasm_pc_offsets():
    """Each Instruction.pc reflects the correct byte offset."""
    bytecode = bytes([0x60, 0x01, 0x60, 0x02, 0x01])
    instrs = disassemble(bytecode)
    assert [i.pc for i in instrs] == [0, 2, 4]


# ---------------------------------------------------------------------------
# Shadow mode
# ---------------------------------------------------------------------------


def test_shadow_records_stack_reads_and_writes():
    """Shadow mode logs every stack pop (read) and push (write)."""
    # PUSH1 3, PUSH1 4, ADD, STOP
    bytecode = bytes([0x60, 0x03, 0x60, 0x04, 0x01, 0x00])
    _, records = run(bytecode, initial_gas=100, shadow=True)
    # ADD record: reads [4, 3] (TOS first), writes [7]
    add_rec = next(r for r in records if r.opcode == 0x01)
    assert set(add_rec.stack_reads) == {3, 4}
    assert add_rec.stack_writes == [7]


def test_shadow_records_storage_rw():
    """Shadow mode logs SLOAD reads and SSTORE reads + writes."""
    bytecode = bytes([0x60, 0x42, 0x60, 0x00, 0x55, 0x60, 0x00, 0x54, 0x00])
    _, records = run(bytecode, initial_gas=100_000, shadow=True)
    sstore_rec = next(r for r in records if r.opcode == 0x55)
    sload_rec = next(r for r in records if r.opcode == 0x54)
    assert (0, 0x42) in sstore_rec.sto_writes
    assert (0, 0x42) in sload_rec.sto_reads


# ---------------------------------------------------------------------------
# Seq 6: JUMPI — conditional branch, taken and not-taken paths
#
# Taken path bytecode (11 bytes):
#   PC=0  PUSH1 0x01 → stack=[1],     gas=97
#   PC=2  PUSH1 0x08 → stack=[1,8],   gas=94   (8=TOS=dest)
#   PC=4  JUMPI      → dest=8, cond=1, gas=84  → PC=8
#   PC=5  PUSH1 0xFF  ← dead code
#   PC=7  INVALID     ← dead code
#   PC=8  JUMPDEST    → gas=83
#   PC=9  PUSH1 0x2A  → stack=[42],   gas=80
#   PC=11 STOP
#
# Not-taken path: cond=0 at PC=4 → fall through to PC=5
#   PC=5  PUSH1 0x2A → stack=[42],    gas=81
#   PC=7  STOP
# ---------------------------------------------------------------------------


def test_seq6_jumpi_taken():
    """JUMPI with non-zero condition jumps to the JUMPDEST target."""
    bytecode = bytes([
        0x60, 0x01,        # PUSH1 1  (condition)
        0x60, 0x08,        # PUSH1 8  (dest, TOS)
        0x57,              # JUMPI
        0x60, 0xFF,        # PUSH1 0xff  — dead code
        0xFE,              # INVALID     — dead code (PC=7)
        0x5B,              # JUMPDEST    (PC=8)
        0x60, 0x2A,        # PUSH1 42
        0x00,              # STOP        (PC=11)
    ])
    state, _ = run(bytecode, initial_gas=100)
    assert state.stack == [42]
    assert state.halted is True
    assert state.trap is False
    assert state.gas == 80  # 100 - 3(PUSH1) - 3(PUSH1) - 10(JUMPI) - 1(JUMPDEST) - 3(PUSH1)


def test_seq6_jumpi_not_taken():
    """JUMPI with zero condition falls through to the next instruction."""
    bytecode = bytes([
        0x60, 0x00,        # PUSH1 0  (condition=0)
        0x60, 0x08,        # PUSH1 8  (dest, TOS — irrelevant when not taken)
        0x57,              # JUMPI    → cond==0, PC advances to 5
        0x60, 0x2A,        # PUSH1 42 (PC=5, taken by fall-through)
        0x00,              # STOP     (PC=7)
    ])
    state, _ = run(bytecode, initial_gas=100)
    assert state.stack == [42]
    assert state.halted is True
    assert state.trap is False
    assert state.gas == 81  # 100 - 3 - 3 - 10(JUMPI) - 3(PUSH1)


def test_seq6_jumpi_invalid_dest_trap():
    """JUMPI to a non-JUMPDEST offset sets trap=True (cond != 0)."""
    # PUSH1 1 (cond), PUSH1 5 (dest=5 which is 0xFE INVALID, not JUMPDEST), JUMPI
    bytecode = bytes([0x60, 0x01, 0x60, 0x05, 0x57, 0xFE, 0x00])
    state, _ = run(bytecode, initial_gas=100)
    assert state.trap is True
    assert state.halted is True


# ---------------------------------------------------------------------------
# Seq 7: RETURN with returndata
#
# Bytecode:
#   PC=0  PUSH1 0xBE → stack=[0xBE]
#   PC=2  PUSH1 0x00 → stack=[0xBE, 0x00]  (offset=TOS)
#   PC=4  MSTORE8    → mem[0]=0xBE; expand to 1 word; gas=3+3=6
#   PC=5  PUSH1 0x01 → stack=[1]   (return length)
#   PC=7  PUSH1 0x00 → stack=[1,0] (return offset=TOS)
#   PC=9  RETURN     → returndata=mem[0..0]=b'\xBE'; mem already 1 word → 0 expand
#
# Gas (start=100): 3+3+6+3+3 = 18 used → 82 remaining
# ---------------------------------------------------------------------------


def test_seq7_return_with_returndata():
    """RETURN copies memory slice into returndata; halt is clean (trap=False)."""
    bytecode = bytes([
        0x60, 0xBE,        # PUSH1 0xBE  (value)
        0x60, 0x00,        # PUSH1 0x00  (offset=TOS)
        0x53,              # MSTORE8     mem[0] = 0xBE
        0x60, 0x01,        # PUSH1 1     (return length)
        0x60, 0x00,        # PUSH1 0     (return offset=TOS)
        0xF3,              # RETURN
    ])
    state, _ = run(bytecode, initial_gas=100)
    assert state.halted is True
    assert state.trap is False
    assert state.returndata == b"\xBE"
    assert state.returndatasize == 1
    assert state.gas == 82  # 100 - 3 - 3 - 6 - 3 - 3


def test_seq7_return_32bytes():
    """RETURN with a 32-byte MSTORE value preserves full big-endian word."""
    # PUSH1 0x42, PUSH1 0x00, MSTORE (32-byte big-endian), PUSH1 0x20, PUSH1 0x00, RETURN
    bytecode = bytes([
        0x60, 0x42,        # PUSH1 0x42  (value)
        0x60, 0x00,        # PUSH1 0x00  (offset=TOS)
        0x52,              # MSTORE      mem[0..31] = 0x00..00 42
        0x60, 0x20,        # PUSH1 32    (return length)
        0x60, 0x00,        # PUSH1 0     (return offset=TOS)
        0xF3,              # RETURN
    ])
    state, _ = run(bytecode, initial_gas=100)
    assert state.halted is True
    assert state.trap is False
    assert state.returndatasize == 32
    assert state.returndata == b"\x00" * 31 + b"\x42"


# ---------------------------------------------------------------------------
# Seq 8: MSTORE8 — writes only the low byte of the value
#
# Bytecode:
#   PC=0  PUSH1 0xAB → stack=[0xAB]
#   PC=2  PUSH1 0x00 → stack=[0xAB, 0x00]  (offset=TOS)
#   PC=4  MSTORE8    → mem[0]=0xAB; expand to 1 word; base 3 + expand 3 = 6
#   PC=5  PUSH1 0x00 → stack=[0x00]
#   PC=7  MLOAD      → reads mem[0..31]; 0xAB at byte 0, zeros for 1..31
#   PC=8  STOP
#
# Gas (start=100): 3+3+6+3+3 = 18 → 82 remaining
# Stack result: 0xAB << 248
# ---------------------------------------------------------------------------


def test_seq8_mstore8_single_byte():
    """MSTORE8 writes one byte at offset; MLOAD confirms only that byte is set."""
    bytecode = bytes([
        0x60, 0xAB,        # PUSH1 0xAB (value)
        0x60, 0x00,        # PUSH1 0x00 (offset=TOS)
        0x53,              # MSTORE8    mem[0] = 0xAB
        0x60, 0x00,        # PUSH1 0    (MLOAD offset)
        0x51,              # MLOAD
        0x00,              # STOP
    ])
    state, _ = run(bytecode, initial_gas=100)
    assert state.stack == [0xAB << 248]
    assert state.mem_words == 1
    assert state.halted is True
    assert state.trap is False
    assert state.gas == 82  # 100 - 3 - 3 - 6 - 3 - 3


def test_seq8_mstore8_truncates_upper_bytes():
    """MSTORE8 stores only value & 0xFF; upper bytes of the word are discarded."""
    # PUSH2 0xCABB, PUSH1 0x00, MSTORE8 → mem[0] must be 0xBB, not 0xCA
    bytecode = bytes([
        0x61, 0xCA, 0xBB,  # PUSH2 0xCABB  (value)
        0x60, 0x00,        # PUSH1 0x00    (offset=TOS)
        0x53,              # MSTORE8       mem[0] = 0xBB
        0x60, 0x00,        # PUSH1 0
        0x51,              # MLOAD
        0x00,              # STOP
    ])
    state, _ = run(bytecode, initial_gas=100)
    assert state.stack == [0xBB << 248]  # only 0xBB, not 0xCA, in position 0
