"""The shared Python-subset language + source interpreter (languages/python
brief).

Registers ``python`` with its deterministic source interpreter ``I_s`` — **pinned
real CPython restricted to the subset** (``eval.interpret``) — shared by every
Python pair (today only ``python-smtlib``). The loader (``subset.load``) enforces
the subset by rejecting any out-of-subset AST node with a typed
``unsupported: python:<construct>`` (no silent drop), and the accepted program
runs under the host CPython in a restricted namespace (no imports / no I/O),
producing a ``Trace`` of post-step environment states (ARCHITECTURE.md §§5-6).

Not an ISA — no Sail model; CPython *is* the de-facto semantics, so it is the
oracle the source side is ``checked`` against (the high-level analogue of an ISA
differential — languages/python brief).

Interpreter version (the shared deliverable's contract — AGENTS.md §3). Bumps
are **additive** — the allow-list only ever grows (the coverage ratchet), so a
program accepted at an earlier version is still accepted and executes identically:
- ``0.1`` — the straight-line integer subset (assignment + linear arithmetic +
  one trailing assert) executed by pinned CPython in a restricted namespace.
- ``0.2`` — adds ``if`` / ``else`` (the guard evaluated through CPython, only the
  taken arm executed). Additive: every ``0.1`` program is unchanged.
- ``0.3`` — adds the **bounded loop** ``for i in range(<const>)`` (the body run
  once per ``i = 0..n-1`` through CPython, the loop variable dropped after the
  loop). Additive: every ``0.2`` program is accepted and executes identically.

The pair over this language (``python-smtlib``) is the only dependent and is
re-validated against this version by its commuting-square tests.
"""

from __future__ import annotations

from ...core.registry import Language, Status, register_language
from .eval import PYTHON_PIN, interpret, run
from .subset import Program, load

INTERPRETER_VERSION = "0.3"

__all__ = ["interpret", "run", "load", "Program", "PYTHON_PIN", "INTERPRETER_VERSION"]

register_language(
    Language("python", source_interpreter=interpret, status=Status.PARTIAL)
)
