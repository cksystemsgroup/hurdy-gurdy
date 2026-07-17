"""A deterministic BTOR2 evaluator (the shared BTOR2 interpreter).

Steps a transition system for ``k`` cycles given a binding (initial state +
per-step inputs), producing a ``Trace`` of post-cycle state values, ``bad``
signal statuses, and — when the system declares them — ``constraint`` signal
statuses (ARCHITECTURE.md §5). Constraints are **enforced** per the BTOR2
standard: each row records ``constraint{id}`` beside ``bad{id}``, and a row
where any constraint is 0 is the run's last (no valid continuation — the
trace truncates after the violating row, which native checkers likewise
never extend). A system with no constraint nodes produces byte-identical
traces to the pre-enforcement evaluator. Bit-vector semantics with width
masking; arrays as sparse maps. Operators outside the MVP set hard-abort
with ``Unsupported`` (BENCHMARKS.md §3). The dev-image acceptance is
agreement with a ``btorsim`` replay of a solver ``.wit`` (DOCKER.md).
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace
from .model import Array, Bitvec, Node, System, from_text

_MISSING = object()  # sentinel: _env_ref without a default raises on absence


class _Array(dict):
    """A sparse array with an ``else`` default (so a witness's const-array
    default replays faithfully)."""
    __slots__ = ("default",)

    def __init__(self, *args: Any, default: int = 0, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.default = default


def _mask(width: int) -> int:
    return (1 << width) - 1


def _to_signed(value: int, width: int) -> int:
    value &= _mask(width)
    if value >> (width - 1):
        value -= 1 << width
    return value


def _bv_width(sys: System, node: Node) -> int | None:
    sort = sys.sorts.get(node.sort) if node.sort is not None else None
    if isinstance(sort, Bitvec):
        return sort.width
    return None  # array-valued (or directive)


def _const_value(sys: System, node: Node) -> int:
    width = _bv_width(sys, node) or 0
    m = _mask(width)
    if node.op == "zero":
        return 0
    if node.op == "one":
        return 1 & m
    if node.op == "ones":
        return m
    if node.op == "constd":
        return int(node.literal) & m
    if node.op == "const":
        return int(node.literal, 2) & m
    if node.op == "consth":
        return int(node.literal, 16) & m
    raise Unsupported("btor2", f"const.{node.op}")


def _label(node: Node) -> str:
    return node.symbol or f"n{node.id}"


def _env_ref(sys: System, env: dict[int, Any], r: int, default: Any = _MISSING) -> Any:
    """Resolve a (possibly negated) node reference: BTOR2 lets any operand
    cite ``-n`` for the bitwise NOT of node ``n``'s bit-vector value
    (surfaced by HWMCC ingestion; a negated array reference is typed
    unsupported)."""
    if r >= 0:
        if default is _MISSING:
            return env[r]
        return env.get(r, default)
    node = sys.nodes[-r]
    w = _bv_width(sys, node)
    if w is None:
        raise Unsupported("btor2", "negated-array-ref")
    v = env[-r] if default is _MISSING else env.get(-r, default)
    return (~v) & _mask(w)


def _eval_node(sys: System, node: Node, env: dict[int, Any], cur: dict[int, Any],
               inputs: dict[int, int]) -> Any:
    op = node.op
    width = _bv_width(sys, node)

    if op == "state":
        return cur[node.id]
    if op == "input":
        return inputs.get(node.id, 0) & _mask(width or 0)
    if op in ("zero", "one", "ones", "const", "constd", "consth"):
        return _const_value(sys, node)

    m = _mask(width or 1)
    refs = [_env_ref(sys, env, r) for r in node.refs]

    if op in ("and",):
        return (refs[0] & refs[1]) & m
    if op == "or":
        return (refs[0] | refs[1]) & m
    if op == "xor":
        return (refs[0] ^ refs[1]) & m
    if op == "nand":
        return (~(refs[0] & refs[1])) & m
    if op == "nor":
        return (~(refs[0] | refs[1])) & m
    if op == "not":
        return (~refs[0]) & m
    if op == "neg":
        return (-refs[0]) & m
    if op == "inc":
        return (refs[0] + 1) & m
    if op == "dec":
        return (refs[0] - 1) & m
    if op == "add":
        return (refs[0] + refs[1]) & m
    if op == "sub":
        return (refs[0] - refs[1]) & m
    if op == "mul":
        return (refs[0] * refs[1]) & m
    if op == "udiv":
        return m if refs[1] == 0 else (refs[0] // refs[1]) & m
    if op == "urem":
        return refs[0] & m if refs[1] == 0 else (refs[0] % refs[1]) & m
    if op == "sdiv":
        bw = width or 1
        x, y = _to_signed(refs[0], bw), _to_signed(refs[1], bw)
        if y == 0:
            return m if x >= 0 else 1  # SMT bvsdiv by zero
        return (-(abs(x) // abs(y)) if (x < 0) != (y < 0) else abs(x) // abs(y)) & m
    if op == "srem":
        bw = width or 1
        x, y = _to_signed(refs[0], bw), _to_signed(refs[1], bw)
        if y == 0:
            return refs[0] & m  # SMT bvsrem by zero -> dividend
        r = abs(x) % abs(y)
        return (-r if x < 0 else r) & m
    if op in ("eq", "iff"):
        return 1 if refs[0] == refs[1] else 0
    if op == "neq":
        return 1 if refs[0] != refs[1] else 0
    if op == "implies":
        return 1 if (refs[0] == 0 or refs[1] != 0) else 0
    if op in ("ult", "ulte", "ugt", "ugte"):
        a, b = refs[0], refs[1]
        return 1 if {"ult": a < b, "ulte": a <= b, "ugt": a > b, "ugte": a >= b}[op] else 0
    if op in ("slt", "slte", "sgt", "sgte"):
        aw = _bv_width(sys, sys.nodes[node.refs[0]]) or 1
        a, b = _to_signed(refs[0], aw), _to_signed(refs[1], aw)
        return 1 if {"slt": a < b, "slte": a <= b, "sgt": a > b, "sgte": a >= b}[op] else 0
    if op in ("redor", "redand", "redxor"):
        aw = _bv_width(sys, sys.nodes[node.refs[0]]) or 1
        a = refs[0] & _mask(aw)
        if op == "redor":
            return 1 if a != 0 else 0
        if op == "redand":
            return 1 if a == _mask(aw) else 0
        return bin(a).count("1") & 1
    if op in ("sll", "srl", "sra"):
        w = width or 1
        sh = refs[1]
        if op == "sll":
            return 0 if sh >= w else (refs[0] << sh) & m
        if op == "srl":
            return 0 if sh >= w else (refs[0] & m) >> sh
        sv = _to_signed(refs[0], w)
        if sh >= w:
            return m if sv < 0 else 0
        return (sv >> sh) & m
    if op == "concat":
        bw = _bv_width(sys, sys.nodes[node.refs[1]]) or 0
        return ((refs[0] << bw) | (refs[1] & _mask(bw))) & m
    if op == "slice":
        upper, lower = node.bounds
        return (refs[0] >> lower) & _mask(upper - lower + 1)
    if op == "sext":
        aw = _bv_width(sys, sys.nodes[node.refs[0]]) or 1
        return _to_signed(refs[0], aw) & m
    if op == "uext":
        return refs[0] & m
    if op == "ite":
        return refs[1] if refs[0] != 0 else refs[2]
    if op == "read":
        arr = refs[0]
        return arr.get(refs[1], getattr(arr, "default", 0)) & m
    if op == "write":
        new = _Array(refs[0], default=getattr(refs[0], "default", 0))
        new[refs[1]] = refs[2]
        return new
    raise Unsupported("btor2", f"op.{op}")


_DIRECTIVES = {"init", "next", "bad", "constraint", "output"}


def _initial_state(sys: System, node: Node, binding: dict[str, Any]) -> Any:
    label = _label(node)
    override = binding.get("state", {})
    width = _bv_width(sys, node)
    if width is None:  # array: a sparse map + an "else" default
        src = override.get(label, {})
        arr = _Array(default=int(src.get("default", 0)))
        for key, val in src.items():
            if key != "default":
                arr[int(key)] = int(val)
        return arr
    if label in override:
        return int(override[label]) & _mask(width)
    # an init directive supplies a constant initial value (a negated
    # reference inverts the constant, masked at the state's width)
    for n in sys.nodes.values():
        if n.op == "init" and n.refs[0] == node.id:
            v = _const_value(sys, sys.nodes[abs(n.refs[1])])
            if n.refs[1] < 0:
                v = (~v) & _mask(width)
            return v
    return 0


def _next_value_ref(sys: System, state_id: int) -> int | None:
    for n in sys.nodes.values():
        if n.op == "next" and n.refs[0] == state_id:
            return n.refs[1]
    return None


def step(sys: System, binding: dict[str, Any] | None = None) -> Trace:
    binding = binding or {}
    k = int(binding.get("steps", 1))
    states = sys.states()
    cur: dict[int, Any] = {s.id: _initial_state(sys, s, binding) for s in states}

    value_ids = sorted(nid for nid, n in sys.nodes.items() if n.op not in _DIRECTIVES)
    trace: list[dict[str, Any]] = []
    for cycle in range(k):
        env: dict[int, Any] = {}
        inputs = binding.get("inputs", {}).get(cycle, {})
        for nid in value_ids:
            env[nid] = _eval_node(sys, sys.nodes[nid], env, cur, inputs)
        row: dict[str, Any] = {}
        for s in states:
            if _bv_width(sys, s) is not None:
                row[_label(s)] = cur[s.id]
        for bnode in sys.bads():
            row[f"bad{bnode.id}"] = 1 if _env_ref(sys, env, bnode.refs[0], 0) != 0 else 0
        violated = False
        for cnode in sys.constraints():
            ok = 1 if _env_ref(sys, env, cnode.refs[0], 0) != 0 else 0
            row[f"constraint{cnode.id}"] = ok
            violated = violated or ok == 0
        trace.append(row)
        if violated:
            break  # constraint violated: no valid continuation (truncate)
        nxt = dict(cur)
        for s in states:
            ref = _next_value_ref(sys, s.id)
            if ref is not None:
                nxt[s.id] = _env_ref(sys, env, ref)
        cur = nxt
    return trace


def interpret(artifact: Any, binding: dict[str, Any] | None = None, **_kw: Any) -> Trace:
    """Parse a BTOR2 artifact (bytes/str/System) and step it. This is the
    callable registered as the language's interpreter."""
    if isinstance(artifact, System):
        sys = artifact
    else:
        text = artifact.decode("utf-8") if isinstance(artifact, (bytes, bytearray)) else str(artifact)
        sys = from_text(text)
    return step(sys, binding)
