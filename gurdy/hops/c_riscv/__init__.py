"""``c-riscv``: reproducible C -> RV64 ELF compile hop (hop 1 of the
C -> RV64 ELF -> BTOR2 chain). See ``CONTRACT.md``.

This is a **compile pair** (``DESIGN_pair_taxonomy.md``): its ``out_lang`` is a
representation (RV64 ELF), not a reasoning language, so it carries no lifter or
solvers. Importing this module registers it as a :class:`CompileHop` in the
unified hop registry, so it appears as the ``c -> rv64-elf`` edge of the
language graph alongside the ``rv64-elf -> btor2`` reasoning pair.
"""

from pathlib import Path

from gurdy.core.hop import CompileHop, Tier, register_hop
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


# The hop as a registered graph edge. ``compile`` is the hop's translation
# callable; its signature is hop-specific (compile pairs do not yet share a
# uniform translate signature with reasoning pairs — see DESIGN_pair_taxonomy).
C_RISCV = CompileHop(
    identifier="c-riscv",
    in_lang="c",
    out_lang="rv64-elf",
    tier=Tier.reproducible,
    compile=compile_c,
    contract_path=Path(__file__).parent / "CONTRACT.md",
)

register_hop(C_RISCV)


__all__ = [
    "C_RISCV",
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
