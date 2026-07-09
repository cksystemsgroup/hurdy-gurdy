"""A curated RV64IMC compliance slice in the riscv-tests convention.

The platform's coverage anchor for the shared RISC-V interpreter
(``languages/riscv`` brief; [`BENCHMARKS.md`](../BENCHMARKS.md) §4): a set of
self-checking programs built with the pinned toolchain
([`DOCKER.md`](../DOCKER.md)) and graded via the HTIF ``tohost`` convention by
``gurdy.languages.riscv.suite``.

Why curated, not the upstream binaries
--------------------------------------
The upstream ``riscv-tests`` ``-p-`` programs open with machine-mode CSR and
trap setup (``csrr a0, mhartid``, ``csrw mtvec``, ``mret``, trap vectors).
The shared interpreter is, by declared scope (``interp.py``), the RV64IMC
**user** ISA only -- SYSTEM with ``funct3 != 0`` (every ``csr*``) and the
privileged instructions hard-abort ``unsupported``. Running the upstream
``-p-`` set would therefore abort on the first instruction, not exercise the
ISA. So this slice re-creates the *grading convention* (HTIF ``tohost`` pass =
1, fail #n = ``(n<<1)|1``, the test number kept in ``gp``/x3) over only the
user subset the interpreter implements. ``sail_riscv_sim`` -- the gold oracle
-- runs these same ELFs via HTIF, so the slice doubles as the differential
corpus (the RISC-V brief's "matches sail_riscv_sim step-for-step on the
coverage slice" acceptance step).

Each program is linked at 0x80000000 (the model's executable base). The RV64I
and RV64M programs assemble ``-march=rv64im``; the RV64C program assembles
``-march=rv64imc`` so the assembler emits the 16-bit forms the interpreter's
compressed decoder must handle.

Run it::

    python tools/riscv_slice.py /tmp/slice     # build the ELFs
    gurdy riscv-suite /tmp/slice               # grade (expect all-pass)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# --- the grading epilogue shared by every program -------------------------
# gp (x3) holds the current test number; a mismatch jumps to ``fail`` which
# writes (gp<<1)|1 to tohost, a clean run writes 1. ``sd`` to tohost halts
# both the interpreter (auto-bound) and sail_riscv_sim (HTIF).
_PROLOGUE = ".section .text\n.globl _start\n_start:\n  li gp, 0\n"
_EPILOGUE = (
    "pass:\n  li a0, 1\n  j _done\n"
    "fail:\n  slli a0, gp, 1\n  ori a0, a0, 1\n"
    "_done:\n  la t6, tohost\n  sd a0, 0(t6)\n1:  j 1b\n"
    ".section .data\n.align 3\nbuf:\n  .dword 0, 0, 0, 0\n"
    '.section .tohost,"aw",@progbits\n.align 3\n.globl tohost\ntohost:\n  .dword 0\n'
)


def case(n: int, op: str, expected: str) -> str:
    """One numbered check: ``op`` computes a result into t0; it must equal
    ``expected`` (a ``li``-able immediate) or control jumps to ``fail``. The
    short ``beq``/``j fail`` idiom keeps the conditional branch in range while
    ``j`` (jal, +/-1MB) reaches ``fail`` from anywhere in the program."""
    return (f"  li gp, {n}\n{op}\n  li t1, {expected}\n"
            f"  beq t0, t1, 1f\n  j fail\n1:\n")


# --- the slice: name -> (march, body between _start and the epilogue) ------

_ARITH = "".join([
    case(1, "  li t0, 5\n  li t2, 37\n  add t0, t0, t2", "42"),
    case(2, "  li t0, 100\n  li t2, 58\n  sub t0, t0, t2", "42"),
    case(3, "  li t0, 40\n  addi t0, t0, 2", "42"),
    case(4, "  li t0, -5\n  addi t0, t0, -3", "-8"),
    case(5, "  lui t0, 0x12345\n  srli t0, t0, 12", "0x12345"),
    case(6, "  li t0, 7\n  li t2, 9\n  slt t0, t0, t2", "1"),
    case(7, "  li t0, 9\n  slti t0, t0, 7", "0"),
    case(8, "  li t0, -1\n  li t2, 1\n  sltu t0, t0, t2", "0"),   # -1 huge unsigned
    # Mixed-sign and equal-operand compares (upstream rv64ui-slt's vectors):
    # same-sign operands cannot tell signed from unsigned — the common-mode
    # experiment's round-1 slt-as-sltu escape (the slice-level instance of
    # incident I23's probe lesson, recorded as I24).
    case(9, "  li t0, -1\n  li t2, 1\n  slt t0, t0, t2", "1"),    # signed: -1 < 1
    case(10, "  li t0, 3\n  li t2, 3\n  slt t0, t0, t2", "0"),    # strictness
])

_LOGIC = "".join([
    case(1, "  li t0, 0xff0\n  li t2, 0x0ff\n  and t0, t0, t2", "0x0f0"),
    case(2, "  li t0, 0xf00\n  li t2, 0x0ff\n  or t0, t0, t2", "0xfff"),
    case(3, "  li t0, 0xfff\n  li t2, 0x0ff\n  xor t0, t0, t2", "0xf00"),
    case(4, "  li t0, 0xabc\n  andi t0, t0, 0x0f0", "0x0b0"),
    case(5, "  li t0, 0xa00\n  ori t0, t0, 0x0bc", "0xabc"),
    case(6, "  li t0, 0xaaa\n  xori t0, t0, -1\n  andi t0, t0, 0x555", "0x555"),  # ~ then mask
])

_SHIFT = "".join([
    case(1, "  li t0, 1\n  slli t0, t0, 10", "0x400"),
    case(2, "  li t0, 0x400\n  srli t0, t0, 4", "0x40"),
    case(3, "  li t0, -16\n  srai t0, t0, 2", "-4"),
    case(4, "  li t0, 1\n  li t2, 12\n  sll t0, t0, t2", "0x1000"),
    case(5, "  li t0, 0x1000\n  li t2, 8\n  srl t0, t0, t2", "0x10"),
    case(6, "  li t0, -256\n  li t2, 4\n  sra t0, t0, t2", "-16"),
    # shift amount masks to low 6 bits (RISC-V defined)
    case(7, "  li t0, 1\n  li t2, 65\n  sll t0, t0, t2", "2"),
])

_WORD = "".join([
    case(1, "  li t0, 0x7fffffff\n  addiw t0, t0, 1", "-2147483648"),   # 32-bit wrap, sext
    case(2, "  li t0, 2\n  li t2, 40\n  addw t0, t0, t2", "42"),
    case(3, "  li t0, 10\n  li t2, 68\n  subw t0, t0, t2", "-58"),
    case(4, "  li t0, 1\n  slliw t0, t0, 31\n  sraiw t0, t0, 31", "-1"),  # sext of bit31
    case(5, "  li t0, 1\n  li t2, 33\n  sllw t0, t0, t2", "2"),           # masks to 5 bits
    case(6, "  li t0, -1\n  li t2, 1\n  srlw t0, t0, t2", "0x7fffffff"),  # 32-bit logical
])

_BRANCH = (
    # each: arrange so the *correct* outcome continues; wrong falls to ``j fail``
    "  li gp, 1\n  li t0, 4\n  li t2, 4\n  beq t0, t2, 1f\n  j fail\n1:\n"
    "  li gp, 2\n  li t0, 4\n  li t2, 5\n  bne t0, t2, 1f\n  j fail\n1:\n"
    "  li gp, 3\n  li t0, -2\n  li t2, 3\n  blt t0, t2, 1f\n  j fail\n1:\n"
    "  li gp, 4\n  li t0, 3\n  li t2, 3\n  bge t0, t2, 1f\n  j fail\n1:\n"
    "  li gp, 5\n  li t0, 1\n  li t2, -1\n  bltu t0, t2, 1f\n  j fail\n1:\n"  # -1 huge
    "  li gp, 6\n  li t0, -1\n  li t2, 1\n  bgeu t0, t2, 1f\n  j fail\n1:\n"
    "  li gp, 7\n  li t0, 4\n  li t2, 5\n  beq t0, t2, fail\n"                # not-taken
)

_JUMP = (
    "  li gp, 1\n  li t0, 0\n  jal ra, 2f\n  j 3f\n"
    "2:\n  li t0, 42\n  jr ra\n"
    "3:\n  li t1, 42\n  beq t0, t1, 1f\n  j fail\n1:\n"
    # jalr to a computed target
    "  li gp, 2\n  la t2, 4f\n  jalr ra, t2, 0\n  j fail\n"
    "4:\n"
)

_LDST = "".join([
    "  la t5, buf\n",
    case(1, "  li t2, 0x1122334455667788\n  sd t2, 0(t5)\n  ld t0, 0(t5)", "0x1122334455667788"),
    case(2, "  li t2, 0xdeadbeef\n  sw t2, 8(t5)\n  lw t0, 8(t5)", "-559038737"),     # sext
    case(3, "  lwu t0, 8(t5)", "0xdeadbeef"),                                          # zext
    case(4, "  li t2, 0x8090\n  sh t2, 16(t5)\n  lh t0, 16(t5)", "-32624"),            # sext 0x8090
    case(5, "  lhu t0, 16(t5)", "0x8090"),
    case(6, "  li t2, 0x84\n  sb t2, 24(t5)\n  lb t0, 24(t5)", "-124"),               # sext 0x84
    case(7, "  lbu t0, 24(t5)", "0x84"),
])

_MUL = "".join([
    case(1, "  li t0, 6\n  li t2, 7\n  mul t0, t0, t2", "42"),
    case(2, "  li t0, -6\n  li t2, 7\n  mul t0, t0, t2", "-42"),
    # mulh of two large positives: (1<<62)*(1<<3) high word
    case(3, "  li t0, 1\n  slli t0, t0, 62\n  li t2, 8\n  mulh t0, t0, t2", "2"),
    case(4, "  li t0, -1\n  li t2, -1\n  mulhu t0, t0, t2", "-2"),   # (2^64-1)^2 high = 2^64-2
    case(5, "  li t0, 3\n  li t2, 1000000\n  mulw t0, t0, t2", "3000000"),
])

_DIV = "".join([
    case(1, "  li t0, 100\n  li t2, 7\n  div t0, t0, t2", "14"),
    case(2, "  li t0, -100\n  li t2, 7\n  div t0, t0, t2", "-14"),     # trunc toward zero
    case(3, "  li t0, -100\n  li t2, 7\n  rem t0, t0, t2", "-2"),      # sign of dividend
    case(4, "  li t0, 100\n  li t2, 7\n  remu t0, t0, t2", "2"),
    # RISC-V-defined: div by zero -> all ones (-1), rem by zero -> dividend
    case(5, "  li t0, 1234\n  li t2, 0\n  div t0, t0, t2", "-1"),
    case(6, "  li t0, 1234\n  li t2, 0\n  rem t0, t0, t2", "1234"),
    # RISC-V-defined: INT_MIN / -1 wraps to INT_MIN (no trap), rem -> 0
    "  li gp, 7\n  li t0, 1\n  slli t0, t0, 63\n  li t2, -1\n  div t0, t0, t2\n"
    "  li t3, 1\n  slli t3, t3, 63\n  beq t0, t3, 1f\n  j fail\n1:\n",
    "  li gp, 8\n  li t0, 1\n  slli t0, t0, 63\n  li t2, -1\n  rem t0, t0, t2\n"
    "  li t1, 0\n  beq t0, t1, 1f\n  j fail\n1:\n",
    case(9, "  li t0, -100\n  li t2, 7\n  divw t0, t0, t2", "-14"),
    case(10, "  li t0, -100\n  li t2, 7\n  remw t0, t0, t2", "-2"),
])

# RV64C: compile -march=rv64imc so gas emits 16-bit forms for these (verified by
# objdump in the build step). Functionally identical arithmetic, decoded through
# the interpreter's compressed expander.
_COMPRESS = "".join([
    case(1, "  li t0, 17\n  addi t0, t0, 25", "42"),     # c.li / c.addi
    case(2, "  li t0, 21\n  add t0, t0, t0", "42"),      # c.add
    case(3, "  li t0, 1\n  slli t0, t0, 12", "0x1000"),  # c.slli
    case(4, "  li t0, 0\n  li t2, 42\n  mv t0, t2", "42"),  # c.mv
    case(5, "  li t0, 5\n  li t2, 5\n  beq t0, t2, 1f\n  j fail\n1:\n  li t0, 42", "42"),
])

SLICE: dict[str, tuple[str, str]] = {
    "rv64ui-arith": ("rv64im", _ARITH),
    "rv64ui-logic": ("rv64im", _LOGIC),
    "rv64ui-shift": ("rv64im", _SHIFT),
    "rv64ui-word": ("rv64im", _WORD),
    "rv64ui-branch": ("rv64im", _BRANCH),
    "rv64ui-jump": ("rv64im", _JUMP),
    "rv64ui-ldst": ("rv64im", _LDST),
    "rv64um-mul": ("rv64im", _MUL),
    "rv64um-div": ("rv64im", _DIV),
    "rv64uc-compress": ("rv64imc", _COMPRESS),
}


def _source(body: str) -> str:
    return _PROLOGUE + body + _EPILOGUE


def find_gcc() -> str | None:
    return os.environ.get("RISCV_GCC") or shutil.which("riscv64-unknown-elf-gcc")


def build(outdir: str | os.PathLike, gcc: str | None = None) -> list[Path]:
    """Assemble every program in the slice into ``outdir`` (one ELF per name,
    no extension, riscv-tests style). Returns the written paths."""
    gcc = gcc or find_gcc()
    if not gcc:
        raise RuntimeError("riscv64-unknown-elf-gcc not found (set $RISCV_GCC)")
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, (march, body) in SLICE.items():
        src = out / f"{name}.s"
        elf = out / name
        src.write_text(_source(body))
        subprocess.run(
            # -mno-relax: keep ``la`` PC-relative (auipc+addi). We use gp (x3)
            # as the test-number register in the riscv-tests convention, so the
            # linker must NOT relax ``la`` to gp-relative addressing (which
            # would compute from our test counter, not __global_pointer$).
            [gcc, "-nostdlib", "-nostartfiles", f"-march={march}", "-mabi=lp64",
             "-mno-relax", "-Wl,--no-relax", "-Wl,-Ttext=0x80000000",
             "-o", str(elf), str(src)],
            check=True, capture_output=True,
        )
        written.append(elf)
    return written


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "build/riscv-slice"
    paths = build(target)
    print(f"built {len(paths)} programs into {target}:")
    for p in paths:
        print(f"  {p.name}")
