"""The shared SMT solver inventory (SOLVERS.md §8 — "enumerate solvers,
decide"). The framework *lists* the registered backends and filters to those
present; it never picks one or races a portfolio — the player (or a corroboration
step) does that (SOLVERS.md §3 "enumerate, don't choose").

Registered, in a stable dispatch order: **z3**, **bitwuzla**, **boolector**,
**cvc5**, **yices2**. z3 and bitwuzla are wired and host-validated; boolector is
host-validated too (shares lineage with bitwuzla — see ``smt_cli``); cvc5 and
yices2 are thin gated adapters that activate when their pinned binary is present
(DOCKER.md). A new engine is one entry here plus a backend class.
"""

from __future__ import annotations

from typing import Any


def _z3() -> Any | None:
    try:
        from .z3_smt import Z3SmtBackend
        return Z3SmtBackend()
    except Exception:
        return None


def _bitwuzla() -> Any | None:
    from .bitwuzla_smt import BitwuzlaSmtBackend
    return BitwuzlaSmtBackend()


def _cli(cls_name: str) -> Any | None:
    from . import smt_cli
    return getattr(smt_cli, cls_name)()


def smt_backends() -> list:
    """Every registered SMT backend, constructed, in dispatch order. Backends
    whose construction fails (e.g. z3's Python module absent) are omitted."""
    out = []
    out.append(_z3())
    out.append(_bitwuzla())
    for name in ("BoolectorSmtBackend", "Cvc5SmtBackend", "Yices2SmtBackend"):
        out.append(_cli(name))
    return [b for b in out if b is not None]


def is_available(backend: Any) -> bool:
    """Uniform availability check across backends with and without ``available``
    (z3's adapter raises on construction if absent, so once built it is present)."""
    try:
        return backend.available() if hasattr(backend, "available") else True
    except Exception:
        return False


def available_smt_backends() -> list:
    """The registered SMT backends whose binary/module is actually present."""
    return [b for b in smt_backends() if is_available(b)]
