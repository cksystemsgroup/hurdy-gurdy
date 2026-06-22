"""The SMT-LIB reasoning language (languages/smtlib brief).

Registered so pairs targeting SMT-LIB (``btor2-smtlib`` and, later,
``crn-smtlib`` / ``python-smtlib``) can register. The deterministic interpreter
for SMT-LIB is **text I/O + model evaluation**, now built and shared from this
language (``sexpr`` / ``script`` / ``model`` / ``eval``): the byte-exact
s-expression reader/printer and a model evaluator over the ``QF_ABV`` and
``QF_LIA`` fragments. ``interpret`` is the shared target interpreter ``I_t``
(it runs one model); deciding over all models is the separate z3
``SolverBackend`` (SOLVERS.md). A pair targeting SMT-LIB reuses this evaluator
to check a ``sat`` witness rather than carrying its own.

Interpreter version (the shared deliverable's contract — AGENTS.md §3): a
versioned bump is required for any additive semantics change so dependent pairs
(``btor2-smtlib``, ``crn-smtlib``, and the registered ``python-smtlib``)
re-validate their square against this version.
- ``0.2`` — *additive* ``QF_LIA`` (linear integer arithmetic) arm of ``eval``:
  the ``Int`` sort over arbitrary-precision ``int``, integer literals, ``+`` /
  ``-`` / ``*`` / ``div`` / ``mod`` / ``abs``, ``<=`` / ``<`` / ``>=`` / ``>``,
  and the ``xor`` boolean connective (the rest of the boolean layer, ``=`` /
  ``distinct`` / ``ite`` were already shared). The ``QF_ABV`` path is unchanged.
- ``0.1`` — the ``QF_ABV`` / ``QF_BV`` bit-vector-and-array model evaluator
  (the ``btor2-smtlib`` bridge fragment).
"""

from __future__ import annotations

from ...core.registry import Language, Status, register_language
from .interp import interpret

INTERPRETER_VERSION = "0.2"  # AGENTS.md §3: bumped when the QF_LIA arm was added.

__all__ = ["interpret", "INTERPRETER_VERSION"]

register_language(
    Language("smtlib", target_interpreter=interpret, status=Status.PARTIAL)
)
