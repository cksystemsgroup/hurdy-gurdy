"""Source mutants of a generated executable — the faults injected.

A *site* is one syntactic place where one classical mutation operator
applies with one replacement. The operators are the ordinary ones of
mutation testing, chosen because each is a fault a generator plausibly
writes:

- ``cmp``   a comparison replaced (``<`` by ``<=`` or ``>=``, ``==`` by
            ``!=``, ``in`` by ``not in``, ...)
- ``bin``   an arithmetic or bitwise operator replaced (``+`` by ``-``,
            ``&`` by ``|``, ``<<`` by ``>>``, ...)
- ``bool``  ``and`` and ``or`` exchanged
- ``not``   a negation dropped
- ``cond``  the test of an ``if``, a ``while`` or a conditional
            expression negated
- ``const`` an integer constant moved by one, a truth constant flipped
- ``del``   a statement with no binding effect removed: an augmented
            assignment, a store into a subscript or an attribute, a
            bare call, a ``raise``; ``break`` and ``continue`` exchanged

Sites are enumerated in the order ``ast.walk`` visits the tree, which
is a function of the source alone, and sampled by a hash of (seed,
site), so a sample is reproducible on any Python that parses the file
the same way. A mutant is the unparsed tree; annotations and strings
are never mutated. The unparsed *intact* tree is the identity mutant,
which every experiment runs first: it must survive everything.
"""

from __future__ import annotations

import ast
import hashlib
from typing import NamedTuple

_CMP = {ast.Lt: (ast.LtE, ast.GtE), ast.LtE: (ast.Lt, ast.Gt),
        ast.Gt: (ast.GtE, ast.LtE), ast.GtE: (ast.Gt, ast.Lt),
        ast.Eq: (ast.NotEq,), ast.NotEq: (ast.Eq,),
        ast.Is: (ast.IsNot,), ast.IsNot: (ast.Is,),
        ast.In: (ast.NotIn,), ast.NotIn: (ast.In,)}

_BIN = {ast.Add: (ast.Sub,), ast.Sub: (ast.Add,), ast.Mult: (ast.Add,),
        ast.FloorDiv: (ast.Mult,), ast.Mod: (ast.FloorDiv,),
        ast.BitAnd: (ast.BitOr,), ast.BitOr: (ast.BitAnd,),
        ast.BitXor: (ast.BitAnd,), ast.LShift: (ast.RShift,),
        ast.RShift: (ast.LShift,)}

_SYMBOL = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
           ast.Eq: "==", ast.NotEq: "!=", ast.Is: "is",
           ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in",
           ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.FloorDiv: "//",
           ast.Mod: "%", ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^",
           ast.LShift: "<<", ast.RShift: ">>", ast.And: "and",
           ast.Or: "or"}

#: Operand shapes on which an arithmetic operator is text or sequence
#: building, not arithmetic: replacing it yields a crash, not a fault.
_TEXTUAL = (ast.JoinedStr, ast.List, ast.Tuple, ast.ListComp)


class Site(NamedTuple):
    node: int          # index of the node in ast.walk order
    op: str            # operator family
    alt: int           # which replacement, where a family has several
    line: int          # first line of the mutated node
    end_line: int      # last line of the mutated node
    detail: str        # human-readable: what became what


def _textual(node: ast.AST) -> bool:
    return isinstance(node, _TEXTUAL) or (
        isinstance(node, ast.Constant) and isinstance(node.value,
                                                      (str, bytes)))


def _annotations(tree: ast.AST) -> set[int]:
    """The ids of every node under an annotation: never mutated."""
    skip: set[int] = set()
    for node in ast.walk(tree):
        for field in ("annotation", "returns"):
            sub = getattr(node, field, None)
            if isinstance(sub, ast.AST):
                skip.update(id(n) for n in ast.walk(sub))
    return skip


