"""Engine adapters for the ``wasm-btor2`` pair.

Subprocess drivers for z3-bmc, z3-spacer, bitwuzla, cvc5, pono.
Likely copied from ``gurdy/pairs/riscv_btor2/solvers/`` on the
``v2-bootstrap`` branch since BTOR2 output is engine-agnostic.

Implementation begins at P6 (z3-bmc first) and continues through P9
(bitwuzla, cvc5, pono).
"""
