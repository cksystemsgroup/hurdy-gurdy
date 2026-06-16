"""BTOR2 model: parser and canonical printer (I/O first — languages/btor2
brief). Round-trip is byte-exact for canonical, comment-free BTOR2 (what the
translators emit); comments/odd spacing are not preserved (a later increment).

Each line is ``<id> <kind> <fields...> [symbol]``. Sorts are
``<id> sort bitvec <w>`` or ``<id> sort array <idx> <elem>``; everything else
is a node referencing sorts/nodes by id.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...core.errors import Unsupported


@dataclass(frozen=True)
class Bitvec:
    width: int


@dataclass(frozen=True)
class Array:
    index: int   # sort id
    element: int  # sort id


# Operator arities, in terms of how many trailing tokens are node references.
# (sort id is handled separately where present.)
_UNARY = {"not", "neg", "inc", "dec", "redor", "redand", "redxor"}
_BINARY = {
    "and", "or", "xor", "nand", "nor", "add", "sub", "mul", "udiv", "urem",
    "sdiv", "srem", "eq", "neq", "ult", "ulte", "ugt", "ugte", "slt", "slte",
    "sgt", "sgte", "sll", "srl", "sra", "concat", "implies", "iff",
}
_CONST_LITERAL = {"const", "constd", "consth"}  # one literal value token
_NULLARY_CONST = {"zero", "one", "ones"}


@dataclass
class Node:
    id: int
    op: str
    sort: int | None = None
    refs: tuple[int, ...] = ()       # node-reference args (for evaluation)
    literal: str | None = None       # constant value token (const/constd/consth)
    bounds: tuple[int, ...] = ()      # slice (upper, lower) / sext|uext (n)
    symbol: str | None = None
    raw_fields: tuple[str, ...] = ()  # tokens after id+op, verbatim (for printing)


@dataclass
class System:
    order: list[int] = field(default_factory=list)
    sorts: dict[int, Bitvec | Array] = field(default_factory=dict)
    nodes: dict[int, Node] = field(default_factory=dict)
    # for printing: id -> (kind, raw_fields, symbol)
    _print: dict[int, tuple[str, tuple[str, ...], str | None]] = field(default_factory=dict)

    def states(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.op == "state"]

    def bads(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.op == "bad"]


def _looks_symbol(tok: str) -> bool:
    try:
        int(tok)
        return False
    except ValueError:
        return True


def from_text(text: str) -> System:
    sys = System()
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        toks = stripped.split()
        nid = int(toks[0])
        kind = toks[1]
        rest = toks[2:]

        if kind == "sort":
            if rest[0] == "bitvec":
                sys.sorts[nid] = Bitvec(int(rest[1]))
            elif rest[0] == "array":
                sys.sorts[nid] = Array(int(rest[1]), int(rest[2]))
            else:
                raise Unsupported("btor2", f"sort.{rest[0]}")
            sys._print[nid] = (kind, tuple(rest), None)
            sys.order.append(nid)
            continue

        node = Node(id=nid, op=kind, raw_fields=tuple(rest))
        symbol = None
        body = list(rest)
        # trailing symbol (input/state/...): a non-numeric final token
        if body and _looks_symbol(body[-1]) and kind not in _CONST_LITERAL | {"sort"}:
            symbol = body[-1]
            body = body[:-1]

        if kind in _NULLARY_CONST:
            node.sort = int(body[0])
        elif kind in _CONST_LITERAL:
            node.sort = int(body[0])
            node.literal = body[1]
        elif kind in ("input", "state"):
            node.sort = int(body[0])
        elif kind in ("init", "next"):
            node.sort = int(body[0])
            node.refs = (int(body[1]), int(body[2]))
        elif kind in ("bad", "constraint", "output"):
            node.refs = (int(body[0]),)
        elif kind in _UNARY:
            node.sort = int(body[0])
            node.refs = (int(body[1]),)
        elif kind in _BINARY:
            node.sort = int(body[0])
            node.refs = (int(body[1]), int(body[2]))
        elif kind == "ite":
            node.sort = int(body[0])
            node.refs = (int(body[1]), int(body[2]), int(body[3]))
        elif kind == "slice":
            node.sort = int(body[0])
            node.refs = (int(body[1]),)
            node.bounds = (int(body[2]), int(body[3]))
        elif kind in ("sext", "uext"):
            node.sort = int(body[0])
            node.refs = (int(body[1]),)
            node.bounds = (int(body[2]),)
        elif kind == "read":
            node.sort = int(body[0])
            node.refs = (int(body[1]), int(body[2]))
        elif kind == "write":
            node.sort = int(body[0])
            node.refs = (int(body[1]), int(body[2]), int(body[3]))
        else:
            raise Unsupported("btor2", f"op.{kind}")

        node.symbol = symbol
        sys.nodes[nid] = node
        sys._print[nid] = (kind, tuple(rest), symbol)
        sys.order.append(nid)
    return sys


def to_text(sys: System) -> str:
    lines = []
    for nid in sys.order:
        kind, raw_fields, _symbol = sys._print[nid]
        parts = [str(nid), kind, *raw_fields]
        lines.append(" ".join(parts))
    return "\n".join(lines) + "\n"
