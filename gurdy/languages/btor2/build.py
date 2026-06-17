"""A small BTOR2 builder — emits canonical BTOR2 a pair's translator can
assemble (the btor2 language owns its model + I/O, so every BTOR2-targeting
pair reuses this rather than re-implementing node emission).

Allocates monotonically increasing node ids (so refs always point backward,
as BTOR2 and the evaluator require) and prints canonical lines that round-trip
through ``model.from_text`` / ``model.to_text``.
"""

from __future__ import annotations


class Builder:
    def __init__(self) -> None:
        self._lines: list[tuple[int, str, tuple[str, ...], str | None]] = []
        self._id = 0
        self._bv_sorts: dict[int, int] = {}             # width -> sort node id
        self._array_sorts: dict[tuple[int, int], int] = {}  # (idx_w, elem_w) -> sort id
        self.width: dict[int, int] = {}                  # bv node id -> width
        self.array_of: dict[int, tuple[int, int]] = {}   # array node id -> (idx_w, elem_w)

    def _emit(self, kind: str, fields: tuple, symbol: str | None = None,
              width: int | None = None) -> int:
        self._id += 1
        nid = self._id
        self._lines.append((nid, kind, tuple(str(f) for f in fields), symbol))
        if width is not None:
            self.width[nid] = width
        return nid

    # sorts
    def bv(self, w: int) -> int:
        if w not in self._bv_sorts:
            self._bv_sorts[w] = self._emit("sort", ("bitvec", w))
        return self._bv_sorts[w]

    def array_sort(self, idx_w: int, elem_w: int) -> int:
        key = (idx_w, elem_w)
        if key not in self._array_sorts:
            self._array_sorts[key] = self._emit(
                "sort", ("array", self.bv(idx_w), self.bv(elem_w))
            )
        return self._array_sorts[key]

    # constants
    def constd(self, w: int, v: int) -> int:
        return self._emit("constd", (self.bv(w), int(v) % (1 << w)), width=w)

    def zero(self, w: int) -> int:
        return self._emit("zero", (self.bv(w),), width=w)

    def one(self, w: int) -> int:
        return self._emit("one", (self.bv(w),), width=w)

    # state
    def state(self, w: int, name: str) -> int:
        return self._emit("state", (self.bv(w),), symbol=name, width=w)

    def state_array(self, idx_w: int, elem_w: int, name: str) -> int:
        nid = self._emit("state", (self.array_sort(idx_w, elem_w),), symbol=name)
        self.array_of[nid] = (idx_w, elem_w)
        return nid

    def init(self, state: int, val: int) -> int:
        return self._emit("init", (self.bv(self.width[state]), state, val))

    def next(self, state: int, val: int) -> int:
        return self._emit("next", (self.bv(self.width[state]), state, val))

    def next_array(self, state: int, val: int) -> int:
        idx_w, elem_w = self.array_of[state]
        return self._emit("next", (self.array_sort(idx_w, elem_w), state, val))

    # bit-vector operators
    def op2(self, name: str, w: int, a: int, b: int) -> int:
        return self._emit(name, (self.bv(w), a, b), width=w)

    def op1(self, name: str, w: int, a: int) -> int:
        return self._emit(name, (self.bv(w), a), width=w)

    def ite(self, w: int, c: int, a: int, b: int) -> int:
        return self._emit("ite", (self.bv(w), c, a, b), width=w)

    def ite_array(self, idx_w: int, elem_w: int, c: int, a: int, b: int) -> int:
        nid = self._emit("ite", (self.array_sort(idx_w, elem_w), c, a, b))
        self.array_of[nid] = (idx_w, elem_w)
        return nid

    def slice(self, arg: int, upper: int, lower: int) -> int:
        w = upper - lower + 1
        return self._emit("slice", (self.bv(w), arg, upper, lower), width=w)

    def sext(self, w_result: int, arg: int, n: int) -> int:
        return self._emit("sext", (self.bv(w_result), arg, n), width=w_result)

    def uext(self, w_result: int, arg: int, n: int) -> int:
        return self._emit("uext", (self.bv(w_result), arg, n), width=w_result)

    # arrays
    def read(self, elem_w: int, arr: int, idx: int) -> int:
        return self._emit("read", (self.bv(elem_w), arr, idx), width=elem_w)

    def write(self, idx_w: int, elem_w: int, arr: int, idx: int, val: int) -> int:
        nid = self._emit("write", (self.array_sort(idx_w, elem_w), arr, idx, val))
        self.array_of[nid] = (idx_w, elem_w)
        return nid

    def bad(self, nid: int) -> int:
        return self._emit("bad", (nid,))

    def _raw_text(self) -> str:
        out = []
        for nid, kind, fields, symbol in self._lines:
            parts = [str(nid), kind, *fields]
            if symbol:
                parts.append(symbol)
            out.append(" ".join(parts))
        return "\n".join(out) + "\n"

    def to_text(self) -> str:
        # Renumber into the node order native checkers (pono/btormc) require:
        # an ``init`` value must precede its state. The builder allocates states
        # before their init constants, so emit through ``canonicalize`` -- the
        # z3 bridge tolerates either order, native checkers do not. (Deferred
        # import: model.py parses what we emit; keep the dependency one-way.)
        from .model import canonicalize

        return canonicalize(self._raw_text())
