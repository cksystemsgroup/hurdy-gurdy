"""The SMT-LIB reasoning language (languages/smtlib brief).

Registered so pairs targeting SMT-LIB (``btor2-smtlib`` and, later,
``crn-smtlib`` / ``python-smtlib``) can register. The deterministic
interpreter for SMT-LIB is text I/O + model evaluation; deciding is the z3
``SolverBackend`` (SOLVERS.md). MVP-1 registers the language; a generic
model-evaluation interpreter is a later increment, so the interpreter slots
are left unset and each pair supplies its own witness decoding.
"""

from __future__ import annotations

from ...core.registry import Language, register_language

register_language(Language("smtlib"))
