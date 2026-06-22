"""The shared WebAssembly language + interpreter (languages/wasm brief).

Registers the ``wasm`` language with its deterministic source interpreter,
reused by every Wasm pair (currently ``wasm-btor2``). Because the Wasm standard
is itself a small-step operational semantics, the interpreter mirrors it
rule-for-rule over the in-scope i32-stack core and can be checked against
WasmCert / the reference interpreter (an unusually strong source-side oracle).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from .interp import Instr, WasmModule, module, run

__all__ = ["run", "WasmModule", "Instr", "module"]

register_language(Language("wasm", source_interpreter=run))
