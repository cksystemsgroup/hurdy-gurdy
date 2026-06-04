"""``c-riscv``: reproducible C -> RV64 ELF compile hop (hop 1 of the
C -> RV64 ELF -> BTOR2 chain). See ``CONTRACT.md``.
"""

from gurdy.hops.c_riscv.compile import (
    CCompileResult,
    CompileError,
    Provenance,
    ToolchainUnavailable,
    compile_c,
    toolchain_available,
)
from gurdy.hops.c_riscv.dwarf import (
    LineEntry,
    LineMapError,
    extract_line_map,
    parse_decodedline,
)
from gurdy.hops.c_riscv.toolchain import ToolchainPin, default_pin

__all__ = [
    "CCompileResult",
    "CompileError",
    "LineEntry",
    "LineMapError",
    "Provenance",
    "ToolchainUnavailable",
    "ToolchainPin",
    "compile_c",
    "default_pin",
    "extract_line_map",
    "parse_decodedline",
    "toolchain_available",
]
