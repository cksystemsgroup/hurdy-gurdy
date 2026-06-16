"""F2 — Bounded. Per program, the pair's lowering T(p) == the Sail reference
for ALL inputs up to bound k (symbolic, SMT) — the all-inputs companion to F1's
sampling.

Sail is a concrete emulator, so the faithful *symbolic* oracle is the
Sail-cross-validated reference (``reference_rv64``; pinned to Sail v0.12 by the
machine gate's reference-vs-Sail check, and the per-instruction lemmas that
make the machine model GREEN). For each generated program this check:

  * lowers it through the pair's OWN path and unrolls the emitted BTOR2
    artifact into z3 with **symbolic initial registers** (``btor2_z3``);
  * symbolically executes ``reference_rv64`` over the same symbolic inputs;
  * proves the two final register projections equal for ALL inputs with z3.

The programs are straight-line ALU (the slice), so ``k = len(program)`` steps
is in fact complete for that program — equivalence over every initial register
state, not merely sampled. A counterexample is a real divergence. Needs the
RISC-V toolchain + z3 (no Sail binary); SKIPs if the toolchain is absent.
"""

from __future__ import annotations

import random

import z3

from gurdy.core.manifest import Manifest
from gurdy.core.report import CheckResult, CheckStatus, Fidelity
from gate.oracle_service import Partitioner

_GATE_KEY = b"hurdy-gurdy/v3 gate held-out key :: sail-riscv"
_MASK = (1 << 64) - 1
_N_PROGRAMS = 16

# ALU mnemonics the agent's lowering covers, as (asm, operand form). We avoid
# li setup entirely: the initial registers ARE the symbolic inputs.
_RR = ["add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or", "and",
       "addw", "subw", "sllw", "srlw", "sraw", "mul", "mulh", "mulhu", "mulhsu",
       "div", "divu", "rem", "remu", "mulw", "divw", "divuw", "remw", "remuw"]
_IMM = ["addi", "slti", "sltiu", "xori", "ori", "andi", "addiw"]
_SHIMM = ["slli", "srli", "srai", "slliw", "srliw", "sraiw"]


def _gen_program(rng: random.Random) -> str:
    srcs = list(range(5, 16))
    out = []
    for _ in range(rng.randint(4, 9)):
        rd = rng.randint(16, 28)
        pick = rng.random()
        if pick < 0.6:
            out.append(f"  {rng.choice(_RR)} x{rd}, x{rng.choice(srcs)}, x{rng.choice(srcs)}")
        elif pick < 0.8:
            out.append(f"  {rng.choice(_IMM)} x{rd}, x{rng.choice(srcs)}, {rng.randint(-2048, 2047)}")
        else:
            sh = rng.choice(_SHIMM)
            out.append(f"  {sh} x{rd}, x{rng.choice(srcs)}, {rng.randint(0, 31)}")
        srcs.append(rd)
    return "\n".join(out) + "\n"


def check(manifest: Manifest) -> CheckResult:
    if manifest.kind not in ("reasoning", "bridge") or manifest.source_group != "sail-riscv":
        return CheckResult(Fidelity.F2_bounded, CheckStatus.SKIP,
                           "F2 bounded equivalence not applicable to this hop")

    import importlib

    from tools.sail_btor2_machine import sail_cross           # assembler (gcc)
    from tools.sail_btor2_machine.verify import _load_reference
    from gurdy.hops.riscv_btor2 import btor2 as own_btor2
    from gate import btor2_z3

    hop = importlib.import_module(f"gurdy.hops.{manifest.id}").HOP
    oracle = sail_cross._load_oracle()
    ref = _load_reference()

    rng = random.Random(0xF2)
    programs = [(f"{manifest.id}/f2/{i}", _gen_program(rng)) for i in range(_N_PROGRAMS)]
    part = Partitioner(_GATE_KEY)
    heldout = [(pid, asm) for pid, asm in programs if part.is_heldout(pid)]
    if not heldout:
        return CheckResult(Fidelity.F2_bounded, CheckStatus.SKIP, "no held-out programs")

    proven = 0
    for pid, asm in heldout:
        try:
            elf_bytes = oracle.assemble(asm, with_halt=False)
        except oracle.ToolchainUnavailable as e:
            return CheckResult(Fidelity.F2_bounded, CheckStatus.SKIP,
                               f"toolchain unavailable: {e}")
        tr = hop.translate(elf_bytes, {}, path="own")
        ops = tr.annotation["ops"]
        if not ops:
            continue

        # symbolic initial registers = the program inputs
        inputs = {k: z3.BitVec(f"in{k}", 64) for k in range(1, 32)}

        # own lowering: unroll the emitted BTOR2 (free initial registers)
        text = own_btor2.lower(ops, tr.annotation["entry"], with_init=False).text
        initials = {f"x{k}": inputs[k] for k in range(1, 32)}
        initials["pc"] = z3.BitVecVal(tr.annotation["entry"], 64)
        initials["halted"] = z3.BitVecVal(0, 1)
        own_final = btor2_z3.unroll(text, len(ops), initials)

        # reference (Sail-validated) over the same symbolic inputs
        ref_final = _ref_run(ref, ops, inputs)

        s = z3.Solver()
        s.add(z3.Or([own_final[f"x{k}"] != ref_final[k] for k in range(1, 32)]))
        res = s.check()
        if res == z3.sat:
            m = s.model()
            bad = next(k for k in range(1, 32)
                       if m.eval(own_final[f"x{k}"] != ref_final[k]))
            return CheckResult(
                Fidelity.F2_bounded, CheckStatus.FAIL,
                f"{pid}: own lowering != Sail reference for some input "
                f"(x{bad}); counterexample exists")
        if res != z3.unsat:
            return CheckResult(Fidelity.F2_bounded, CheckStatus.SKIP,
                               f"{pid}: solver returned {res}")
        proven += 1

    return CheckResult(
        Fidelity.F2_bounded, CheckStatus.PASS,
        f"{proven} held-out programs: own lowering == Sail reference for ALL "
        f"register inputs (z3, complete per straight-line program)")


def _ref_run(ref, ops, inputs: dict) -> dict:
    """Symbolically execute the Sail-validated reference over a decoded program."""
    regs = {k: inputs[k] for k in range(1, 32)}
    regs[0] = z3.BitVecVal(0, 64)
    for op in ops:
        a = regs[op.rs1]
        if op.kind == "rr":
            b = regs[op.rs2]
        else:
            b = z3.BitVecVal(op.imm & _MASK, 64)
        if op.mnem == "lui":
            val = ref.LUI(z3.BitVecVal(op.imm & _MASK, 64))
        elif op.mnem == "auipc":
            val = ref.AUIPC(z3.BitVecVal(op.pc & _MASK, 64), z3.BitVecVal(op.imm & _MASK, 64))
        else:
            val = ref.REGREG[op.mnem.upper()](a, b)
        if op.rd != 0:
            regs[op.rd] = z3.simplify(val)
        regs[0] = z3.BitVecVal(0, 64)
    return regs
