"""BTOR2 text parser.

The parser is permissive: it accepts the HWMCC superset by treating
unknown opcodes as plain ``Node`` records with raw arg tokens. It
reports diagnostics for malformed lines but never raises — the caller
inspects diagnostics to decide.

Round-trip property: any model produced by ``to_text`` parses back to
an identical model. We achieve that by preserving comments (standalone
and inline) and by keeping arg tokens as strings.

Copied from ``gurdy.pairs.riscv_btor2.btor2.parser`` at
INTERPRETER_VERSION 1.1.0 per V2_BOOTSTRAP.md §3.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gurdy.core.diagnostics import Diagnostic, Severity
from gurdy.pairs.wasm_btor2.btor2.nodes import (
    ArraySort,
    BitvecSort,
    Comment,
    Model,
    Node,
)


@dataclass
class ParseResult:
    model: Model
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def has_errors(self) -> bool:
        return any(d.is_error() for d in self.diagnostics)


# Recognized "binding" ops whose last token is a symbol name rather
# than a numeric arg. We keep a conservative list — others fall back
# to "no symbol" and store the token in args (round-trip is preserved
# either way; this is just for nicer access).
_SYMBOLIC_OPS = frozenset(
    {
        "state",
        "input",
    }
)


def _split_inline_comment(line: str) -> tuple[str, str]:
    """Split off a trailing ``;`` comment. Returns ``(payload, comment)``."""
    if ";" not in line:
        return line.rstrip(), ""
    idx = line.find(";")
    payload = line[:idx].rstrip()
    rest = line[idx + 1 :]
    if rest.startswith(" "):
        rest = rest[1:]
    return payload, rest


def from_text(text: str) -> ParseResult:
    result = ParseResult(model=Model())
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            result.model.append(Comment(text=""))
            continue
        if stripped.startswith(";"):
            comment_text = stripped[1:]
            if comment_text.startswith(" "):
                comment_text = comment_text[1:]
            result.model.append(Comment(text=comment_text))
            continue
        payload, inline = _split_inline_comment(raw)
        tokens = payload.split()
        if not tokens:
            result.model.append(Comment(text=""))
            continue
        try:
            nid = int(tokens[0])
        except ValueError:
            result.diagnostics.append(
                Diagnostic(
                    Severity.ERROR,
                    "btor2/parse/0001",
                    f"line does not start with an integer nid: {raw!r}",
                    location=f"line {lineno}",
                )
            )
            continue
        if len(tokens) < 2:
            result.diagnostics.append(
                Diagnostic(
                    Severity.ERROR,
                    "btor2/parse/0002",
                    f"line has nid but no opcode: {raw!r}",
                    location=f"line {lineno}",
                )
            )
            continue
        op = tokens[1]
        rest = tokens[2:]

        node = Node(nid=nid, op=op, args=[], inline_comment=inline)

        if op == "sort":
            _parse_sort(node, rest, lineno, result.diagnostics)
        else:
            symbol = None
            if op in _SYMBOLIC_OPS and rest and not _looks_like_int(rest[-1]):
                symbol = rest[-1]
                rest = rest[:-1]
            elif rest and not _looks_like_int(rest[-1]) and op not in {"const", "constd", "consth"}:
                symbol = rest[-1]
                rest = rest[:-1]
            node.args = list(rest)
            node.symbol = symbol

        result.model.append(node)
    return result


def _parse_sort(node: Node, rest: list[str], lineno: int, diags: list[Diagnostic]) -> None:
    if not rest:
        diags.append(
            Diagnostic(
                Severity.ERROR,
                "btor2/parse/0010",
                f"sort declaration missing kind on line {lineno}",
                location=f"line {lineno}",
            )
        )
        return
    kind = rest[0]
    if kind == "bitvec":
        if len(rest) < 2:
            diags.append(
                Diagnostic(
                    Severity.ERROR,
                    "btor2/parse/0011",
                    "bitvec sort missing width",
                    location=f"line {lineno}",
                )
            )
            return
        try:
            width = int(rest[1])
        except ValueError:
            diags.append(
                Diagnostic(
                    Severity.ERROR,
                    "btor2/parse/0012",
                    f"bitvec sort width is not an integer: {rest[1]!r}",
                    location=f"line {lineno}",
                )
            )
            return
        node.sort = BitvecSort(width=width)
        node.args = []  # canonical: sort args carried in node.sort
        if len(rest) > 2:
            node.symbol = rest[2]
        return
    if kind == "array":
        if len(rest) < 3:
            diags.append(
                Diagnostic(
                    Severity.ERROR,
                    "btor2/parse/0013",
                    "array sort needs index and element sort nids",
                    location=f"line {lineno}",
                )
            )
            return
        try:
            idx = int(rest[1])
            elt = int(rest[2])
        except ValueError:
            diags.append(
                Diagnostic(
                    Severity.ERROR,
                    "btor2/parse/0014",
                    "array sort index/element must be integers",
                    location=f"line {lineno}",
                )
            )
            return
        node.sort = ArraySort(index_sort_nid=idx, element_sort_nid=elt)
        node.args = []
        if len(rest) > 3:
            node.symbol = rest[3]
        return
    diags.append(
        Diagnostic(
            Severity.ERROR,
            "btor2/parse/0015",
            f"unknown sort kind {kind!r}",
            location=f"line {lineno}",
        )
    )


def _looks_like_int(tok: str) -> bool:
    if not tok:
        return False
    if tok[0] in "+-":
        tok = tok[1:]
    return tok.isdigit()


__all__ = ["ParseResult", "from_text"]
