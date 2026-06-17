"""The SMT-LIB model evaluator — the deterministic ``I_t`` (languages/smtlib
brief; ARCHITECTURE.md §5).

Given a script and a *model* (a symbol->value binding a solver proposed),
substitute the model into the script and compute its truth: ``evaluate`` returns
whether every ``assert`` holds. This is the deterministic witness check that
validates a ``sat`` model *before it is believed* (SOLVERS.md §4-5) — it is
**not** the solver. It interprets the ``QF_ABV`` / ``QF_BV`` fragment the
``btor2-smtlib`` bridge emits (bit-vectors with width masking, arrays as sparse
maps); any operator outside that set hard-aborts with ``Unsupported``
(BENCHMARKS.md §3). Bit-vector semantics match the BTOR2 evaluator
(``languages/btor2/eval.py``), since the bridge maps operator-for-operator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core.errors import Unsupported
from .script import Script, read_script


@dataclass(frozen=True)
class BV:
    """A bit-vector value: an integer plus its width (bits)."""
    val: int
    width: int


@dataclass(frozen=True)
class Arr:
    """An array value: a sparse store over a default element, with the element
    width so a ``select`` masks to the right size."""
    store: dict
    default: int
    ewidth: int


def _mask(w: int) -> int:
    return (1 << w) - 1


def _to_signed(v: int, w: int) -> int:
    v &= _mask(w)
    return v - (1 << w) if v >> (w - 1) else v


def _bv(op: str, a: BV, b: BV) -> BV:
    w = a.width
    m = _mask(w)
    if op == "bvand":
        return BV(a.val & b.val, w)
    if op == "bvor":
        return BV(a.val | b.val, w)
    if op == "bvxor":
        return BV(a.val ^ b.val, w)
    if op == "bvnand":
        return BV(~(a.val & b.val) & m, w)
    if op == "bvnor":
        return BV(~(a.val | b.val) & m, w)
    if op == "bvadd":
        return BV((a.val + b.val) & m, w)
    if op == "bvsub":
        return BV((a.val - b.val) & m, w)
    if op == "bvmul":
        return BV((a.val * b.val) & m, w)
    if op == "bvudiv":
        return BV(m if b.val == 0 else (a.val // b.val) & m, w)
    if op == "bvurem":
        return BV(a.val & m if b.val == 0 else (a.val % b.val) & m, w)
    if op == "bvsdiv":
        x, y = _to_signed(a.val, w), _to_signed(b.val, w)
        if y == 0:
            return BV(m if x >= 0 else 1, w)
        q = -(abs(x) // abs(y)) if (x < 0) != (y < 0) else abs(x) // abs(y)
        return BV(q & m, w)
    if op == "bvsrem":
        x, y = _to_signed(a.val, w), _to_signed(b.val, w)
        if y == 0:
            return BV(a.val & m, w)
        r = abs(x) % abs(y)
        return BV((-r if x < 0 else r) & m, w)
    if op == "bvshl":
        return BV(0 if b.val >= w else (a.val << b.val) & m, w)
    if op == "bvlshr":
        return BV(0 if b.val >= w else (a.val & m) >> b.val, w)
    if op == "bvashr":
        sv = _to_signed(a.val, w)
        if b.val >= w:
            return BV(m if sv < 0 else 0, w)
        return BV((sv >> b.val) & m, w)
    if op == "concat":
        return BV(((a.val << b.width) | (b.val & _mask(b.width))) & _mask(w + b.width),
                  w + b.width)
    raise Unsupported("smtlib", f"bvbin:{op}")


_UCMP = {"bvult": lambda a, b: a < b, "bvule": lambda a, b: a <= b,
         "bvugt": lambda a, b: a > b, "bvuge": lambda a, b: a >= b}
_SCMP = {"bvslt": lambda a, b: a < b, "bvsle": lambda a, b: a <= b,
         "bvsgt": lambda a, b: a > b, "bvsge": lambda a, b: a >= b}


def _arr_eq(a: Arr, b: Arr) -> bool:
    if a.default != b.default:
        return False
    keys = set(a.store) | set(b.store)
    return all(a.store.get(k, a.default) == b.store.get(k, b.default) for k in keys)


def _eq(a: Any, b: Any) -> bool:
    if isinstance(a, BV) and isinstance(b, BV):
        return a.val == b.val and a.width == b.width
    if isinstance(a, Arr) and isinstance(b, Arr):
        return _arr_eq(a, b)
    return a == b


def _indexed(head: list, args: list, env: dict):
    op = head[1]
    x = value_of(args[0], env)
    if op == "extract":
        u, lo = int(head[2]), int(head[3])
        return BV((x.val >> lo) & _mask(u - lo + 1), u - lo + 1)
    if op == "sign_extend":
        n = int(head[2])
        return BV(_to_signed(x.val, x.width) & _mask(x.width + n), x.width + n)
    if op == "zero_extend":
        n = int(head[2])
        return BV(x.val & _mask(x.width + n), x.width + n)
    raise Unsupported("smtlib", f"indexed:{op}")


def value_of(t, env: dict):
    """Evaluate a term ``t`` under the environment ``env`` (symbol -> value).
    Returns a ``BV``, an ``Arr``, or a Python ``bool``."""
    if isinstance(t, str):
        if t.startswith("#b"):
            return BV(int(t[2:], 2), len(t) - 2)
        if t.startswith("#x"):
            return BV(int(t[2:], 16), 4 * (len(t) - 2))
        if t == "true":
            return True
        if t == "false":
            return False
        if t in env:
            return env[t]
        raise Unsupported("smtlib", f"symbol:{t}")

    head = t[0]
    if isinstance(head, list):  # indexed op: ((_ extract u l) x), etc.
        return _indexed(head, t[1:], env)

    args = t[1:]
    if head == "_":  # the (_ bvN w) literal
        return BV(int(t[1][2:]) & _mask(int(t[2])), int(t[2]))

    if head == "ite":
        return value_of(args[1], env) if value_of(args[0], env) else value_of(args[2], env)
    if head == "=":
        first = value_of(args[0], env)
        return all(_eq(first, value_of(x, env)) for x in args[1:])
    if head == "distinct":
        vals = [value_of(x, env) for x in args]
        return all(not _eq(vals[i], vals[j])
                   for i in range(len(vals)) for j in range(i + 1, len(vals)))
    if head == "not":
        return not value_of(args[0], env)
    if head == "and":
        return all(value_of(x, env) for x in args)
    if head == "or":
        return any(value_of(x, env) for x in args)
    if head == "=>":
        *ps, q = [value_of(x, env) for x in args]
        return (not all(ps)) or q
    if head in _UCMP:
        a, b = value_of(args[0], env), value_of(args[1], env)
        return _UCMP[head](a.val, b.val)
    if head in _SCMP:
        a, b = value_of(args[0], env), value_of(args[1], env)
        return _SCMP[head](_to_signed(a.val, a.width), _to_signed(b.val, b.width))
    if head == "bvnot":
        x = value_of(args[0], env)
        return BV(~x.val & _mask(x.width), x.width)
    if head == "bvneg":
        x = value_of(args[0], env)
        return BV(-x.val & _mask(x.width), x.width)
    if head == "select":
        arr, idx = value_of(args[0], env), value_of(args[1], env)
        return BV(arr.store.get(idx.val, arr.default) & _mask(arr.ewidth), arr.ewidth)
    if head == "store":
        arr, idx, val = (value_of(args[0], env), value_of(args[1], env),
                         value_of(args[2], env))
        new = dict(arr.store)
        new[idx.val] = val.val
        return Arr(new, arr.default, arr.ewidth)
    # binary bit-vector ops (bvand .. concat)
    return _bv(head, value_of(args[0], env), value_of(args[1], env))


def _seed(sort, mval):
    """An initial value for a declared symbol from its sort and model entry
    (defaulting an omitted / don't-care symbol to 0 / the empty array)."""
    if isinstance(sort, list) and sort[0] == "_" and sort[1] == "BitVec":
        w = int(sort[2])
        return BV((int(mval) if mval is not None else 0) & _mask(w), w)
    if isinstance(sort, list) and sort[0] == "Array":
        ewidth = int(sort[2][2])  # (Array (_ BitVec iw) (_ BitVec ew))
        store, default = {}, 0
        if isinstance(mval, dict):
            for k, v in mval.items():
                if k == "default":
                    default = int(v)
                else:
                    store[int(k)] = int(v)
        return Arr(store, default, ewidth)
    raise Unsupported("smtlib", f"sort:{sort}")


def evaluate(script, model: dict | None = None) -> bool:
    """Does ``model`` satisfy ``script`` — i.e. do all its assertions hold?

    The deterministic witness check: a solver's ``sat`` model is only believed
    once this returns ``True``. Raises ``Unsupported`` on a construct outside the
    bridged fragment.
    """
    if not isinstance(script, Script):
        script = read_script(script)
    model = model or {}
    env: dict = {}
    for name, sort in script.declares().items():
        env[name] = _seed(sort, model.get(name))
    for name, _sort, body in script.defines():
        env[name] = value_of(body, env)
    return all(value_of(a, env) is True for a in script.assertions())
