"""Engine adapters for the ``wasm-btor2`` pair.

P7: z3-bmc in-process adapter.  Subsequent phases add z3-spacer,
bitwuzla, cvc5, and pono adapters.
"""

from gurdy.pairs.wasm_btor2.solvers.z3bmc import Z3BMCSolver
from gurdy.pairs.wasm_btor2.solvers._bmc import Compiled, compile_btor2
from gurdy.pairs.wasm_btor2.solvers.btor2_to_z3 import Z3Backend, bmc

__all__ = ["Z3BMCSolver", "Compiled", "compile_btor2", "Z3Backend", "bmc"]
