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
        self._sorts: dict[int, int] = {}   # bitvec width -> sort node id
        self.width: dict[int, int] = {}     # value node id -> bitvec width

    def _emit(self, kind: str, fields: tuple, symbol: str | None = None,
              width: int | None = None) -> int:
        self._id += 1
        nid = self._id
        self._lines.append((nid, kind, tuple(str(f) for f in fields), symbol))
        if width is not None:
            self.width[nid] = width
        return nid

    def bv(self, w: int) -> int:
        if w not in self._sorts:
            self._sorts[w] = self._emit("sort", ("bitvec", w))
        return self._sorts[w]

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

    def init(self, state: int, val: int) -> int:
        return self._emit("init", (self.bv(self.width[state]), state, val))

    def next(self, state: int, val: int) -> int:
        return self._emit("next", (self.bv(self.width[state]), state, val))

    # operators
    def op2(self, name: str, w: int, a: int, b: int) -> int:
        return self._emit(name, (self.bv(w), a, b), width=w)

    def op1(self, name: str, w: int, a: int) -> int:
        return self._emit(name, (self.bv(w), a), width=w)

    def ite(self, w: int, c: int, a: int, b: int) -> int:
        return self._emit("ite", (self.bv(w), c, a, b), width=w)

    def bad(self, nid: int) -> int:
        return self._emit("bad", (nid,))

    def to_text(self) -> str:
        out = []
        for nid, kind, fields, symbol in self._lines:
            parts = [str(nid), kind, *fields]
            if symbol:
                parts.append(symbol)
            out.append(" ".join(parts))
        return "\n".join(out) + "\n"
