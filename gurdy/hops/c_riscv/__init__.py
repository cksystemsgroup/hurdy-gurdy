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
from gurdy.hops.c_riscv.verify import (
    CbmcProvenance,
    CbmcResult,
    CbmcVerifyError,
    cbmc_verify,
    classify_differential,
    parse_cbmc_verdict,
    to_cbmc_dialect,
)

__all__ = [
    "CCompileResult",
    "CbmcProvenance",
    "CbmcResult",
    "CbmcVerifyError",
    "CompileError",
    "LineEntry",
    "LineMapError",
    "Provenance",
    "ToolchainUnavailable",
    "ToolchainPin",
    "cbmc_verify",
    "classify_differential",
    "compile_c",
    "default_pin",
    "extract_line_map",
    "parse_cbmc_verdict",
    "parse_decodedline",
    "to_cbmc_dialect",
    "toolchain_available",
]
