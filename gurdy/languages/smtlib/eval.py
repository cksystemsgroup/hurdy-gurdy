"""The SMT-LIB model evaluator — the deterministic ``I_t`` (languages/smtlib
brief; ARCHITECTURE.md §5).

Given a script and a *model* (a symbol->value binding a solver proposed),
substitute the model into the script and compute its truth: ``evaluate`` returns
whether every ``assert`` holds. This is the deterministic witness check that
validates a ``sat`` model *before it is believed* (SOLVERS.md §4-5) — it is
**not** the solver.

Two fragments are interpreted:

* ``QF_ABV`` / ``QF_BV`` — the bit-vector-and-array fragment the
  ``btor2-smtlib`` bridge emits (bit-vectors with width masking, arrays as
  sparse maps). Bit-vector semantics match the BTOR2 evaluator
  (``languages/btor2/eval.py``), since the bridge maps operator-for-operator.
* ``QF_LIA`` — the linear-integer-arithmetic fragment the ``crn-smtlib`` (and,
  once built, ``python-smtlib``) pairs emit: the ``Int`` sort over Python's
  arbitrary-precision ``int`` (the faithful match for SMT ``Int``), integer
  literals, ``+`` / ``-`` (binary and unary) / ``*`` / ``div`` / ``mod`` /
  ``abs``, the integer comparisons ``<=`` / ``<`` / ``>=`` / ``>``, and the
  boolean layer (``and`` / ``or`` / ``not`` / ``=>`` / ``xor`` / ``=`` /
  ``distinct`` / ``ite``) shared with the bit-vector path. ``div`` / ``mod``
  follow the **SMT-LIB Ints theory** (Euclidean: ``0 <= (mod m n) < abs n``),
  which differs from Python's floored ``//`` / ``%`` for a negative divisor.

Any operator outside both sets hard-aborts with ``Unsupported``
(BENCHMARKS.md §3) — it is never silently mis-evaluated. (``let`` is not in the
``QF_ABV`` path either, so it stays out of fragment and hard-aborts.)

This is a **versioned** shared interpreter (AGENTS.md §3): the ``QF_LIA`` arm is
strictly *additive* — it leaves every ``QF_ABV`` evaluation value-for-value
unchanged — but adding it bumps ``INTERPRETER_VERSION`` and re-validates the
dependent pairs (``btor2-smtlib``, ``crn-smtlib``) against it — see
``languages/smtlib/__init__.py``.
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

# --- QF_LIA (linear integer arithmetic) -----------------------------------
# The integer comparisons (additive — these heads are free in the QF_ABV path,
# which uses ``bvult`` / ``bvslt`` / … instead). Over Python ``int`` they are
# exact arbitrary-precision integer order, the faithful match for SMT ``Int``.
_ICMP = {"<=": lambda a, b: a <= b, "<": lambda a, b: a < b,
         ">=": lambda a, b: a >= b, ">": lambda a, b: a > b}


def _is_int_literal(t: str) -> bool:
    """An SMT-LIB ``Int`` numeral is a non-empty run of decimal digits
    (``0``, ``42``, …; negatives are written ``(- 42)``, not ``-42``). Never
    collides with a bit-vector literal (those start ``#b`` / ``#x`` / ``(_ bvN``)."""
    return t.isdigit()


def _int_div(m: int, n: int) -> int:
    """SMT-LIB Ints ``div`` (Euclidean): the unique ``q`` with
    ``m = n*q + r`` and ``0 <= r < |n|``. Differs from Python ``//`` when ``n``
    is negative; division by zero is left to the caller's guard."""
    q = m // abs(n)
    return q if n > 0 else -q


def _int_mod(m: int, n: int) -> int:
    """SMT-LIB Ints ``mod`` (Euclidean): the remainder ``r`` with
    ``0 <= r < |n|`` (always non-negative), matching ``m - n*(div m n)``."""
    return m % abs(n)


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
    if not args:  # an indexed op applied with no operand is out of fragment
        raise Unsupported("smtlib", f"indexed:{op}")
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
    Returns a ``BV``, an ``Arr``, a Python ``int`` (``QF_LIA``), or a Python
    ``bool``."""
    if isinstance(t, str):
        if t.startswith("#b"):
            return BV(int(t[2:], 2), len(t) - 2)
        if t.startswith("#x"):
            return BV(int(t[2:], 16), 4 * (len(t) - 2))
        if t == "true":
            return True
        if t == "false":
            return False
        if _is_int_literal(t):  # QF_LIA: a decimal Int numeral (arbitrary-precision)
            return int(t)
        if t in env:
            return env[t]
        raise Unsupported("smtlib", f"symbol:{t}")

    head = t[0]
    if isinstance(head, list):  # indexed op: ((_ extract u l) x), etc.
        return _indexed(head, t[1:], env)

    args = t[1:]
    if head == "_":  # the (_ bvN w) literal
        return BV(int(t[1][2:]) & _mask(int(t[2])), int(t[2]))

    if head == "let":  # not handled in either fragment; hard-abort (not guessed)
        raise Unsupported("smtlib", "let")

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
    if head == "xor":  # boolean xor: parity of the truthy operands
        acc = False
        for x in args:
            acc ^= bool(value_of(x, env))
        return acc
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

    # --- QF_LIA integer ops (additive; these heads are free in QF_ABV) ----
    if head == "+":  # n-ary sum (SMT-LIB ``+`` is variadic)
        acc = 0
        for x in args:
            acc += value_of(x, env)
        return acc
    if head == "*":  # n-ary product
        acc = 1
        for x in args:
            acc *= value_of(x, env)
        return acc
    if head == "-":  # unary negation or n-ary left-associative subtraction
        vals = [value_of(x, env) for x in args]
        if len(vals) == 1:
            return -vals[0]
        acc = vals[0]
        for v in vals[1:]:
            acc -= v
        return acc
    if head == "div":  # SMT-LIB Ints Euclidean division (left-associative)
        acc = value_of(args[0], env)
        for x in args[1:]:
            n = value_of(x, env)
            if n == 0:
                raise Unsupported("smtlib", "div-by-zero")
            acc = _int_div(acc, n)
        return acc
    if head == "mod":  # SMT-LIB Ints Euclidean remainder (binary)
        m, n = value_of(args[0], env), value_of(args[1], env)
        if n == 0:
            raise Unsupported("smtlib", "mod-by-zero")
        return _int_mod(m, n)
    if head == "abs":
        return abs(value_of(args[0], env))
    if head in _ICMP:  # chained integer comparison (SMT-LIB ``<`` … are n-ary)
        vals = [value_of(x, env) for x in args]
        return all(_ICMP[head](vals[i], vals[i + 1]) for i in range(len(vals) - 1))

    # binary bit-vector ops (bvand .. concat). An unknown head — or a wrong
    # arity — is out of fragment: hard-abort with a typed ``Unsupported``
    # (BENCHMARKS.md §3) rather than crashing on a missing operand.
    if len(args) != 2:
        raise Unsupported("smtlib", f"op:{head}")
    return _bv(head, value_of(args[0], env), value_of(args[1], env))


def _bool_of(mval) -> bool:
    """A model entry for a ``Bool`` constant -> a Python ``bool``. The z3 backend
    stringifies it to ``"True"`` / ``"False"``; accept the obvious shapes (and
    the SMT literals ``true`` / ``#b1``), defaulting an omitted don't-care to
    ``False``."""
    if isinstance(mval, bool):
        return mval
    if isinstance(mval, int):
        return mval != 0
    if isinstance(mval, str):
        return mval.strip().lower() in ("true", "#b1", "1")
    return False


def _seed(sort, mval):
    """An initial value for a declared symbol from its sort and model entry
    (defaulting an omitted / don't-care symbol to 0 / False / the empty array)."""
    if sort == "Int":  # QF_LIA: arbitrary-precision Python int (defaults to 0)
        return int(mval) if mval is not None else 0
    if sort == "Bool":  # QF_LIA boolean layer (defaults to False)
        return _bool_of(mval)
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
    once this returns ``True``. Works over both the ``QF_ABV`` / ``QF_BV``
    (bit-vector/array) and the ``QF_LIA`` (linear integer arithmetic) fragments;
    raises ``Unsupported`` on a construct outside both.
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
