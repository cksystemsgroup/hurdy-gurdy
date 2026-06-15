"""The reference realization: the pinned Sail-RISCV executable model.

Uniform interface ``run(program, binding) -> [Projection]`` over the Sail
emulator. This is the *reference* the gate trusts; it is exposed to builder
agents only through the gate's sandboxed oracle service (never directly, for
``differential_only`` pairs).

HOW IT WORKS
============
The pinned Sail-RISCV release ships a single unified simulator binary,
``sail_riscv_sim`` (RV64 by default; see the repo-root ``Dockerfile`` Sail
layer, tag 0.12). We drive it with its trace flags::

    sail_riscv_sim --inst-limit N --trace-instr --trace-gpr program.elf

and parse the per-step trace into ``Projection`` records. The trace emits,
per retired instruction::

    [k] [M]: 0x<pc> (0x<word>) <disasm>            <sym>+<off>
    x<i> <- 0x<value>           # zero or more GPR writebacks for that step

The machine halts via HTIF (a store of 1 to the ``tohost`` symbol); when it
halts the simulator simply stops emitting steps before the instruction limit
is reached, so ``halted`` is inferred from "retired fewer steps than the
limit". This is a concrete, executable reference: give it a program (and an
initial register binding) and it yields the observed architectural state.

The symbolic per-instruction reference used by the F3 lowering lemmas lives in
``semantics/sail-riscv/reference_rv64.py``; that reference is itself
cross-validated against THIS emulator (see
``tools/sail_btor2_machine/verify.reference_vs_sail``), which discharges the
"stands in for Sail" caveat honestly.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

XLEN = 64
NREGS = 32

# RV64 bare-metal load address used by the Sail default config (RAM base).
RAM_BASE = 0x80000000


# ---------------------------------------------------------------------------
# Projection — the pinned observable state for the rv64 group
# ---------------------------------------------------------------------------

@dataclass
class Projection:
    """Observable state for one retired instruction (the pinned pi for rv64).

    ``pc``      : architectural address of the retired instruction.
    ``regs``    : full general-purpose register file x0..x31 after this
                  instruction's writebacks (x0 is always 0). Callers that pin
                  only ``x1..x31`` simply ignore x0.
    ``halted``  : True on the last projection iff the machine stopped (HTIF)
                  rather than hitting the instruction limit.
    """

    pc: int = 0
    regs: dict[int, int] = field(default_factory=dict)   # x0..x31
    halted: bool = False


# ---------------------------------------------------------------------------
# Toolchain / binary discovery
# ---------------------------------------------------------------------------

class SailUnavailable(RuntimeError):
    """Raised when no Sail-RISCV simulator binary can be found."""


class ToolchainUnavailable(RuntimeError):
    """Raised when no RISC-V assembler/linker can be found."""


def sail_binary() -> str:
    """Locate the Sail-RISCV simulator. Search order:

      1. ``$SAIL_RISCV_SIM`` (explicit path),
      2. ``sail_riscv_sim`` on PATH (the 0.12+ unified release binary),
      3. ``riscv_sim_RV64`` on PATH (legacy make-build name).
    """
    env = os.environ.get("SAIL_RISCV_SIM")
    if env:
        if Path(env).is_file() and os.access(env, os.X_OK):
            return env
        raise SailUnavailable(f"$SAIL_RISCV_SIM={env!r} is not an executable file")
    for name in ("sail_riscv_sim", "riscv_sim_RV64"):
        found = shutil.which(name)
        if found:
            return found
    raise SailUnavailable(
        "no Sail-RISCV simulator found (looked for $SAIL_RISCV_SIM, "
        "sail_riscv_sim, riscv_sim_RV64). Install the pinned release — see "
        "the Sail layer in the repo-root Dockerfile (tag 0.12)."
    )


def _gcc() -> str:
    env = os.environ.get("SAIL_RISCV_GCC")
    if env:
        return env
    for name in ("riscv64-unknown-elf-gcc", "riscv64-elf-gcc", "riscv64-linux-gnu-gcc"):
        found = shutil.which(name)
        if found:
            return found
    raise ToolchainUnavailable(
        "no RISC-V gcc found (looked for $SAIL_RISCV_GCC, "
        "riscv64-unknown-elf-gcc, ...). Needed only to assemble test programs."
    )


def available() -> bool:
    """True iff a Sail simulator binary is reachable (cheap, no run)."""
    try:
        sail_binary()
        return True
    except SailUnavailable:
        return False


# ---------------------------------------------------------------------------
# Assembling tiny RV64 test programs (host toolchain)
# ---------------------------------------------------------------------------

# A minimal bare-metal layout: code at RAM_BASE, a page-aligned .tohost word so
# the Sail HTIF can find the ``tohost`` symbol to halt on.
_LINKER_SCRIPT = """\
OUTPUT_ARCH("riscv")
ENTRY(_start)
SECTIONS {
  . = 0x80000000;
  .text.init : { *(.text.init) }
  .text      : { *(.text) }
  .data      : { *(.data) }
  . = ALIGN(0x1000);
  .tohost    : { *(.tohost) }
  .bss       : { *(.bss) }
}
"""

# Standard HTIF halt epilogue: write 1 to ``tohost`` then spin. Appended after
# the caller's instruction sequence. Uses t0/t1 (x5/x6) as scratch.
HALT_EPILOGUE = """\
  la   t0, tohost
  li   t1, 1
  sd   t1, 0(t0)
