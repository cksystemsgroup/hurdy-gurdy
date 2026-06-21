"""c -> RISC-V translator (pairs/c-riscv): a **pinned** C compiler.

The translator is opaque (nobody predicts ``gcc -O2`` from a schema), so its
honest fidelity is ``reproducible``: the same toolchain + the same fixed,
ordered flags + the same source produce a **byte-identical** ELF. Determinism
is achieved by pinning the flags and dropping host-leaking bytes (no debug
paths, no unwind tables); meaning-preservation is established *downstream* via
the RISC-V→BTOR2 route(s) and a C-level differential, not by reading the
translation.

Pin: ``riscv64-unknown-elf-gcc`` (located via ``$RISCV_GCC`` or PATH) with the
flags in ``FLAGS``. Migrating the pin (new compiler version) is a versioned
change that may shift addresses and must re-validate.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Fixed, ordered flags. rv64im (no compressed, so the 4-byte fetch is exact),
# freestanding, no unwind tables / debug paths -> reproducible bytes.
FLAGS = (
    "-O2", "-nostdlib", "-nostartfiles", "-march=rv64im", "-mabi=lp64",
    "-fno-asynchronous-unwind-tables", "-static",
)


class CompilerUnavailable(RuntimeError):
    """Raised when the pinned C compiler cannot be located."""


def find_gcc() -> str | None:
    return os.environ.get("RISCV_GCC") or shutil.which("riscv64-unknown-elf-gcc")


def compile_c(source: str, gcc: str | None = None,
              extra_flags: tuple[str, ...] = ()) -> bytes:
    """Compile C source to a RISC-V ELF with the pinned compiler + flags.

    ``extra_flags`` appends to the pinned ``FLAGS`` for a **non-reproducible**
    parallel build only (e.g. ``-g`` for line-level carry-back, ``lift.py``);
    the reproducible artifact is always the default (empty ``extra_flags``).
    """
    gcc = gcc or find_gcc()
    if not gcc or not (shutil.which(gcc) or os.path.exists(gcc)):
        raise CompilerUnavailable("riscv64-unknown-elf-gcc not found (set $RISCV_GCC)")
    with tempfile.TemporaryDirectory() as d:
        src, out = Path(d) / "prog.c", Path(d) / "prog.elf"
        src.write_text(source)
        subprocess.run([gcc, *FLAGS, *extra_flags, "-o", str(out), str(src)],
                       check=True, capture_output=True)
        return out.read_bytes()


def translate(program: Any) -> bytes:
    """``program`` is the C source (a string) or ``{"source": ...}``."""
    source = program["source"] if isinstance(program, dict) else program
    return compile_c(source)
