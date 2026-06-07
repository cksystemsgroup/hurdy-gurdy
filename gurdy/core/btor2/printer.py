"""BTOR2 text printer.

Canonical output rules:

- One entry per line; no trailing whitespace.
- Tokens separated by single spaces.
- Inline comments preserved as ``  ; <text>`` (two spaces + ``; ``).
- Blank lines preserved as empty.
- Standalone comments printed as ``; <text>``.
"""

from __future__ import annotations

from gurdy.core.btor2.nodes import (
    ArraySort,
    BitvecSort,
    Comment,
    LineEntry,
    Model,
    Node,
)


def _node_to_text(n: Node) -> str:
    parts = [str(n.nid), n.op]
    if n.op == "sort" and n.sort is not None:
        parts.extend(n.sort.to_args())
    else:
        parts.extend(n.args)
    if n.symbol:
        parts.append(n.symbol)
    line = " ".join(parts)
    if n.inline_comment:
        line += "  ; " + n.inline_comment
    return line


def _entry_to_text(e: LineEntry) -> str:
    if isinstance(e, Node):
        return _node_to_text(e)
    if e.is_blank():
        return ""
    return "; " + e.text


def to_text(model: Model) -> str:
    return "\n".join(_entry_to_text(e) for e in model.entries) + "\n"


def to_bytes(model: Model) -> bytes:
    return to_text(model).encode("utf-8")


__all__ = ["to_text", "to_bytes"]
