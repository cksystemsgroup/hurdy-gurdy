"""BTOR2 node-construction helpers for the wasm-btor2 pair.

Adapted from the riscv-btor2 reference at
``gurdy.pairs.riscv_btor2.translation.builder``; imports target the
wasm-specific btor2 subpackage at ``gurdy.pairs.wasm_btor2.btor2.*``.
bv16 is added to SORT_TABLE for the PC register.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gurdy.pairs.wasm_btor2.btor2.nodes import (
    ArraySort,
    BitvecSort,
    Comment,
    Model,
    Node,
)


SORT_TABLE: dict[str, BitvecSort | ArraySort] = {
    "bv1": BitvecSort(1),
    "bv8": BitvecSort(8),
    "bv16": BitvecSort(16),
    "bv32": BitvecSort(32),
    "bv64": BitvecSort(64),
}


@dataclass
class Builder:
    model: Model = field(default_factory=Model)
    sort_nids: dict[str, int] = field(default_factory=dict)
    constants: dict[tuple[str, int], int] = field(default_factory=dict)
    _sort_name_by_nid: dict[int, str] = field(default_factory=dict)
    _nid_sort: dict[int, str] = field(default_factory=dict)
    next_nid: int = 1

    def _alloc(self) -> int:
        n = self.next_nid
        self.next_nid += 1
        return n

    # ---- sorts ----

    def declare_sort(self, name: str) -> int:
        if name in self.sort_nids:
            return self.sort_nids[name]
        if name in SORT_TABLE:
            sort = SORT_TABLE[name]
        elif name.startswith("bv") and name[2:].isdigit():
            width = int(name[2:])
            if width <= 0:
                raise ValueError(f"invalid bitvec width in {name!r}")
            sort = BitvecSort(width)
        else:
            raise KeyError(name)
        nid = self._alloc()
        self.model.append(Node(nid=nid, op="sort", sort=sort, symbol=name))
        self.sort_nids[name] = nid
        self._sort_name_by_nid[nid] = name
        return nid

    def declare_array_sort(self, name: str, idx: str, elt: str) -> int:
        if name in self.sort_nids:
            return self.sort_nids[name]
        i = self.declare_sort(idx)
        e = self.declare_sort(elt)
        nid = self._alloc()
        self.model.append(
            Node(
                nid=nid,
                op="sort",
                sort=ArraySort(index_sort_nid=i, element_sort_nid=e),
                symbol=name,
            )
        )
        self.sort_nids[name] = nid
        self._sort_name_by_nid[nid] = name
        return nid

    # ---- constants ----

    def const(self, sort: str, value: int) -> int:
        key = (sort, value)
        if key in self.constants:
            return self.constants[key]
        sort_nid = self.declare_sort(sort)
        if value == 0:
            op = "zero"
            args: list[str] = [str(sort_nid)]
        elif value == 1:
            op = "one"
            args = [str(sort_nid)]
        else:
            op = "constd"
            args = [str(sort_nid), str(value)]
        nid = self._alloc()
        self.model.append(Node(nid=nid, op=op, args=args))
        self.constants[key] = nid
        self._nid_sort[nid] = sort
        return nid

    def ones(self, sort: str) -> int:
        sort_nid = self.declare_sort(sort)
        nid = self._alloc()
        self.model.append(Node(nid=nid, op="ones", args=[str(sort_nid)]))
        self._nid_sort[nid] = sort
        return nid

    # ---- generic node emission ----

    def emit(self, op: str, sort: str, *args: int, symbol: str | None = None) -> int:
        sort_nid = self.declare_sort(sort)
        nid = self._alloc()
        self.model.append(
            Node(
                nid=nid,
                op=op,
                args=[str(sort_nid), *(str(a) for a in args)],
                symbol=symbol,
            )
        )
        self._nid_sort[nid] = sort
        return nid

    def emit_no_sort(self, op: str, *args: int, symbol: str | None = None) -> int:
        nid = self._alloc()
        self.model.append(
            Node(
                nid=nid,
                op=op,
                args=[str(a) for a in args],
                symbol=symbol,
            )
        )
        if op in ("state", "input", "output") and args:
            name = self._sort_name_by_nid.get(args[0])
            if name is not None:
                self._nid_sort[nid] = name
        return nid

    def sort_of_nid(self, nid: int) -> str | None:
        return self._nid_sort.get(nid)

    def comment(self, text: str = "") -> None:
        self.model.append(Comment(text=text))

    # ---- arithmetic / logical helpers ----

    def add(self, sort: str, a: int, b: int) -> int:
        return self.emit("add", sort, a, b)

    def sub(self, sort: str, a: int, b: int) -> int:
        return self.emit("sub", sort, a, b)

    def and_(self, sort: str, a: int, b: int) -> int:
        return self.emit("and", sort, a, b)

    def or_(self, sort: str, a: int, b: int) -> int:
        return self.emit("or", sort, a, b)

    def xor(self, sort: str, a: int, b: int) -> int:
        return self.emit("xor", sort, a, b)

    def not_(self, sort: str, a: int) -> int:
        return self.emit("not", sort, a)

    def neg(self, sort: str, a: int) -> int:
        return self.emit("neg", sort, a)

    def mul(self, sort: str, a: int, b: int) -> int:
        return self.emit("mul", sort, a, b)

    def udiv(self, sort: str, a: int, b: int) -> int:
        return self.emit("udiv", sort, a, b)

    def sdiv(self, sort: str, a: int, b: int) -> int:
        return self.emit("sdiv", sort, a, b)

    def urem(self, sort: str, a: int, b: int) -> int:
        return self.emit("urem", sort, a, b)

    def srem(self, sort: str, a: int, b: int) -> int:
        return self.emit("srem", sort, a, b)

    # comparisons return bv1
    def eq(self, a: int, b: int) -> int:
        return self.emit("eq", "bv1", a, b)

    def neq(self, a: int, b: int) -> int:
        return self.emit("neq", "bv1", a, b)

    def slt(self, a: int, b: int) -> int:
        return self.emit("slt", "bv1", a, b)

    def ult(self, a: int, b: int) -> int:
        return self.emit("ult", "bv1", a, b)

    def ite(self, sort: str, c: int, a: int, b: int) -> int:
        return self.emit("ite", sort, c, a, b)

    def sext(self, target_sort: str, a: int, extra_bits: int) -> int:
        sort_nid = self.declare_sort(target_sort)
        nid = self._alloc()
        self.model.append(
            Node(nid=nid, op="sext", args=[str(sort_nid), str(a), str(extra_bits)])
        )
        self._nid_sort[nid] = target_sort
        return nid

    def uext(self, target_sort: str, a: int, extra_bits: int) -> int:
        sort_nid = self.declare_sort(target_sort)
        nid = self._alloc()
        self.model.append(
            Node(nid=nid, op="uext", args=[str(sort_nid), str(a), str(extra_bits)])
        )
        self._nid_sort[nid] = target_sort
        return nid

    # ---- array ops ----

    def read(self, target_sort: str, array: int, index: int) -> int:
        return self.emit("read", target_sort, array, index)

    def write(self, target_sort: str, array: int, index: int, value: int) -> int:
        return self.emit("write", target_sort, array, index, value)


__all__ = ["Builder", "SORT_TABLE"]
