"""Assemble a bare-metal AArch64 corpus task from source.S → source.elf.

Requires clang (multi-target) and ld.lld (LLVM linker). Both are
available in the development environment without the aarch64-linux-gnu
cross-toolchain.

Convention for ``source.S``::

    .text
    .globl  _start
    .type   _start, %function
_start:
    # ... AArch64 instructions ...
    svc     #0               /* normal halt */
    .size   _start, .-_start

The assembled ELF::

- Text segment placed at ``TEXT_BASE`` (0x400000 by default) so all
  corpus tasks share a consistent address space.
- Statically linked, no C runtime, entry point ``_start``.
- Linker: ld.lld (part of the LLVM toolchain; handles AArch64 even on
  an x86-64 host, unlike GNU ld which needs a cross-configured build).

Usage::

    python bench/aarch64-btor2/corpus/_assemble_asm.py <task_dir>
    python bench/aarch64-btor2/corpus/_assemble_asm.py <task_dir> --verify

``--verify`` disassembles the resulting ELF with llvm-objdump and
prints the instruction listing so PCs can be confirmed.

Assembly tasks that have been assembled this way record the flags in
``task.toml`` under ``[asm]``::

    [asm]
    assembler = "clang-18"
    assembler_flags = "-target aarch64-linux-gnu -nostdlib -static -fuse-ld=lld -Wl,-e,_start -Wl,-Ttext=0x400000"
    text_base = "0x400000"
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

TEXT_BASE = "0x400000"

_CLANG_FLAGS = [
    "-target", "aarch64-linux-gnu",
    "-nostdlib",
    "-static",
    "-fuse-ld=lld",
    f"-Wl,-e,_start",
    f"-Wl,-Ttext={TEXT_BASE}",
]


def assemble(task_dir: Path, *, verify: bool = False) -> int:
    """Assemble ``source.S`` in *task_dir* to ``source.elf``.

    Returns 0 on success, 1 on failure.
    """
    src = task_dir / "source.S"
    out = task_dir / "source.elf"

    if not src.exists():
        print(f"error: {src} not found", file=sys.stderr)
        return 1

    clang = shutil.which("clang")
    if clang is None:
        print("error: clang not found on PATH", file=sys.stderr)
        return 1
    if shutil.which("ld.lld") is None:
        print("error: ld.lld not found on PATH", file=sys.stderr)
        return 1

    cmd = [clang] + _CLANG_FLAGS + ["-o", str(out), str(src)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"error: clang failed:\n{result.stderr}", file=sys.stderr)
        return 1

    print(f"assembled: {out}  ({out.stat().st_size} bytes)")

    if verify:
        objdump = shutil.which("llvm-objdump")
        if objdump:
            r = subprocess.run([objdump, "-d", str(out)], capture_output=True, text=True)
            print(r.stdout)
        else:
            print("warning: llvm-objdump not found, skipping disassembly")

    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_dir", help="corpus task directory containing source.S")
    ap.add_argument("--verify", action="store_true", help="disassemble the ELF after assembling")
    args = ap.parse_args(argv)

    task_dir = Path(args.task_dir).resolve()
    if not task_dir.is_dir():
        print(f"error: {task_dir} is not a directory", file=sys.stderr)
        return 2

    return assemble(task_dir, verify=args.verify)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["assemble", "TEXT_BASE"]
