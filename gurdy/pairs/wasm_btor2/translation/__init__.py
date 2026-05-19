"""WebAssembly → BTOR2 translator.

Deterministic, schema-pinned. Layered artifact (header / machine /
library / dispatch / init / constraint / bad / binding).
See ``V2_BOOTSTRAP.md`` §3.3.

P4 scope: single-function WASM modules with i32 arithmetic (add, sub,
const, mul), local.get/set/tee, drop, return, unreachable, and the
function-level end. ``reach_trap`` property only; ``LocalInit``
assumptions supported.
"""

from gurdy.pairs.wasm_btor2.translation.translate import (
    SCHEMA_VERSION,
    TRANSLATOR_VERSION,
    Translator,
    translate,
)

__all__ = ["Translator", "translate", "TRANSLATOR_VERSION", "SCHEMA_VERSION"]
