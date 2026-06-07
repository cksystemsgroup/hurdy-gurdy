"""WebAssembly module loader and instruction decoder.

``WasmSource`` wraps a decoded ``WasmModule`` and exposes the accessors
that the translator and source interpreter need: ``export()``,
``function()``, ``globals_info()``, and ``memory_info()``.

``load_wasm_source(payload)`` accepts a file path (str or Path) or raw
bytes and returns a ``WasmSource``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from gurdy.pairs.wasm_btor2.source.decoder import (
    CodeEntry,
    Export,
    FuncType,
    Global,
    KIND_FUNC,
    MemType,
    WasmDecodeError,
    WasmModule,
    WasmTrap,
    decode_module,
)


@dataclass
class WasmSource:
    """The pair's source type — wraps a decoded ``WasmModule``.

    All indices follow the WASM module-level convention: import functions
    occupy indices 0..N_imports-1; local (non-import) functions follow.
    """

    module: WasmModule
    content_hash: str | None = None   # SHA-256 hex of raw binary, if known

    # -----------------------------------------------------------------
    # Export lookup
    # -----------------------------------------------------------------

    def export(self, name: str) -> Export | None:
        """Return the ``Export`` record for *name*, or ``None``."""
        for ex in self.module.exports:
            if ex.name == name:
                return ex
        return None

    def export_func_idx(self, name: str) -> int | None:
        """Return the function index for an exported function, or ``None``."""
        ex = self.export(name)
        if ex is None or ex.kind != KIND_FUNC:
            return None
        return ex.index

    # -----------------------------------------------------------------
    # Function info
    # -----------------------------------------------------------------

    def func_type(self, func_idx: int) -> FuncType | None:
        return self.module.func_type(func_idx)

    def code_entry(self, func_idx: int) -> CodeEntry | None:
        """Return the ``CodeEntry`` for a local function, or ``None`` for imports."""
        n_imp = self.module.import_func_count
        if func_idx < n_imp:
            return None  # import — no code
        local_idx = func_idx - n_imp
        if local_idx >= len(self.module.codes):
            return None
        return self.module.codes[local_idx]

    def is_import(self, func_idx: int) -> bool:
        return func_idx < self.module.import_func_count

    @property
    def total_func_count(self) -> int:
        return self.module.total_func_count

    # -----------------------------------------------------------------
    # Globals / memory
    # -----------------------------------------------------------------

    def globals_info(self) -> list[Global]:
        return list(self.module.globals)

    def memory_info(self) -> MemType | None:
        return self.module.memories[0] if self.module.memories else None

    # -----------------------------------------------------------------
    # Import resolution
    # -----------------------------------------------------------------

    def import_funcs(self) -> list[tuple[str, str, int]]:
        """Return ``(module_name, field_name, type_idx)`` for every func import."""
        result = []
        for imp in self.module.imports:
            if imp.kind == KIND_FUNC:
                result.append((imp.module, imp.name, imp.type_idx))
        return result


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_wasm_source(payload: bytes | str | Path) -> "WasmSource":
    """Load a WASM module from raw bytes or a file path.

    Returns a ``WasmSource`` with ``content_hash`` set to the SHA-256 of
    the raw bytes.

    Raises ``WasmDecodeError`` on format violations.
    """
    if isinstance(payload, (str, Path)):
        raw = Path(payload).read_bytes()
    elif isinstance(payload, (bytes, bytearray)):
        raw = bytes(payload)
    else:
        raise ValueError(f"load_wasm_source: unsupported payload type {type(payload)!r}")
    digest = hashlib.sha256(raw).hexdigest()
    mod = decode_module(raw)
    return WasmSource(module=mod, content_hash=digest)


__all__ = [
    "WasmSource",
    "load_wasm_source",
    # Re-export for convenience
    "WasmDecodeError",
    "WasmTrap",
]