def _alternatives(node: ast.AST) -> list[tuple[str, str]]:
    """The (family, detail) of every replacement at one node, in a
    fixed order; ``_apply`` realises the i-th by the same order."""
    out: list[tuple[str, str]] = []
    if isinstance(node, ast.Compare):
        for i, op in enumerate(node.ops):
            for new in _CMP.get(type(op), ()):
                out.append(("cmp", f"{_SYMBOL[type(op)]} -> "
                                   f"{_SYMBOL[new]} (operator {i})"))
    elif isinstance(node, (ast.BinOp, ast.AugAssign)):
        operands = ([node.left, node.right] if isinstance(node, ast.BinOp)
                    else [node.value])
        if not any(_textual(x) for x in operands):
            for new in _BIN.get(type(node.op), ()):
                out.append(("bin", f"{_SYMBOL[type(node.op)]} -> "
                                   f"{_SYMBOL[new]}"))
        if isinstance(node, ast.AugAssign):
            out.append(("del", "augmented assignment removed"))
    elif isinstance(node, ast.BoolOp):
        new = ast.Or if isinstance(node.op, ast.And) else ast.And
        out.append(("bool", f"{_SYMBOL[type(node.op)]} -> {_SYMBOL[new]}"))
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        out.append(("not", "negation dropped"))
    elif isinstance(node, (ast.If, ast.While, ast.IfExp)):
        out.append(("cond", f"{type(node).__name__.lower()} test negated"))
    elif isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            out.append(("const", f"{v} -> {not v}"))
        elif isinstance(v, int):
            out.append(("const", f"{v} -> {v + 1}"))
            if v == 1:
                out.append(("const", "1 -> 0"))
    elif isinstance(node, ast.Assign):
        if all(isinstance(t, (ast.Subscript, ast.Attribute))
               for t in node.targets):
            out.append(("del", "store removed"))
    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        out.append(("del", "call removed"))
    elif isinstance(node, ast.Raise):
        out.append(("del", "raise removed"))
    elif isinstance(node, ast.Break):
        out.append(("del", "break -> continue"))
    elif isinstance(node, ast.Continue):
        out.append(("del", "continue -> break"))
    return out


def sites(source: str) -> list[Site]:
    """Every mutation site of ``source``, in ``ast.walk`` order."""
    tree = ast.parse(source)
    skip = _annotations(tree)
    found: list[Site] = []
    for index, node in enumerate(ast.walk(tree)):
        if id(node) in skip:
            continue
        for alt, (op, detail) in enumerate(_alternatives(node)):
            found.append(Site(index, op, alt, node.lineno,
                              getattr(node, "end_lineno", node.lineno),
                              detail))
    return found


def _replace(tree: ast.AST, old: ast.AST, new: ast.AST) -> None:
    """Put ``new`` where ``old`` stands, wherever its parent holds it."""
    for parent in ast.walk(tree):
        for field, value in ast.iter_fields(parent):
            if value is old:
                setattr(parent, field, new)
                return
            if isinstance(value, list):
                for i, item in enumerate(value):
                    if item is old:
                        value[i] = new
                        return
    raise ValueError("node has no parent")


def _apply(tree: ast.AST, node: ast.AST, alt: int) -> None:
    family, _ = _alternatives(node)[alt]
    if family == "cmp":
        k = 0
        for i, op in enumerate(node.ops):
            for new in _CMP.get(type(op), ()):
                if k == alt:
                    node.ops[i] = new()
                    return
                k += 1
    elif family == "bin":
        node.op = _BIN[type(node.op)][alt]()
    elif family == "bool":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif family == "not":
        _replace(tree, node, node.operand)
    elif family == "cond":
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
    elif family == "const":
        v = node.value
        node.value = (not v) if isinstance(v, bool) else (
            v + 1 if alt == 0 else 0)
    elif isinstance(node, ast.Break):
        _replace(tree, node, ast.Continue())
    elif isinstance(node, ast.Continue):
        _replace(tree, node, ast.Break())
    else:
        _replace(tree, node, ast.Pass())


def identity(source: str) -> str:
    """The intact tree unparsed: what every mutant differs from by
    exactly one site, and the control every experiment runs first."""
    return ast.unparse(ast.parse(source)) + "\n"


def mutant(source: str, site: Site) -> str:
    """``source`` with the one fault ``site`` names."""
    tree = ast.parse(source)
    node = list(ast.walk(tree))[site.node]
    _apply(tree, node, site.alt)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def sample(source: str, what: str, n: int, seed: int) -> list[Site]:
    """``n`` sites of ``source`` (all of them when it has no more),
    ordered by a hash of (seed, ``what``, site) and so the same on
    every run; mutants whose text equals the identity are dropped."""
    def rank(s: Site) -> str:
        return hashlib.sha256(
            f"{seed}:{what}:{s.node}:{s.alt}".encode()).hexdigest()
    same, chosen = identity(source), []
    for s in sorted(sites(source), key=rank):
        if len(chosen) == n:
            break
        if mutant(source, s) != same:
            chosen.append(s)
    return chosen
