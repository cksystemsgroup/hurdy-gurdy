"""Tests for AArch64 ELF parser and source loader."""

from __future__ import annotations

import pytest

from gurdy.pairs.aarch64_btor2.source.elf import EM_AARCH64, ELFParseError, parse_elf
from gurdy.pairs.aarch64_btor2.source.loader import load_aarch64_binary
from tests.fixtures.elf_builder_aarch64 import FuncDef, build_elf

TEXT_BASE = 0x400000
# NOP (A64): 0xD503201F
_NOP = bytes.fromhex("1F2003D5")
# RET x30: 0xD65F03C0
_RET = bytes.fromhex("C0035FD6")


def _simple_elf():
    code = _NOP + _RET
    return build_elf(code, TEXT_BASE, [FuncDef("main", TEXT_BASE, len(code))])


def test_parse_elf_aarch64():
    data = _simple_elf()
    elf = parse_elf(data)
    assert elf.header.machine == EM_AARCH64


def test_load_aarch64_binary(tmp_path):
    p = tmp_path / "test.elf"
    p.write_bytes(_simple_elf())
    src = load_aarch64_binary(p)
    assert src.is_aarch64
    fn = src.function("main")
    assert fn is not None
    assert fn.start == TEXT_BASE
    assert fn.end == TEXT_BASE + 8


def test_load_rejects_non_aarch64():
    # Build an ELF with wrong machine
    import struct
    data = bytearray(_simple_elf())
    # Patch e_machine at offset 18 (2 bytes LE): set to EM_RISCV=243
    struct.pack_into("<H", data, 18, 243)
    with pytest.raises(ValueError, match="EM_AARCH64"):
        load_aarch64_binary(bytes(data))


def test_instruction_words_fixed_4_bytes():
    code = _NOP + _RET
    elf_bytes = build_elf(code, TEXT_BASE, [FuncDef("main", TEXT_BASE, len(code))])
    from gurdy.pairs.aarch64_btor2.source.elf import AArch64Binary
    binary = AArch64Binary.from_bytes(elf_bytes)
    fn = binary.function("main")
    words = list(binary.instruction_words(fn))
    assert len(words) == 2
    assert words[0] == (TEXT_BASE, 0xD503201F)      # NOP
    assert words[1] == (TEXT_BASE + 4, 0xD65F03C0)  # RET
