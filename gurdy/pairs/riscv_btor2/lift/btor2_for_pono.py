"""Canonicalize a hurdy-gurdy BTOR2 model for Pono v2.0.0's parser.

Pono enforces a stricter ordering than the BTOR2 standard: for every
``init <sort> <state> <value>`` line, ``nid(state)`` must be greater
than ``nid(value)``. Hurdy-gurdy's emitter declares ``state`` nodes
early (right after sorts) and the ``constd`` values used to initialize
them later in the dispatch/init layer, so the constraint is often
violated.

The fix is a topological renumber: reorder Nodes such that for every
``init S V`` the value V comes before the state S, then assign fresh
sequential nids and substitute references.

The canonicalized model is semantically equivalent to the original
(same sorts, states, transitions, constraints, bads), just with
different nids and a different in-file ordering. The standard BTOR2
spec allows this, so other tools (z3-bmc, bitwuzla, cvc5) accept the
canonicalized form too.
"""

from __future__ import annotations

from gurdy.pairs.riscv_btor2.btor2.nodes import Model, Node
from gurdy.pairs.riscv_btor2.btor2.parser import from_text
from gurdy.pairs.riscv_btor2.btor2.printer import to_text


# Ops whose numeric args (after args[0]=sort_nid) are integer LITERALS,
# not nid references.
_CONST_OPS = {"const", "constd", "consth", "ones", "zero", "one"}


def _operand_nids(node: Node) -> list[int]:
    """Return the nids referenced by this node's args.

    Sort node refs (when applicable) are included so the renumber
    respects dependencies on sorts too. Literal values for const-family
    ops are excluded.
    """
    if node.op == "sort":
        # Array sorts reference two sort nids; bitvec sorts reference none.
        if node.args and node.args[0] == "array":
            return [int(node.args[1]), int(node.args[2])]
        return []
    if node.op in _CONST_OPS:
        # args[0] is the sort nid; the rest are decimal/hex/bit literals.
        return [int(node.args[0])] if node.args else []
    # Generic case: every arg is a nid reference. (We skip the trailing
    # ``symbol`` field — that's a separate attribute, not in ``args``.)
    return [int(a) for a in node.args]


def _rewrite_args(node: Node, renumber: dict[int, int]) -> None:
    """Replace nid references in-place using ``renumber``."""
    if node.op == "sort":
        if node.args and node.args[0] == "array":
            node.args[1] = str(renumber[int(node.args[1])])
            node.args[2] = str(renumber[int(node.args[2])])
        return
    if node.op in _CONST_OPS:
        if node.args:
            node.args[0] = str(renumber[int(node.args[0])])
        return
    for i, a in enumerate(node.args):
        node.args[i] = str(renumber[int(a)])


def canonicalize_for_pono(model_text: str) -> bytes:
    """Reorder + renumber a BTOR2 model so Pono v2.0.0 accepts it."""
    parsed = from_text(model_text)
    nodes = parsed.model.nodes()  # in original order
    by_nid = {n.nid: n for n in nodes}

    # Build edges: for each node, every operand must precede it.
    successors: dict[int, list[int]] = {n.nid: [] for n in nodes}
    indeg: dict[int, int] = {n.nid: 0 for n in nodes}

    def _add_edge(src: int, dst: int) -> None:
        successors[src].append(dst)
        indeg[dst] += 1

    for n in nodes:
        for op in _operand_nids(n):
            if op in by_nid:
                _add_edge(op, n.nid)

    # Extra edge for Pono: in `init S V`, V must precede S.
    # (Operands already give us S→init and V→init; we additionally need
    # V→S so the *state* node appears after the *value* node.)
    for n in nodes:
        if n.op == "init" and len(n.args) >= 3:
            state_nid = int(n.args[1])
            value_nid = int(n.args[2])
            if state_nid in by_nid and value_nid in by_nid:
                _add_edge(value_nid, state_nid)

    # Kahn's algorithm — pick ready nodes in original order to keep the
    # file shape close to the input.
    original_order = {n.nid: i for i, n in enumerate(nodes)}
    ready = sorted([n.nid for n in nodes if indeg[n.nid] == 0],
                   key=lambda x: original_order[x])
    new_order: list[int] = []
    while ready:
        cur = ready.pop(0)
        new_order.append(cur)
        for s in successors[cur]:
            indeg[s] -= 1
            if indeg[s] == 0:
                ready.append(s)
        ready.sort(key=lambda x: original_order[x])

    if len(new_order) != len(nodes):
        raise ValueError(
            f"topological order incomplete: {len(new_order)}/{len(nodes)} — "
            "model has a cycle?"
        )

    # Assign fresh sequential nids 1..N in the new order.
    renumber = {old: new for new, old in enumerate(new_order, start=1)}

    # Build a fresh Model containing only the renumbered nodes
    # (drop standalone comments — they're informational and Pono is happy
    # without them).
    out = Model()
    for old_nid in new_order:
        n = by_nid[old_nid]
        new_node = Node(
            nid=renumber[old_nid],
            op=n.op,
            args=list(n.args),
            symbol=n.symbol,
            inline_comment="",
            sort=n.sort,
        )
        _rewrite_args(new_node, renumber)
        out.append(new_node)

    return to_text(out).encode("utf-8")


__all__ = ["canonicalize_for_pono"]
