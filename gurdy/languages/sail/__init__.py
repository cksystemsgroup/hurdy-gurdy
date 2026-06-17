"""The shared Sail language + interpreter (languages/sail brief).

Registers ``sail`` with the independent RISC-V executor built on the
Sail-derived ``Expr`` semantics (``rv64.EXEC``). Source of ``riscv-sail`` and
consumed by ``sail-btor2``.
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from . import expr, rv64  # noqa: F401  (the semantic encoding)
from .interp import run

__all__ = ["run", "expr", "rv64"]

register_language(Language("sail", source_interpreter=run))
