"""The ``Language`` descriptor and registry.

A language is admissible iff it has a *formal semantics* — a definable
meaning function. A language needs **oracle-grade** semantics only to sit on
a *source* edge; on a *reasoning* edge it needs only precise semantics plus a
sound decision procedure. The obligation attaches to the edge position, not
the language (see ``ARCHITECTURE.md``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

KINDS = ("input", "representation", "reasoning")


@dataclass(frozen=True)
class Language:
    """A formal language usable as a hop endpoint.

    ``kind``:
      - ``input`` — a subject under study (a C program, a binary, ...);
      - ``representation`` — an execution target (rv64 ELF, ...);
      - ``reasoning`` — a logic where a solver lives (BTOR2, SMT-LIB).

    ``semantics`` is a one-line note; ``reasons_via`` names the decision
    procedures that consume a reasoning language (empty otherwise).
    """

    id: str
    kind: str
    semantics: str = ""
    reasons_via: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {self.kind!r}")


# The languages the three example hops span. Registered here for
# introspection; route enumeration works off hop endpoint strings directly.
LANGUAGES: dict[str, Language] = {
    "c": Language("c", "input", semantics="Cerberus C abstract machine"),
    "rv64-elf": Language("rv64-elf", "representation", semantics="Sail-RISCV (rv64)"),
    "btor2": Language(
        "btor2", "reasoning",
        semantics="bit-level word transition system",
        reasons_via=("bitwuzla", "z3-bmc", "pono"),
    ),
    "smt-lib": Language(
        "smt-lib", "reasoning",
        semantics="many-sorted FO theories (QF_BV, arrays)",
        reasons_via=("z3", "cvc5", "bitwuzla"),
    ),
}


def get(lang_id: str) -> Language | None:
    return LANGUAGES.get(lang_id)
