"""Differential testing of the shared RISC-V interpreter against the official
Sail RISC-V emulator ``sail_riscv_sim`` (languages/riscv brief: "Oracle —
differential against the pinned ``sail_riscv_sim``"; DOCKER.md).

The two are compared over the **executed-instruction stream**: for each
retired instruction, the pc of that instruction and the integer register file
afterwards. Canonicalizing both sides this way makes the check independent of
how each tool reports the *post-step* pc or models the halt, and it reuses the
framework's commuting-square oracle (`core.oracle.align`) for the step-by-step
comparison and divergence localization.

Only the external-binary invocation is environment-dependent: the emulator is
located via ``$SAIL_RISCV_SIM`` (or ``sail_riscv_sim`` on ``PATH``), its flags
via ``$SAIL_RISCV_ARGS``, and the exact build is pinned in the container
(DOCKER.md). The trace parser and the comparison are pure and unit-tested; the
oracle callable is injectable so the differential is exercised without the
binary present.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable

from ...core import oracle
from ...core.types import AlignResult, Projection, Trace
from .elf import load_elf
from .interp import RiscvImage, run

_REGS = tuple(f"x{r}" for r in range(1, 32))
# executed-instruction pc + the integer registers (x0 is hardwired zero)
PROJECTION = Projection(("pc_exec", *_REGS))

# Oracle callable: (elf_bytes, max_steps) -> executed-instruction Trace.
Oracle = Callable[[bytes, int], Trace]


class OracleUnavailable(RuntimeError):
    """Raised when ``sail_riscv_sim`` cannot be located."""


def executed_stream(trace: Trace, entry: int) -> Trace:
    """Canonicalize a post-step ``Trace`` into the executed-instruction stream:
    row ``i`` carries ``pc_exec`` (the pc of the instruction executed at step
    ``i``) and the integer register file after it."""
    out: list[dict[str, Any]] = []
    pc_exec = entry
    for row in trace:
        rec: dict[str, Any] = {"pc_exec": pc_exec}
        for r in range(1, 32):
            rec[f"x{r}"] = row.get(f"x{r}")
        out.append(rec)
        pc_exec = row.get("pc")     # next instruction's pc == this row's post-step pc
    return out


# A retired-instruction line: ``[<cyc>] [<priv>]: 0x<pc> (0x<insn>) <asm>``.
_PC_LINE = re.compile(r"\]\s*:\s*0x([0-9a-fA-F]+)\s*\(0x[0-9a-fA-F]+\)")
# A register write: ``x<n> <- 0x<value>``.
_REG_WRITE = re.compile(r"\bx(\d+)\s*<-\s*0x([0-9a-fA-F]+)")


def parse_sail_log(text: str) -> Trace:
    """Parse a sail-riscv instruction/register trace into the executed stream.

    The emulator logs, per retired instruction, a pc line followed by zero or
    more ``x<n> <- 0x<val>`` register-write lines (register printing enabled).
    We accumulate the register file and emit one row per instruction; memory /
    CSR lines are ignored (outside the projection)."""
    regs = [0] * 32
    rows: list[dict[str, Any]] = []
    pending_pc: int | None = None

    def flush() -> None:
        nonlocal pending_pc
        if pending_pc is None:
            return
        rec: dict[str, Any] = {"pc_exec": pending_pc}
        for r in range(1, 32):
            rec[f"x{r}"] = regs[r]
        rows.append(rec)
        pending_pc = None

    for line in text.splitlines():
        m = _PC_LINE.search(line)
        if m:
            flush()
            pending_pc = int(m.group(1), 16)
            continue
        if pending_pc is not None:
            w = _REG_WRITE.search(line)
            if w:
                idx = int(w.group(1))
                if 0 <= idx < 32:
                    regs[idx] = int(w.group(2), 16)
                    regs[0] = 0
    flush()
    return rows


def find_sail() -> str | None:
    return os.environ.get("SAIL_RISCV_SIM") or shutil.which("sail_riscv_sim")


class SailRiscvOracle:
    """Runs ``sail_riscv_sim`` on an ELF and parses its trace."""

    def __init__(self, binary: str | None = None, args: tuple[str, ...] | None = None):
        self.binary = binary or find_sail()
        if args is None:
            # The emulator is SILENT without a trace flag, so an unset
            # $SAIL_RISCV_ARGS must still enable the per-instruction +
            # register-write log the parser consumes (otherwise the
            # differential would align two empty streams — a vacuous pass).
            # ``--trace`` is "all traces except TLB/PTW"; the parser ignores
            # the mem/CSR/clint lines and keeps only the pc and ``x<n> <-``
            # rows. Override the whole flag set via $SAIL_RISCV_ARGS.
            env = os.environ.get("SAIL_RISCV_ARGS")
            args = tuple(env.split()) if env else ("--trace",)
        self.args = args

    def available(self) -> bool:
        return bool(self.binary) and (
            os.path.exists(self.binary) or shutil.which(self.binary) is not None
        )

    def trace(self, elf_bytes: bytes, max_steps: int) -> Trace:
        if not self.available():
            raise OracleUnavailable("sail_riscv_sim not found (set $SAIL_RISCV_SIM)")
        with tempfile.NamedTemporaryFile(suffix=".elf", delete=False) as f:
            f.write(elf_bytes)
            path = f.name
        try:
            proc = subprocess.run(
                [self.binary, *self.args, path],
                capture_output=True, text=True, timeout=300,
            )
        finally:
            os.unlink(path)
        return parse_sail_log(proc.stdout + "\n" + proc.stderr)


def differential(
    elf_bytes: bytes | None = None,
    *,
    image: RiscvImage | None = None,
    subject: Oracle | None = None,
    oracle_fn: Oracle | None = None,
    max_steps: int = 100_000,
    entry_symbol: str | None = None,
    trim_to_common: bool = True,
) -> AlignResult:
    """Compare a *subject* RISC-V interpreter to ``sail_riscv_sim`` on an ELF,
    under the executed-instruction projection.

    The subject defaults to the shared RISC-V interpreter; pass ``subject`` (an
    ``(elf_bytes, max_steps) -> Trace`` callable, e.g. the Sail interpreter's
    ``sail_subject``) to validate a different interpreter against the same gold
    oracle. ``image`` compares a pre-loaded image; ``oracle_fn`` injects an
    oracle (the default runs the real emulator, raising ``OracleUnavailable``
    if it is absent)."""
    if subject is not None:
        ours = subject(elf_bytes or b"", max_steps)
    else:
        if image is None:
            if elf_bytes is None:
                raise ValueError("differential: provide elf_bytes or image")
            image = load_elf(elf_bytes, entry_symbol=entry_symbol)
        # Halt our interpreter on the HTIF ``tohost`` write when the image
        # carries that symbol (the riscv-tests / coverage-slice convention),
        # so it stops where the emulator does instead of spinning in the
        # test's terminal loop up to ``max_steps``.
        binding = {"tohost": image.symbols["tohost"]} if "tohost" in image.symbols else None
        ours = executed_stream(run(image, binding, max_steps=max_steps), image.entry)
    theirs = (oracle_fn or SailRiscvOracle().trace)(elf_bytes or b"", max_steps)

    # An empty oracle stream is not agreement — it is a silent oracle (no trace
    # flag) or an ELF the model could not fetch (wrong link base). Refuse to
    # report a vacuous ``ok`` over two empty streams.
    if not theirs:
        raise OracleUnavailable(
            "oracle produced no executed-instruction trace: enable tracing via "
            "$SAIL_RISCV_ARGS (default '--trace') and link the ELF into the "
            "model's executable region (e.g. 0x80000000)"
        )

    if trim_to_common:
        n = min(len(ours), len(theirs))   # tolerate a trailing halt-logging difference
        ours, theirs = ours[:n], theirs[:n]
    return oracle.align(ours, theirs, PROJECTION)
