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
- ``0.4`` — adds the **BMC-bounded loop** ``while <cond>: <body>`` (the guard run
  through CPython, the body run while it holds, capped at the BMC bound
  ``WHILE_BOUND`` so an unbounded loop can never hang ``I_s``; body-only names
  dropped after the loop). Additive: every ``0.3`` program is accepted and executes
  identically.
- ``0.5`` — adds **nested loops**: a ``for`` / ``while`` may appear inside another
  loop's body (and inside an ``if`` arm inside a loop), within the fixed nesting
  caps ``MAX_LOOP_DEPTH`` / ``MAX_UNROLL_PRODUCT`` (a loop nested too deep or whose
  unrolled product would exceed the cap hard-aborts ``nesting-too-deep``). CPython
  already runs nested loops, so the executor change is *only* the loader admitting
  them; the ``WHILE_BOUND`` replay cap keeps ``I_s`` total at every level. Additive:
  every ``0.4`` program is accepted and executes identically (the existing
  single-loop traces are byte-unchanged).
- ``0.6`` — adds **fixed-length integer lists**: a list literal ``[e0, …, e{L-1}]``
  of statically-known length ``L`` (bounded by ``MAX_LIST_LEN`` = 16), a constant /
  dynamic index **read** ``xs[i]`` and **write** ``xs[i] = v``, and ``len(xs)``.
  CPython runs the real list natively (a list literal builds it, ``xs[i] = v``
  mutates it in place); the executor change is the loader admitting the list AST
  nodes plus exposing the single builtin ``len`` and snapshotting list values by
  copy in each trace row. An out-of-range index is recorded as a *defined error*
  (``I_s`` stays total). Additive: every ``0.5`` program is accepted and executes
  identically (the existing int-only traces are byte-unchanged — lists are new
  names only).

The pair over this language (``python-smtlib``) is the only dependent and is
re-validated against this version by its commuting-square tests.
"""

from __future__ import annotations

from ...core.registry import Language, Status, register_language
from .eval import PYTHON_PIN, interpret, run
from .subset import Program, load

INTERPRETER_VERSION = "0.6"

__all__ = ["interpret", "run", "load", "Program", "PYTHON_PIN", "INTERPRETER_VERSION"]

register_language(
    Language("python", source_interpreter=interpret, status=Status.PARTIAL)
)
