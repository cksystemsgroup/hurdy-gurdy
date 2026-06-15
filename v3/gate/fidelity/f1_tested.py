"""F1 — Tested. The pair's OWN lowering agrees with the Sail reference on a
generated program suite, validated on the **held-out** partition (the
``differential_only`` discipline).

This exercises the agent's independent lowering end-to-end: each held-out
program is run through ``HOP.translate(path="own")`` (the agent's static
decode + specializing semantics) and through the Sail emulator, and the
resulting register projections are compared. Because the lowering never saw
Sail (independence audit), agreement is a genuine differential — informative
about both the pair and Sail.

If Sail (or the RISC-V toolchain) is unavailable, F1 SKIPs with a reason.
"""

from __future__ import annotations

import random

from gurdy.core.manifest import Manifest
from gurdy.core.report import CheckResult, CheckStatus, Fidelity
from gate.oracle_service import Partitioner

# Gate-owned partition key (secret/per-run in a live gate; pinned here for a
# reproducible skeleton). The agent never sees it, so it cannot tell a
# program's partition and cannot selectively avoid the validation set.
_GATE_KEY = b"hurdy-gurdy/v3 gate held-out key :: sail-riscv"
_MASK = (1 << 64) - 1
_N_PROGRAMS = 40
_MAX_SHOWN = 5

_ALU = ["add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or", "and",
        "addw", "subw", "sllw", "srlw", "sraw", "mul", "mulh", "mulhu", "mulhsu",
        "div", "divu", "rem", "remu", "mulw", "divw", "divuw", "remw", "remuw"]


def _gen_program(rng: random.Random) -> str:
    srcs = list(range(5, 14))
    body = "".join(
        f"  li x{r}, {_signed(rng.getrandbits(64))}\n" for r in srcs)
    for _ in range(rng.randint(4, 12)):
        body += (f"  {rng.choice(_ALU)} x{rng.randint(15, 28)}, "
                 f"x{rng.choice(srcs)}, x{rng.choice(srcs)}\n")
    return body


def _signed(v: int) -> int:
    v &= _MASK
    return v - (1 << 64) if v >> 63 else v


def check(manifest: Manifest) -> CheckResult:
    if manifest.kind not in ("reasoning", "bridge") or manifest.source_group != "sail-riscv":
        return CheckResult(Fidelity.F1_tested, CheckStatus.SKIP,
                           "F1 differential not applicable to this hop")

    import importlib

    from tools.sail_btor2_machine import sail_cross           # gate tooling: Sail
    from gurdy.hops.riscv_btor2 import decode

    hop = importlib.import_module(f"gurdy.hops.{manifest.id}").HOP
    oracle = sail_cross._load_oracle()
    try:
        oracle.sail_binary()
    except oracle.SailUnavailable as e:
        return CheckResult(Fidelity.F1_tested, CheckStatus.SKIP,
                           f"Sail unavailable: {e}")

    rng = random.Random(0xF1)
    programs = [(f"{manifest.id}/prog/{i}", _gen_program(rng)) for i in range(_N_PROGRAMS)]
    part = Partitioner(_GATE_KEY)
    heldout = [(pid, asm) for pid, asm in programs if part.is_heldout(pid)]
    if not heldout:
        return CheckResult(Fidelity.F1_tested, CheckStatus.SKIP, "no held-out programs generated")

    divergences: list[str] = []
    checked = 0
    for pid, asm in heldout:
        try:
            elf_bytes = oracle.assemble(asm, with_halt=False)
        except oracle.ToolchainUnavailable as e:
            return CheckResult(Fidelity.F1_tested, CheckStatus.SKIP,
                               f"toolchain unavailable: {e}")
        # the pair's OWN lowering (static decode + specializing semantics)
        tr = hop.translate(elf_bytes, {}, path="own")
        own = decode.run(tr.annotation["ops"])
        # the Sail reference on the same program
        projs = oracle.run(elf_bytes, max_steps=tr.annotation["n_insns"])
        sail = projs[-1].regs if projs else {}
        checked += 1
        for k in range(1, 32):
            if (own.get(k, 0) & _MASK) != (sail.get(k, 0) & _MASK):
                divergences.append(
                    f"{pid} x{k}: own=0x{own.get(k, 0):016x} sail=0x{sail.get(k, 0):016x}")
                break

    if divergences:
        shown = "; ".join(divergences[:_MAX_SHOWN])
        more = "" if len(divergences) <= _MAX_SHOWN else f" (+{len(divergences) - _MAX_SHOWN} more)"
        return CheckResult(Fidelity.F1_tested, CheckStatus.FAIL,
                           f"{len(divergences)}/{checked} held-out programs diverge from Sail: {shown}{more}")

    return CheckResult(
        Fidelity.F1_tested, CheckStatus.PASS,
        f"{checked} held-out programs: own lowering agrees with Sail v0.12 "
        f"(of {_N_PROGRAMS} generated; differential_only held-out discipline)")
