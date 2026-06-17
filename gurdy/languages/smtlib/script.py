"""SMT-LIB scripts: read the command list, expose declares / defines / asserts,
and re-print byte-exactly (languages/smtlib brief — text I/O before evaluation).

A ``Script`` is just the ordered list of top-level commands (parsed
s-expressions). The accessors below pick out the pieces the model evaluator
(eval.py) needs from the ``QF_ABV`` / ``QF_BV`` fragment the ``btor2-smtlib``
bridge emits: nullary ``declare-fun`` constants, nullary ``define-fun`` macros,
and ``assert`` bodies.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import sexpr


@dataclass(frozen=True)
class Script:
    commands: tuple  # each command is a parsed s-expression (str | list)

    def to_text(self) -> str:
        """Byte-exact for the canonical one-command-per-line form (sexpr.py)."""
        return "\n".join(sexpr.dumps(c) for c in self.commands) + "\n"

    @property
    def logic(self) -> str | None:
        for c in self.commands:
            if isinstance(c, list) and c and c[0] == "set-logic":
                return c[1]
        return None

    def declares(self) -> dict:
        """``name -> sort`` for nullary ``declare-fun`` / ``declare-const``."""
        out: dict = {}
        for c in self.commands:
            if not isinstance(c, list) or not c:
                continue
            if c[0] == "declare-fun" and c[2] == []:
                out[c[1]] = c[3]
            elif c[0] == "declare-const":
                out[c[1]] = c[2]
        return out

    def defines(self) -> list:
        """``[(name, sort, body), ...]`` for nullary ``define-fun``, in order."""
        return [(c[1], c[3], c[4]) for c in self.commands
                if isinstance(c, list) and c and c[0] == "define-fun" and c[2] == []]

    def assertions(self) -> list:
        """The body term of each ``assert``, in order."""
        return [c[1] for c in self.commands
                if isinstance(c, list) and c and c[0] == "assert"]


def read_script(text: str | bytes) -> Script:
    s = text.decode("utf-8") if isinstance(text, (bytes, bytearray)) else text
    return Script(tuple(sexpr.parse(s)))
