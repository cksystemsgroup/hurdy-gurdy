"""A small, deterministic RV64IMC program generator for *differential* fuzzing
(BENCHMARKS.md §3 — defeating a cherry-picked corpus).

It emits random **straight-line** RV64IMC programs — a mix of base (32-bit) and
compressed (16-bit) ALU / M instructions with random operands and random initial
register values, ending in ECALL. Straight-line ⇒ guaranteed termination and a
clean instruction boundary at every PC, so no oracle is needed beyond *agreement
between two independent realizations*: the hand-written RISC-V interpreter and
the Sail-derived one must produce identical traces. A divergence is a real bug in
one of them. Seeded ⇒ reproducible (the determinism invariant, ARCHITECTURE.md
§4). The mixed 2-/4-byte stream exercises exactly the C-extension fetch path.

External-generator fuzzing (Csmith, riscv-torture) against the `sail_riscv_sim`
oracle is the complementary axis — pending those tools in the dev image.
"""

from __future__ import annotations

import random
import struct

from gurdy.languages.riscv import asm, casm
from gurdy.languages.riscv.interp import RiscvImage, image_from_bytes

MASK64 = (1 << 64) - 1

# Base (32-bit) reg-reg ops by mnemonic -> asm encoder.
_RR = {m: getattr(asm, m if m not in ("or", "and") else m + "_")
       for m in ("add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or", "and",
                 "addw", "subw", "sllw", "srlw", "sraw",
                 "mul", "mulh", "mulhsu", "mulhu", "div", "divu", "rem", "remu",
                 "mulw", "divw", "divuw", "remw", "remuw")}
_RI = {m: getattr(asm, m) for m in ("addi", "slti", "sltiu", "xori", "ori", "andi", "addiw")}


def _edge(rng: random.Random) -> int:
    """A 64-bit value biased toward the edges where datapath bugs hide."""
    return rng.choice([0, 1, MASK64, 1 << 63, (1 << 63) - 1, 0xFFFFFFFF,
                       rng.getrandbits(64), rng.getrandbits(64)])


def _base(rng: random.Random) -> int:
    kind = rng.random()
    rd, rs1, rs2 = rng.randint(0, 31), rng.randint(0, 31), rng.randint(0, 31)
    if kind < 0.55:                                   # reg-reg (ALU / M / W)
        return _RR[rng.choice(list(_RR))](rd, rs1, rs2)
    if kind < 0.8:                                    # reg-imm
        return _RI[rng.choice(list(_RI))](rd, rs1, rng.randint(-2048, 2047))
    shop = rng.choice(["slli", "srli", "srai", "slliw", "srliw", "sraiw"])  # shifts
    return getattr(asm, shop)(rd, rs1, rng.randint(0, 31 if shop.endswith("w") else 63))


def _comp(rng: random.Random) -> int:
    """A valid compressed instruction (operand constraints respected)."""
    r = rng.randint(1, 31)
    rp, rp2 = 8 + rng.randint(0, 7), 8 + rng.randint(0, 7)   # x8..x15 ("'") regs
    return rng.choice([
        lambda: casm.c_addi(r, rng.randint(-32, 31)),
        lambda: casm.c_li(r, rng.randint(-32, 31)),
        lambda: casm.c_addiw(r, rng.randint(-32, 31)),
        lambda: casm.c_slli(r, rng.randint(1, 63)),
        lambda: casm.c_add(r, rng.randint(1, 31)),
        lambda: casm.c_mv(r, rng.randint(1, 31)),
        lambda: casm.c_and(rp, rp2), lambda: casm.c_or(rp, rp2),
        lambda: casm.c_xor(rp, rp2), lambda: casm.c_sub(rp, rp2),
        lambda: casm.c_addw(rp, rp2), lambda: casm.c_subw(rp, rp2),
        lambda: casm.c_srli(rp, rng.randint(1, 63)),
        lambda: casm.c_srai(rp, rng.randint(1, 63)),
        lambda: casm.c_andi(rp, rng.randint(-32, 31)),
    ])()


def random_program(seed: int, n_instr: int = 24) -> tuple[RiscvImage, dict[int, int]]:
    """A reproducible random straight-line RV64IMC program (image + initial
    register binding). ~40% of instructions are compressed."""
    rng = random.Random(seed)
    code = b""
    for _ in range(n_instr):
        if rng.random() < 0.4:
            code += struct.pack("<H", _comp(rng) & 0xFFFF)
        else:
            code += struct.pack("<I", _base(rng) & 0xFFFFFFFF)
    code += struct.pack("<I", asm.ecall())
    init_regs = {r: _edge(rng) for r in range(1, 32)}
    return image_from_bytes(code), init_regs
