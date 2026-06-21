"""Target-to-source interpreter ``L`` for c-riscv: carry a RISC-V behavior
back toward the C source.

Two granularities, both reading the reproducible (no-``-g``) ELF's addresses:

* **function-level** (``c_function_at``) — maps a RISC-V pc to the enclosing C
  function via the ELF symbol table; needs no debug info, so it is always
  available ("reached in ``f``").
* **line-level** (``c_line_at``) — maps a pc to ``(c_file, line)``. The
  reproducible artifact deliberately carries no debug-line info, so this
  compiles a **parallel ``-g`` build** of the same source and resolves through
  the toolchain's ``addr2line``. ``-g`` is orthogonal to ``-O2`` codegen, so
  the debug build's code bytes are identical to the reproducible ELF's (asserted
  in the c-riscv tests) — the line table is valid for the reproducible
  addresses, and the throwaway debug build never becomes the pinned artifact.

``lift`` re-projects the RISC-V trace into the pair's observable shape.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ...core.types import Trace
from .translate import CompilerUnavailable, compile_c, find_gcc

# addr2line prints "<path>:<line>" (optionally "<path>:<line> (discriminator N)").
_ADDR2LINE = re.compile(r"^(.*?):(\d+)")


def lift(target_trace: Trace) -> Trace:
    out: list[dict[str, Any]] = []
    for row in target_trace:
        rec: dict[str, Any] = {"pc": row.get("pc"), "halted": bool(row.get("halted", 0))}
        for i in range(1, 32):
            rec[f"x{i}"] = row.get(f"x{i}")
        out.append(rec)
    return out


def c_function_at(image, pc: int) -> str | None:
    """The C function enclosing ``pc`` (nearest preceding code symbol)."""
    best_name, best_addr = None, -1
    for name, addr in image.symbols.items():
        if name.startswith("$"):
            continue   # ELF mapping symbols ($x...), not functions
        if image.code_lo <= addr <= pc and addr > best_addr:
            best_name, best_addr = name, addr
    return best_name


def find_addr2line(gcc: str | None = None) -> str | None:
    """Locate the toolchain ``addr2line`` (the binutils sibling of the pinned
    ``gcc``): ``$RISCV_ADDR2LINE``, then PATH, then derived from the gcc path."""
    cand = os.environ.get("RISCV_ADDR2LINE") or shutil.which("riscv64-unknown-elf-addr2line")
    if cand:
        return cand
    gcc = gcc or find_gcc()
    if gcc and gcc.endswith("gcc"):
        sib = gcc[:-3] + "addr2line"
        if os.path.exists(sib) or shutil.which(sib):
            return sib
    return None


def c_line_at(source: str, pc: int, gcc: str | None = None,
              addr2line: str | None = None) -> tuple[str, int] | None:
    """Line-level carry-back: map a RISC-V ``pc`` to ``(c_file, line)``.

    Compiles a parallel ``-g`` build of ``source`` (identical code bytes to the
    reproducible ELF; see the module docstring) and resolves ``pc`` through
    ``addr2line``. Returns ``None`` when ``pc`` has no source line (e.g. it falls
    outside the compiled code). Only the file *basename* is returned, so the
    throwaway debug build's host path never leaks.
    """
    a2l = addr2line or find_addr2line(gcc)
    if not a2l:
        raise CompilerUnavailable(
            "riscv64-unknown-elf-addr2line not found (set $RISCV_ADDR2LINE)")
    debug_elf = compile_c(source, gcc, extra_flags=("-g",))
    with tempfile.TemporaryDirectory() as d:
        elf = Path(d) / "prog.debug.elf"
        elf.write_bytes(debug_elf)
        out = subprocess.run([a2l, "-e", str(elf), f"0x{pc:x}"],
                             check=True, capture_output=True, text=True).stdout
    m = _ADDR2LINE.match(out.strip())
    if not m:
        return None
    path, line = m.group(1), int(m.group(2))
    if path == "??" or line == 0:
        return None
    return os.path.basename(path), line
