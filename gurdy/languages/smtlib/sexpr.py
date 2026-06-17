"""S-expression I/O for SMT-LIB (languages/smtlib brief — byte-exact text I/O).

Tokenize and parse an SMT-LIB script into nested s-expressions (an atom is a
``str``; a compound term is a ``list``), and print them back canonically. The
printer is byte-exact for the canonical, single-space, one-token-apart form the
translators emit, so a round-trip ``dumps(parse(t))`` reproduces the structure
and ``read_script(t).to_text() == t`` (script.py) holds for emitted scripts.
Comments and non-canonical spacing are normalized, not preserved (a later
increment, mirroring ``languages/btor2/model.py``).
"""

from __future__ import annotations

SExpr = "str | list"  # documentation alias: an atom (str) or a list of SExpr

_DELIMS = " \t\r\n();|"


def tokenize(text: str) -> list[str]:
    toks: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == ";":  # comment to end of line
            while i < n and text[i] != "\n":
                i += 1
        elif c in "()":
            toks.append(c)
            i += 1
        elif c == "|":  # quoted symbol |...|
            j = text.index("|", i + 1)
            toks.append(text[i:j + 1])
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in _DELIMS:
                j += 1
            toks.append(text[i:j])
            i = j
    return toks


def _parse_at(toks: list[str], i: int):
    tok = toks[i]
    if tok == "(":
        i += 1
        items: list = []
        while i < len(toks) and toks[i] != ")":
            item, i = _parse_at(toks, i)
            items.append(item)
        if i >= len(toks):
            raise ValueError("unbalanced '('")
        return items, i + 1
    if tok == ")":
        raise ValueError("unexpected ')'")
    return tok, i + 1


def parse(text: str) -> list:
    """Every top-level s-expression in ``text``, in order."""
    toks = tokenize(text)
    out: list = []
    i = 0
    while i < len(toks):
        expr, i = _parse_at(toks, i)
        out.append(expr)
    return out


def dumps(expr) -> str:
    """Canonical print: an atom verbatim; a list as ``(`` children-joined-by-one
    -space ``)`` (the empty list as ``()``)."""
    if isinstance(expr, list):
        return "(" + " ".join(dumps(e) for e in expr) + ")"
    return expr
