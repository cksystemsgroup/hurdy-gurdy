"""Tests for the c-riscv DWARF line-map extraction.

``parse_decodedline`` is pure and tested without docker; ``extract_line_map``
is docker-guarded like the rest of the hop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gurdy.hops.c_riscv import toolchain_available
from gurdy.hops.c_riscv.dwarf import extract_line_map, parse_decodedline

REPO = Path(__file__).resolve().parents[3]
TASK0101 = (
    REPO / "bench" / "riscv-btor2" / "corpus" / "0101-c-add-trap-bug" / "task.c"
)

# A captured `objdump --dwarf=decodedline` sample (image format).
_SAMPLE = """
out.elf:     file format elf64-littleriscv

Contents of the .debug_line section:

task.c:
File name                        Line number    Starting address    View    Stmt
task.c                                    11             0x10000               x
task.c                                    12             0x10008       1       x
task.c                                     -             0x10050
"""


def test_parse_decodedline_pure():
    entries, end_pc = parse_decodedline(_SAMPLE)
    assert end_pc == 0x10050
    assert [(e.pc, e.file, e.line) for e in entries] == [
        (0x10000, "task.c", 11),
        (0x10008, "task.c", 12),
    ]


def test_parse_decodedline_ignores_header_and_preamble():
    # The "File name ... Line number" header and the "task.c:" CU line
    # must not be parsed as anchors.
    entries, _ = parse_decodedline(_SAMPLE)
    assert all(e.file == "task.c" and isinstance(e.line, int) for e in entries)
    assert all(e.line > 0 for e in entries)


@pytest.mark.skipif(
    not toolchain_available(),
    reason="pinned bench Docker image not available",
)
def test_extract_line_map_from_compiled_elf():
    from gurdy.hops.c_riscv import compile_c

    elf = compile_c(TASK0101.read_bytes(), source_name="task.c").elf_bytes
    entries, end_pc = extract_line_map(elf)
    assert entries, "no line entries recovered"
    assert all(e.file.endswith("task.c") for e in entries)
    assert end_pc is not None and end_pc > 0
    # Entries should be PC-sorted-ish and within [entry, end_pc].
    assert max(e.pc for e in entries) < end_pc
