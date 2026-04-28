"""Build a minimal RV64 ELF programmatically.

Produces a 64-bit little-endian ELF for EM_RISCV with:

- one PT_LOAD segment containing the supplied instruction bytes
- a section table (.text, .symtab, .strtab, .shstrtab)
- one or more STT_FUNC symbols pointing into .text

This is enough for the loader to find functions, read instruction
bytes, and resolve symbols. Generated binaries don't run on real
hardware but exercise the parser's full path.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


# Replicated from elf.py to avoid coupling fixture builder to the
# prod parser's internals.
ELFCLASS64 = 2
ELFDATA2LSB = 1
ET_EXEC = 2
EM_RISCV = 243
EV_CURRENT = 1
PT_LOAD = 1
PF_X = 1
PF_W = 2
PF_R = 4
SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHF_ALLOC = 2
SHF_EXECINSTR = 4

STT_FUNC = 2
STB_GLOBAL = 1


_EHDR64 = struct.Struct("<16sHHIQQQIHHHHHH")
_PHDR64 = struct.Struct("<IIQQQQQQ")
_SHDR64 = struct.Struct("<IIQQQQIIQQ")
_SYM64 = struct.Struct("<IBBHQQ")


@dataclass(frozen=True)
class FuncDef:
    name: str
    addr: int
    size: int


def build_elf(
    text_bytes: bytes,
    text_vaddr: int,
    functions: list[FuncDef],
    entry: int | None = None,
) -> bytes:
    """Produce ELF bytes."""

    # ----- string tables -----
    # .shstrtab: section names
    section_names = ["", ".text", ".shstrtab", ".strtab", ".symtab"]
    shstrtab = b"\x00".join(s.encode() for s in section_names) + b"\x00"
    sh_name_offsets = {}
    cursor = 0
    for s in section_names:
        sh_name_offsets[s] = cursor
        cursor += len(s) + 1

    # .strtab: symbol names
    sym_names = ["", *(f.name for f in functions)]
    strtab = b"\x00".join(s.encode() for s in sym_names) + b"\x00"
    str_offsets = {}
    cursor = 0
    for s in sym_names:
        str_offsets[s] = cursor
        cursor += len(s) + 1

    # ----- layout: header | program headers | text | strtab | shstrtab | symtab | section headers -----
    ehdr_size = _EHDR64.size
    phdr_size = _PHDR64.size
    shdr_size = _SHDR64.size
    sym_size = _SYM64.size

    num_phdrs = 1
    num_shdrs = 5  # null, text, shstrtab, strtab, symtab

    offset = ehdr_size + num_phdrs * phdr_size
    text_offset = offset
    offset += len(text_bytes)
    strtab_offset = offset
    offset += len(strtab)
    shstrtab_offset = offset
    offset += len(shstrtab)
    symtab_offset = offset
    # 1 null sym + N function syms
    symtab_size = (1 + len(functions)) * sym_size
    offset += symtab_size
    sh_table_offset = offset

    # ----- ELF header -----
    e_ident = bytes(
        [
            0x7F,
            ord("E"),
            ord("L"),
            ord("F"),
            ELFCLASS64,
            ELFDATA2LSB,
            EV_CURRENT,
            0,  # OSABI
            0,  # ABIVERSION
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ]
    )
    out = bytearray()
    out += _EHDR64.pack(
        e_ident,
        ET_EXEC,
        EM_RISCV,
        EV_CURRENT,
        entry if entry is not None else (functions[0].addr if functions else text_vaddr),
        ehdr_size,  # e_phoff
        sh_table_offset,
        0,  # e_flags
        ehdr_size,  # e_ehsize
        phdr_size,
        num_phdrs,
        shdr_size,
        num_shdrs,
        2,  # e_shstrndx -> .shstrtab is the 3rd section (index 2)
    )

    # ----- program header (one PT_LOAD covering text) -----
    out += _PHDR64.pack(
        PT_LOAD,
        PF_R | PF_X,
        text_offset,
        text_vaddr,
        text_vaddr,
        len(text_bytes),
        len(text_bytes),
        0x1000,  # alignment
    )

    # ----- text body -----
    out += text_bytes

    # ----- .strtab body -----
    out += strtab

    # ----- .shstrtab body -----
    out += shstrtab

    # ----- .symtab body -----
    # 0: null
    out += _SYM64.pack(0, 0, 0, 0, 0, 0)
    for f in functions:
        st_info = (STB_GLOBAL << 4) | STT_FUNC
        out += _SYM64.pack(
            str_offsets[f.name],
            st_info,
            0,
            1,  # st_shndx = .text
            f.addr,
            f.size,
        )

    # ----- section headers -----
    # 0: null
    out += _SHDR64.pack(0, SHT_NULL, 0, 0, 0, 0, 0, 0, 0, 0)
    # 1: .text
    out += _SHDR64.pack(
        sh_name_offsets[".text"],
        SHT_PROGBITS,
        SHF_ALLOC | SHF_EXECINSTR,
        text_vaddr,
        text_offset,
        len(text_bytes),
        0,
        0,
        2,
        0,
    )
    # 2: .shstrtab
    out += _SHDR64.pack(
        sh_name_offsets[".shstrtab"],
        SHT_STRTAB,
        0,
        0,
        shstrtab_offset,
        len(shstrtab),
        0,
        0,
        1,
        0,
    )
    # 3: .strtab
    out += _SHDR64.pack(
        sh_name_offsets[".strtab"],
        SHT_STRTAB,
        0,
        0,
        strtab_offset,
        len(strtab),
        0,
        0,
        1,
        0,
    )
    # 4: .symtab (sh_link -> .strtab @ index 3)
    out += _SHDR64.pack(
        sh_name_offsets[".symtab"],
        SHT_SYMTAB,
        0,
        0,
        symtab_offset,
        symtab_size,
        3,  # link -> strtab
        1,  # info: index of first non-local symbol (we put one local null then globals)
        8,
        sym_size,
    )

    return bytes(out)
