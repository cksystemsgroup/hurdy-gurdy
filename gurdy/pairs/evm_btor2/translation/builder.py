"""BTOR2 model builder for the evm-btor2 translator (SCHEMA.md §2–§3).

``Btor2Builder`` appends nodes to a ``Model`` and returns nids.
Sort-name resolution is centralized in ``EVM_SORT_TABLE`` so all
translation layers share the same canonical sort nids.

``emit_header()`` declares the six bitvec sorts and three array sorts
from SCHEMA.md §2.  ``emit_machine_states()`` declares all thirteen
state variables from SCHEMA.md §3.1 and §3.2 (returning their nids
keyed by the SCHEMA symbol name so downstream layers can reference
them without scanning the model).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gurdy.pairs.evm_btor2.btor2.nodes import (
    ArraySort,
    BitvecSort,
    Comment,
    Model,
    Node,
)


# ---------------------------------------------------------------------------
# Sort catalogue (SCHEMA.md §2)
# ---------------------------------------------------------------------------

EVM_BITVEC_SORTS: tuple[tuple[str, int], ...] = (
    ("bv1",   1),
    ("bv8",   8),
    ("bv10",  10),
    ("bv16",  16),
    ("bv64",  64),
    ("bv256", 256),
)

# (name, index_sort_name, element_sort_name)
EVM_ARRAY_SORTS: tuple[tuple[str, str, str], ...] = (
    ("stack_t", "bv10",  "bv256"),
    ("mem_t",   "bv256", "bv8"),
    ("sto_t",   "bv256", "bv256"),
)

# ---------------------------------------------------------------------------
# Machine-state variable catalogue (SCHEMA.md §3.1 + §3.2)
# ---------------------------------------------------------------------------

# (symbol, sort_name)
MACHINE_STATE_VARS: tuple[tuple[str, str], ...] = (
    ("sp",             "bv10"),
    ("stack",          "stack_t"),
    ("mem",            "mem_t"),
    ("mem_words",      "bv256"),
    ("sto",            "sto_t"),
    ("pc",             "bv16"),
    ("gas",            "bv64"),
    ("trap",           "bv1"),
    ("halted",         "bv1"),
    ("returndata",     "mem_t"),
    ("returndatasize", "bv256"),
    ("sto_warm",       "sto_t"),   # §3.2 warm-slot tracking
)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


@dataclass
class Btor2Builder:
    """Ergonomic BTOR2 node emitter for the evm-btor2 translator.

    All methods return the nid of the emitted (or previously cached)
    node.  Sort declarations are idempotent — the same canonical name
    always returns the same nid within a builder instance.
    """

    model: Model = field(default_factory=Model)
    sort_nids: dict[str, int] = field(default_factory=dict)
    """Symbolic sort name → nid."""

    state_nids: dict[str, int] = field(default_factory=dict)
    """Machine-state symbol → nid (populated by emit_machine_states)."""

    constants: dict[tuple[str, int], int] = field(default_factory=dict)
    """Cache of (sort_name, value) → nid for emitted constants."""

    next_nid: int = 1

    # ------------------------------------------------------------------
    # NID allocation
    # ------------------------------------------------------------------

    def _alloc(self) -> int:
        n = self.next_nid
        self.next_nid += 1
        return n

    # ------------------------------------------------------------------
    # Sort declarations
    # ------------------------------------------------------------------

    def declare_sort(self, name: str) -> int:
        """Declare a bitvec sort by canonical name.  Emits a node only
        the first time; subsequent calls return the cached nid.

        Names of the form ``bv<N>`` are created on demand for any
        positive integer ``N`` — necessary for intermediate widths
        produced by concat/slice during lowering.
        """
        if name in self.sort_nids:
            return self.sort_nids[name]
        if name.startswith("bv") and name[2:].isdigit():
            width = int(name[2:])
            if width <= 0:
                raise ValueError(f"invalid bitvec width in {name!r}")
            sort: BitvecSort | ArraySort = BitvecSort(width)
        else:
            raise KeyError(f"unknown sort name {name!r}; use declare_array_sort for arrays")
        nid = self._alloc()
        self.model.append(Node(nid=nid, op="sort", sort=sort, symbol=name))
        self.sort_nids[name] = nid
        return nid

    def declare_array_sort(self, name: str, idx: str, elt: str) -> int:
        """Declare an array sort.  ``idx`` and ``elt`` are bitvec sort
        names declared (or auto-declared) on demand."""
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
        return nid

    # ------------------------------------------------------------------
    # Header (SCHEMA.md §2)
    # ------------------------------------------------------------------

    def emit_header(self) -> dict[str, int]:
        """Emit all sort declarations for SCHEMA.md §2.

        Declares the six bitvec sorts (bv1, bv8, bv10, bv16, bv64,
        bv256) and the three array sorts (stack_t, mem_t, sto_t) in
        the order the schema defines them.  Returns ``sort_nids``.
        """
        self.comment("sorts — SCHEMA.md §2")
        for name, width in EVM_BITVEC_SORTS:
            self.declare_sort(name)
        for name, idx, elt in EVM_ARRAY_SORTS:
            self.declare_array_sort(name, idx, elt)
        return dict(self.sort_nids)

    # ------------------------------------------------------------------
    # Machine-state declarations (SCHEMA.md §3.1 + §3.2)
    # ------------------------------------------------------------------

    def emit_machine_states(self) -> dict[str, int]:
        """Emit state variable declarations for SCHEMA.md §3.1 and §3.2.

        Requires ``emit_header()`` to have been called first so all
        sorts are already declared.  Returns ``state_nids`` (symbol →
        nid) for use by downstream translation layers.
        """
        self.comment("machine state — SCHEMA.md §3.1 + §3.2")
        for sym, sort_name in MACHINE_STATE_VARS:
            sort_nid = self.sort_nids[sort_name]
            nid = self._alloc()
            self.model.append(
                Node(nid=nid, op="state", args=[str(sort_nid)], symbol=sym)
            )
            self.state_nids[sym] = nid
        return dict(self.state_nids)

    # ------------------------------------------------------------------
    # Constants
    # ------------------------------------------------------------------

    def const(self, sort: str, value: int) -> int:
        """Emit a constant (cached).  Uses ``zero``/``one``/``constd``."""
        key = (sort, value)
        if key in self.constants:
            return self.constants[key]
        sort_nid = self.declare_sort(sort)
        if value == 0:
            op, args = "zero", [str(sort_nid)]
        elif value == 1:
            op, args = "one", [str(sort_nid)]
        else:
            op, args = "constd", [str(sort_nid), str(value)]
        nid = self._alloc()
        self.model.append(Node(nid=nid, op=op, args=args))
        self.constants[key] = nid
        return nid

    def ones(self, sort: str) -> int:
        sort_nid = self.declare_sort(sort)
        nid = self._alloc()
        self.model.append(Node(nid=nid, op="ones", args=[str(sort_nid)]))
        return nid

    # ------------------------------------------------------------------
    # Generic node emission
    # ------------------------------------------------------------------

    def emit(self, op: str, sort: str, *args: int, symbol: str | None = None) -> int:
        """Emit an op that carries a sort prefix.  Returns the new nid."""
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
        return nid

    def emit_no_sort(self, op: str, *args: int, symbol: str | None = None) -> int:
        """Emit a node without a sort prefix (state, init, next, bad, …)."""
        nid = self._alloc()
        self.model.append(
            Node(nid=nid, op=op, args=[str(a) for a in args], symbol=symbol)
        )
        return nid

    def comment(self, text: str = "") -> None:
        self.model.append(Comment(text=text))

    # ------------------------------------------------------------------
    # Arithmetic / logical helpers
    # ------------------------------------------------------------------

    def add(self, sort: str, a: int, b: int) -> int:
        return self.emit("add", sort, a, b)

    def sub(self, sort: str, a: int, b: int) -> int:
        return self.emit("sub", sort, a, b)

    def mul(self, sort: str, a: int, b: int) -> int:
        return self.emit("mul", sort, a, b)

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

    def sll(self, sort: str, a: int, b: int) -> int:
        return self.emit("sll", sort, a, b)

    def srl(self, sort: str, a: int, b: int) -> int:
        return self.emit("srl", sort, a, b)

    def sra(self, sort: str, a: int, b: int) -> int:
        return self.emit("sra", sort, a, b)

    def udiv(self, sort: str, a: int, b: int) -> int:
        return self.emit("udiv", sort, a, b)

    def urem(self, sort: str, a: int, b: int) -> int:
        return self.emit("urem", sort, a, b)

    def sdiv(self, sort: str, a: int, b: int) -> int:
        return self.emit("sdiv", sort, a, b)

    def srem(self, sort: str, a: int, b: int) -> int:
        return self.emit("srem", sort, a, b)

    # Comparisons → bv1.
    def eq(self, a: int, b: int) -> int:
        return self.emit("eq", "bv1", a, b)

    def neq(self, a: int, b: int) -> int:
        return self.emit("neq", "bv1", a, b)

    def ult(self, a: int, b: int) -> int:
        return self.emit("ult", "bv1", a, b)

    def ule(self, a: int, b: int) -> int:
        return self.emit("ulte", "bv1", a, b)

    def ugt(self, a: int, b: int) -> int:
        return self.emit("ugt", "bv1", a, b)

    def uge(self, a: int, b: int) -> int:
        return self.emit("ugte", "bv1", a, b)

    def slt(self, a: int, b: int) -> int:
        return self.emit("slt", "bv1", a, b)

    def sgt(self, a: int, b: int) -> int:
        return self.emit("sgt", "bv1", a, b)

    def ite(self, sort: str, c: int, a: int, b: int) -> int:
        return self.emit("ite", sort, c, a, b)

    def uext(self, target_sort: str, a: int, extra_bits: int) -> int:
        sort_nid = self.declare_sort(target_sort)
        nid = self._alloc()
        self.model.append(
            Node(nid=nid, op="uext", args=[str(sort_nid), str(a), str(extra_bits)])
        )
        return nid

    def sext(self, target_sort: str, a: int, extra_bits: int) -> int:
        sort_nid = self.declare_sort(target_sort)
        nid = self._alloc()
        self.model.append(
            Node(nid=nid, op="sext", args=[str(sort_nid), str(a), str(extra_bits)])
        )
        return nid

    def slice(self, target_sort: str, a: int, hi: int, lo: int) -> int:
        sort_nid = self.declare_sort(target_sort)
        nid = self._alloc()
        self.model.append(
            Node(nid=nid, op="slice", args=[str(sort_nid), str(a), str(hi), str(lo)])
        )
        return nid

    def concat(self, target_sort: str, a: int, b: int) -> int:
        return self.emit("concat", target_sort, a, b)

    # ------------------------------------------------------------------
    # Array ops
    # ------------------------------------------------------------------

    def read(self, target_sort: str, array: int, index: int) -> int:
        return self.emit("read", target_sort, array, index)

    def write(self, array_sort: str, array: int, index: int, value: int) -> int:
        return self.emit("write", array_sort, array, index, value)

    # ------------------------------------------------------------------
    # Transition-system wiring
    # ------------------------------------------------------------------

    def state(self, sort: str, symbol: str) -> int:
        sort_nid = self.sort_nids.get(sort) or self.declare_sort(sort)
        nid = self._alloc()
        self.model.append(Node(nid=nid, op="state", args=[str(sort_nid)], symbol=symbol))
        return nid

    def init(self, sort: str, state_nid: int, value_nid: int) -> int:
        sort_nid = self.sort_nids.get(sort) or self.declare_sort(sort)
        return self.emit_no_sort("init", sort_nid, state_nid, value_nid)

    def next(self, sort: str, state_nid: int, next_nid: int) -> int:
        sort_nid = self.sort_nids.get(sort) or self.declare_sort(sort)
        return self.emit_no_sort("next", sort_nid, state_nid, next_nid)

    def bad(self, expr_nid: int) -> int:
        return self.emit_no_sort("bad", expr_nid)

    def constraint(self, expr_nid: int) -> int:
        return self.emit_no_sort("constraint", expr_nid)


__all__ = [
    "Btor2Builder",
    "EVM_BITVEC_SORTS",
    "EVM_ARRAY_SORTS",
    "MACHINE_STATE_VARS",
]
