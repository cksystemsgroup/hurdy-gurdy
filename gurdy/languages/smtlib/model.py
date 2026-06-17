"""SMT-LIB models — the witness a solver returns, in the shape the deterministic
evaluator (eval.py) checks (languages/smtlib brief).

A ``Model`` maps a declared symbol to a concrete value: an ``int`` for a
bit-vector, or a ``{index: value, "default": d}`` map for an array. The z3
backend already returns this normalized shape (``solvers/z3_smt.py``);
``read_model`` parses an SMT-LIB ``(model ...)`` / ``get-value`` textual reply
into the same shape, so a native solver's text witness can be checked too.
Bit-vector values and ``store`` / const-array chains are parsed; an entry whose
value is some other (unrecognized) term is skipped rather than guessed at.
"""

from __future__ import annotations

from typing import Any

from . import sexpr

Model = dict[str, Any]


def parse_bv_literal(tok) -> int | None:
    """An SMT bit-vector literal -> its integer value, else ``None``.
    Handles ``#b1010``, ``#xff`` and the indexed ``(_ bv42 w)`` form."""
    if isinstance(tok, str):
        if tok.startswith("#b"):
            return int(tok[2:], 2)
        if tok.startswith("#x"):
            return int(tok[2:], 16)
        return None
    if (isinstance(tok, list) and len(tok) == 3 and tok[0] == "_"
            and isinstance(tok[1], str) and tok[1].startswith("bv")):
        return int(tok[1][2:])
    return None


def _read_value(tok):
    bv = parse_bv_literal(tok)
    if bv is not None:
        return bv
    if isinstance(tok, list) and tok:
        # (store base idx val) -- one entry over a base array
        if tok[0] == "store":
            base = _read_value(tok[1])
            arr = dict(base) if isinstance(base, dict) else {}
            idx, val = parse_bv_literal(tok[2]), parse_bv_literal(tok[3])
            if idx is not None and val is not None:
                arr[idx] = val
            return arr
        # ((as const (Array I E)) default)
        if (isinstance(tok[0], list) and len(tok[0]) >= 2
                and tok[0][0] == "as" and tok[0][1] == "const"):
            d = parse_bv_literal(tok[1])
            return {"default": d if d is not None else 0}
    return None


def _read_define(c, out: Model) -> None:
    if (isinstance(c, list) and len(c) >= 5 and c[0] == "define-fun"
            and c[2] == []):
        v = _read_value(c[4])
        if v is not None:
            out[c[1]] = v


def read_model(text: str | bytes) -> Model:
    """Parse a solver's textual model reply into a ``Model``.

    Accepts the ``(model (define-fun x () S v) ...)`` form, a bare list of
    ``define-fun`` commands, and the ``get-value`` reply ``((x v) ...)``.
    """
    s = text.decode("utf-8") if isinstance(text, (bytes, bytearray)) else text
    out: Model = {}
    for top in sexpr.parse(s):
        if not isinstance(top, list) or not top:
            continue
        if top[0] == "model":
            for c in top[1:]:
                _read_define(c, out)
        elif top[0] == "define-fun":
            _read_define(top, out)
        else:  # get-value form: ((term value) ...)
            for pair in top:
                if (isinstance(pair, list) and len(pair) == 2
                        and isinstance(pair[0], str)):
                    v = _read_value(pair[1])
                    if v is not None:
                        out[pair[0]] = v
    return out
