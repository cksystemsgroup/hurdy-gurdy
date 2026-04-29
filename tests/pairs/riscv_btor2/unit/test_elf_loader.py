import json

import pytest

from gurdy.pairs.riscv_btor2.source.elf import EM_RISCV, RISCVBinary, parse_elf
from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary

from tests.fixtures.elf_builder import FuncDef, build_elf


# A handful of synthetic instruction words. We don't decode these
# semantically yet; we just want bytes that round-trip correctly.
# 0x00000013 = nop (addi x0, x0, 0)
# 0x00008067 = ret  (jalr x0, 0(x1))
# 0x00100513 = li a0, 1 (addi a0, x0, 1)
# 0x00150513 = addi a0, a0, 1
# C.NOP (0x0001) is RVC.
TEXT_BASE = 0x10000

ADD2_BYTES = bytes.fromhex(
    "13050100"  # 13 05 01 00  ; addi a0, x0, 1
    "13051500"  # 13 05 15 00  ; addi a0, a0, 1
    "67800000"  # 67 80 00 00  ; ret
)


def _build_fixture():
    funcs = [FuncDef(name="add2", addr=TEXT_BASE, size=len(ADD2_BYTES))]
    return build_elf(ADD2_BYTES, TEXT_BASE, funcs)


def test_parse_elf_reads_header_and_machine():
    data = _build_fixture()
    elf = parse_elf(data)
    assert elf.header.machine == EM_RISCV
    assert elf.header.entry == TEXT_BASE


def test_riscv_binary_finds_functions():
    bin_ = RISCVBinary.from_bytes(_build_fixture())
    fns = bin_.functions()
    assert [f.name for f in fns] == ["add2"]
    f = bin_.function("add2")
    assert f is not None
    assert f.start == TEXT_BASE
    assert f.end == TEXT_BASE + len(ADD2_BYTES)


def test_read_bytes_matches_text():
    bin_ = RISCVBinary.from_bytes(_build_fixture())
    got = bin_.read_bytes(TEXT_BASE, len(ADD2_BYTES))
    assert got == ADD2_BYTES


def test_loader_implements_protocol(tmp_path):
    p = tmp_path / "add2.elf"
    p.write_bytes(_build_fixture())
    src = load_riscv_binary(p)
    assert src.is_riscv
    f = src.function("add2")
    assert f is not None
    assert f.start == TEXT_BASE


def test_loader_loads_dwarf_sidecar(tmp_path):
    p = tmp_path / "add2.elf"
    p.write_bytes(_build_fixture())
    sidecar = tmp_path / "add2.elf.dwarfmap.json"
    sidecar.write_text(
        json.dumps(
            {
                "end_pc": TEXT_BASE + len(ADD2_BYTES),
                "entries": [
                    {"pc": TEXT_BASE, "file": "add2.c", "line": 3},
                    {"pc": TEXT_BASE + 4, "file": "add2.c", "line": 4},
                    {"pc": TEXT_BASE + 8, "file": "add2.c", "line": 5},
                ],
            }
        )
    )
    src = load_riscv_binary(p)
    assert src.line_table.lookup(TEXT_BASE).line == 3
    assert src.line_table.lookup(TEXT_BASE + 4).line == 4
    assert src.line_table.lookup(TEXT_BASE + 5).line == 4  # interpolated


def test_loader_rejects_non_riscv(tmp_path):
    # Force machine = 0 (no machine) by tweaking a header byte.
    data = bytearray(_build_fixture())
    # e_machine offset is 18 (sizeof e_ident=16 + sizeof e_type=2)
    data[18] = 0
    data[19] = 0
    p = tmp_path / "x.elf"
    p.write_bytes(bytes(data))
    with pytest.raises(ValueError):
        load_riscv_binary(p)


def test_instruction_words_iterates_byte_correctly():
    bin_ = RISCVBinary.from_bytes(_build_fixture())
    f = bin_.function("add2")
    words = list(bin_.instruction_words(f))
    assert len(words) == 3
    pcs = [w[0] for w in words]
    assert pcs == [TEXT_BASE, TEXT_BASE + 4, TEXT_BASE + 8]
    # All standard 32-bit (low two bits == 11).
    for _, _, length in words:
        assert length == 4


def test_rvc_instruction_detected_as_two_byte():
    # 0x0001 = c.nop: bottom two bits = 01, not 11, so 2-byte.
    text = b"\x01\x00" + b"\x13\x00\x00\x00"  # c.nop, addi x0, x0, 0
    funcs = [FuncDef(name="rvc", addr=TEXT_BASE, size=len(text))]
    elf = build_elf(text, TEXT_BASE, funcs)
    bin_ = RISCVBinary.from_bytes(elf)
    f = bin_.function("rvc")
    words = list(bin_.instruction_words(f))
    assert len(words) == 2
    # First is RVC (length 2)
    assert words[0][2] == 2
    # Second is 32-bit
    assert words[1][2] == 4


# ---------- _emit_dwarfmap.parse_decodedline ----------

# Sample output from `riscv64-unknown-elf-objdump --dwarf=decodedline`.
SAMPLE_DECODEDLINE = """
header trash that should be ignored

Contents of the .debug_line section:

CU: source.S:
File name                        Line number    Starting address    View    Stmt
source.S                                   5             0x10000               x
source.S                                   6             0x10002       1       x
source.S                                   7             0x10006       2       x
source.S                                   8             0x10008       3       x
source.S                                   -             0x1000a
"""


def test_parse_decodedline_extracts_pc_file_line_and_end_pc():
    import importlib.util, sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[4]
    src = repo / "bench" / "riscv-btor2" / "corpus" / "_emit_dwarfmap.py"
    spec = importlib.util.spec_from_file_location("_emit_dwarfmap", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_emit_dwarfmap"] = mod
    spec.loader.exec_module(mod)

    entries, end_pc = mod.parse_decodedline(SAMPLE_DECODEDLINE)
    assert end_pc == 0x1000A
    assert entries == [
        {"pc": "0x10000", "file": "source.S", "line": 5},
        {"pc": "0x10002", "file": "source.S", "line": 6},
        {"pc": "0x10006", "file": "source.S", "line": 7},
        {"pc": "0x10008", "file": "source.S", "line": 8},
    ]