9: j 9b
.section .tohost, "aw", @progbits
.align 6
.globl tohost
tohost: .dword 0
.globl fromhost
fromhost: .dword 0
"""

_PROLOGUE = """\
.section .text.init
.globl _start
_start:
"""


def assemble(body_asm: str, *, march: str = "rv64im", with_halt: bool = True) -> bytes:
    """Assemble+link an RV64 program from an instruction body, returning ELF
    bytes ready for ``run``. ``body_asm`` is placed at ``_start``; unless
    ``with_halt`` is False a HTIF halt epilogue is appended so the program
    terminates. Uses the host RISC-V gcc (bare-metal, no startup files)."""
    gcc = _gcc()
    src = _PROLOGUE + body_asm + ("\n" + HALT_EPILOGUE if with_halt else "\n")
    with tempfile.TemporaryDirectory(prefix="sail_asm_") as d:
        dp = Path(d)
        (dp / "p.s").write_text(src)
        (dp / "link.ld").write_text(_LINKER_SCRIPT)
        elf = dp / "p.elf"
        cmd = [
            gcc, f"-march={march}", "-mabi=lp64", "-nostdlib", "-nostartfiles",
            "-static", "-T", str(dp / "link.ld"), "-o", str(elf), str(dp / "p.s"),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise ToolchainUnavailable(
                f"assembly failed:\n{res.stderr}\n--- source ---\n{src}"
            )
        return elf.read_bytes()


# ---------------------------------------------------------------------------
# Running the Sail emulator and parsing its trace
# ---------------------------------------------------------------------------

_STEP_RE = re.compile(r"^\[\d+\]\s+\[\w+\]:\s+0x([0-9A-Fa-f]+)\s+\(0x([0-9A-Fa-f]+)\)")
_GPR_RE = re.compile(r"^x(\d+)\s+<-\s+0x([0-9A-Fa-f]+)")


def run(program: bytes, binding: dict | None = None, *, max_steps: int = 64) -> list[Projection]:
    """Execute an RV64 ELF on the pinned Sail emulator; return the per-step
    projection list (one ``Projection`` per retired instruction, up to
    ``max_steps``).

    ``binding`` may carry ``{"regs": {idx: value, ...}}`` giving the initial
    register file (defaults to all-zero). Because the Sail CLI does not accept
    an arbitrary initial register state, callers that need preset operands must
    materialize them in the program itself (see ``assemble``); the binding here
    only seeds the projection's running register file so the reported values
    are absolute, not deltas.
    """
    binding = binding or {}
    sail = sail_binary()

    with tempfile.NamedTemporaryFile(suffix=".elf", delete=False) as tf:
        tf.write(program)
        elf_path = tf.name
    try:
        cmd = [sail, "--inst-limit", str(max_steps),
               "--trace-instr", "--trace-gpr", elf_path]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    finally:
        os.unlink(elf_path)

    text = res.stdout + "\n" + res.stderr

    # running register file: x0..x31, x0 hardwired 0, overlaid with binding
    regs = {i: 0 for i in range(NREGS)}
    for i, v in (binding.get("regs") or {}).items():
        regs[int(i)] = int(v) & ((1 << XLEN) - 1)

    projections: list[Projection] = []
    cur_pc: int | None = None
    have_step = False

    def flush():
        nonlocal have_step
        if have_step:
            snap = dict(regs)
            snap[0] = 0
            projections.append(Projection(pc=cur_pc, regs=snap, halted=False))
            have_step = False

    for line in text.splitlines():
        line = line.strip()
        m = _STEP_RE.match(line)
        if m:
            flush()                       # finalize the previous step
            cur_pc = int(m.group(1), 16)
            have_step = True
            continue
        g = _GPR_RE.match(line)
        if g and have_step:
            idx = int(g.group(1))
            val = int(g.group(2), 16) & ((1 << XLEN) - 1)
            if idx != 0:                  # x0 is hardwired zero
                regs[idx] = val
    flush()                               # finalize the last step

    # halted iff the machine stopped before exhausting the instruction limit
    if projections and len(projections) < max_steps:
        projections[-1].halted = True

    return projections
