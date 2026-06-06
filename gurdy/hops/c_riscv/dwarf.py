"""Reproducible DWARF line-map extraction from a compiled ELF.

The riscv-btor2 source loader's ``from_elf`` only reads a sidecar JSON and
otherwise returns an empty table (it has no in-process ``.debug_line``
decoder), so loading an ELF from *bytes* yields no source map. The chain
needs that map for the transitive ``BTOR2 nid -> pc -> C file:line``
grounding, so this module recovers it by running
``objdump --dwarf=decodedline`` in the pinned image and parsing the output
— the same approach as ``bench/riscv-btor2/corpus/_emit_dwarfmap.py``, but
in-process. (Reading DWARF is not byte-critical: the ELF, already
reproducible from hop 1, fixes the content. The pinned objdump is used for
consistency.)
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from gurdy.hops.c_riscv.compile import toolchain_available
from gurdy.hops.c_riscv.toolchain import ToolchainPin, default_pin

_OBJDUMP = "riscv64-unknown-elf-objdump"
_EXTRACT_TIMEOUT_S = 120

# objdump --dwarf=decodedline rows: "<file> <line|-> <0xaddr> [view] [stmt]".
# The header ("File name ... Line number ...") and CU lines ("task.c:")
# don't match (no <0xaddr> after a bare integer / "-").
_LINE_RE = re.compile(r"^(?P<file>\S+)\s+(?P<line>\d+|-)\s+(?P<addr>0x[0-9a-fA-F]+)")


class LineMapError(RuntimeError):
    """objdump failed while extracting the line map."""


@dataclass(frozen=True)
class LineEntry:
    pc: int
    file: str
    line: int


def parse_decodedline(text: str) -> tuple[tuple[LineEntry, ...], int | None]:
    """Parse ``objdump --dwarf=decodedline`` output into ``(entries, end_pc)``.

    Mirrors ``_emit_dwarfmap.py::parse_decodedline``. The ``-`` line-number
    row is the end-of-sequence sentinel and sets the upper PC bound; other
    rows are ``(pc, file, line)`` anchors.
    """
    entries: list[LineEntry] = []
    end_pc: int | None = None
    in_table = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Contents of the .debug_line"):
            in_table = True
            continue
        if not in_table or not line:
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        addr = int(m["addr"], 16)
        if m["line"] == "-":
            if end_pc is None or addr > end_pc:
                end_pc = addr
            continue
        entries.append(LineEntry(pc=addr, file=m["file"], line=int(m["line"])))
    return tuple(entries), end_pc


def extract_line_map(
    elf_bytes: bytes, *, pin: ToolchainPin | None = None
) -> tuple[tuple[LineEntry, ...], int | None]:
    """Extract the ``pc -> (file, line)`` map from ``elf_bytes`` using the
    pinned objdump. ELF goes in on stdin; decodedline text comes back on
    stdout. Raises ``LineMapError`` if objdump is unavailable or fails."""
    pin = pin or default_pin()
    if not toolchain_available(pin):
        raise LineMapError(
            f"pinned toolchain {pin.ref} not available (line-map extraction needs it)"
        )
    script = f"set -e; cat > /tmp/x.elf; {_OBJDUMP} --dwarf=decodedline /tmp/x.elf"
    cmd = ["docker", "run", "--rm", "-i", pin.ref, "sh", "-c", script]
    try:
        proc = subprocess.run(
            cmd, input=elf_bytes, capture_output=True, timeout=_EXTRACT_TIMEOUT_S
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - env dependent
        raise LineMapError("objdump timed out") from exc
    if proc.returncode != 0:
        raise LineMapError(
            f"objdump failed (exit {proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace')[-500:]}"
        )
    return parse_decodedline(proc.stdout.decode("utf-8", "replace"))


__all__ = ["LineEntry", "LineMapError", "extract_line_map", "parse_decodedline"]
