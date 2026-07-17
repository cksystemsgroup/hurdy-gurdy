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

    def constraints(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.op == "constraint"]


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


def _render(new: dict[int, int], nid: int, node: Node) -> list[str]:
    """Rebuild a node's line tokens (after ``id`` + ``op``) with references
    remapped through ``new``. Mirrors ``from_text``'s per-kind field layout;
    literals (constant values, widths, slice/extend amounts) pass through."""
    k = node.op
    sort = [str(new[node.sort])] if node.sort is not None else []
    refs = [str(new[r]) for r in node.refs]
    sym = [node.symbol] if node.symbol else []
    if k in _CONST_LITERAL:
        return sort + [node.literal] + sym
    if k == "slice":
        return sort + refs + [str(b) for b in node.bounds] + sym
    if k in ("sext", "uext"):
        return sort + refs + [str(node.bounds[0])] + sym
    # nullary const, input/state, init/next, bad/constraint/output, unary,
    # binary, ite, read, write: sort (if any) then node refs then symbol.
    return sort + refs + sym


def canonicalize(text: str | bytes) -> str:
    """Renumber a BTOR2 system into the node order native checkers require.

    ``btor2tools`` (and thus ``pono`` / ``btormc``) enforce, beyond
    backward references, that an ``init``'s value operand has a *smaller* id
    than its state ("state id must be greater than id of second operand").
    The builder allocates states before the constants they are initialized to,
    which violates this -- so the bridged z3 path accepts the output but every
    native checker rejects it (the bug the native-vs-bridged cross-check
    exists to catch was hiding in the emitter).

    The fix is a stable regrouping -- sorts, then constant leaves, then states,
    then everything else in original order -- which places every init value (a
    constant) before every state while keeping all references backward. Pure
    and idempotent; the z3 bridge and the BTOR2 evaluator are unaffected (they
    key off symbols and re-parse ids consistently)."""
    sys = from_text(text.decode("utf-8") if isinstance(text, (bytes, bytearray)) else text)
    consts = _CONST_LITERAL | _NULLARY_CONST
    groups: list[list[int]] = [[], [], [], []]  # sorts, consts, states, rest
    for nid in sys.order:
        kind = sys._print[nid][0]
        idx = 0 if kind == "sort" else 1 if kind in consts else 2 if kind == "state" else 3
        groups[idx].append(nid)
    order = [nid for g in groups for nid in g]
    new = {old: i + 1 for i, old in enumerate(order)}

    lines: list[str] = []
    for old in order:
        nid = new[old]
        if old in sys.sorts:
            s = sys.sorts[old]
            fields = (["bitvec", str(s.width)] if isinstance(s, Bitvec)
                      else ["array", str(new[s.index]), str(new[s.element])])
            lines.append(" ".join([str(nid), "sort", *fields]))
        else:
            node = sys.nodes[old]
            lines.append(" ".join([str(nid), node.op, *_render(new, nid, node)]))
    return "\n".join(lines) + "\n"
