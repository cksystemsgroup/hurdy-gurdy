"""BTOR2 in-memory model.

This module is intentionally domain-free: it knows BTOR2 surface
syntax and nothing about EVM or any specific encoding. Its role is
to be a faithful AST that round-trips to text byte-for-byte (modulo
trailing whitespace) and lets the translator construct nodes
programmatically.

A BTOR2 file is a sequence of lines. Each non-empty, non-comment line
introduces one node with an integer ``nid`` and an opcode. Comments
(``;`` to end-of-line) and blank lines are preserved as ``Comment``
records so the printer can reproduce them in place.

We represent every entry as ``LineEntry``; ``Node`` is the subset
that has a numeric ``nid``. A ``Model`` is just an ordered list of
``LineEntry``.

We do not model BTOR2 semantics here — args are stored as raw token
strings (``str``) so we can support the HWMCC superset without
encoding every operator's signature; a strict validator can layer on
top.

Verbatim copy of riscv-btor2/btor2/nodes.py; imports are local.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Sort
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BitvecSort:
    width: int

    def to_args(self) -> list[str]:
        return ["bitvec", str(self.width)]


@dataclass(frozen=True)
class ArraySort:
    index_sort_nid: int
    element_sort_nid: int

    def to_args(self) -> list[str]:
        return ["array", str(self.index_sort_nid), str(self.element_sort_nid)]


SortKind = BitvecSort | ArraySort


# ---------------------------------------------------------------------------
# Line entries
# ---------------------------------------------------------------------------


@dataclass
class Comment:
    """A standalone comment line or blank line."""

    text: str = ""

    def is_blank(self) -> bool:
        return self.text == ""

    def is_node(self) -> bool:
        return False


@dataclass
class Node:
    """A single BTOR2 node."""

    nid: int
    op: str
    args: list[str] = field(default_factory=list)
    symbol: str | None = None
    inline_comment: str = ""
    sort: SortKind | None = None

    def is_node(self) -> bool:
        return True

    def is_sort(self) -> bool:
        return self.op == "sort"

    def is_state(self) -> bool:
        return self.op == "state"

    def is_input(self) -> bool:
        return self.op == "input"

    def is_init(self) -> bool:
        return self.op == "init"

    def is_next(self) -> bool:
        return self.op == "next"

    def is_bad(self) -> bool:
        return self.op == "bad"

    def is_constraint(self) -> bool:
        return self.op == "constraint"


LineEntry = Node | Comment


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclass
class Model:
    """An ordered sequence of entries forming a BTOR2 file."""

    entries: list[LineEntry] = field(default_factory=list)

    def append(self, entry: LineEntry) -> LineEntry:
        self.entries.append(entry)
        return entry

    def extend(self, entries: Iterable[LineEntry]) -> None:
        for e in entries:
            self.append(e)

    def nodes(self) -> list[Node]:
        return [e for e in self.entries if isinstance(e, Node)]

    def by_nid(self, nid: int) -> Node | None:
        for e in self.entries:
            if isinstance(e, Node) and e.nid == nid:
                return e
        return None

    def next_nid(self) -> int:
        max_nid = 0
        for e in self.entries:
            if isinstance(e, Node) and e.nid > max_nid:
                max_nid = e.nid
        return max_nid + 1


__all__ = [
    "BitvecSort",
    "ArraySort",
    "SortKind",
    "Comment",
    "Node",
    "LineEntry",
    "Model",
]
