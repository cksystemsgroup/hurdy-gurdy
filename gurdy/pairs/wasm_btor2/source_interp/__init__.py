"""WebAssembly concrete executor.

Stack machine + locals + globals + linear memory + function tables.
Implements ``run(source, binding, max_steps) -> SourceTrace`` and a shadow
mode that records per-instruction state cell reads/writes for the alignment
oracle.  See ``V2_BOOTSTRAP.md`` §3.1.
"""

from gurdy.pairs.wasm_btor2.source_interp.bindings import (
    FREE,
    Free,
    FreeFieldNotAllowed,
    WasmInputBinding,
)
from gurdy.pairs.wasm_btor2.source_interp.interpreter import (
    INTERPRETER_VERSION,
    PAIR_ID,
    WasmSourceInterpreter,
)

__all__ = [
    "FREE",
    "Free",
    "FreeFieldNotAllowed",
    "INTERPRETER_VERSION",
    "PAIR_ID",
    "WasmInputBinding",
    "WasmSourceInterpreter",
]
