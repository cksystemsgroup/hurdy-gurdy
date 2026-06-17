"""The SMT-LIB reasoning language (languages/smtlib brief).

Registered so pairs targeting SMT-LIB (``btor2-smtlib`` and, later,
``crn-smtlib`` / ``python-smtlib``) can register. The deterministic interpreter
for SMT-LIB is **text I/O + model evaluation**, now built and shared from this
language (``sexpr`` / ``script`` / ``model`` / ``eval``): the byte-exact
s-expression reader/printer and a model evaluator over the ``QF_ABV`` fragment.
``interpret`` is the shared target interpreter ``I_t`` (it runs one model);
deciding over all models is the separate z3 ``SolverBackend`` (SOLVERS.md). A
pair targeting SMT-LIB reuses this evaluator to check a ``sat`` witness rather
than carrying its own.
"""

from __future__ import annotations

from ...core.registry import Language, Status, register_language
from .interp import interpret

register_language(
    Language("smtlib", target_interpreter=interpret, status=Status.PARTIAL)
)
