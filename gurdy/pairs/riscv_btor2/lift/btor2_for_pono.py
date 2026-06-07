"""Canonicalize a hurdy-gurdy BTOR2 model for Pono v2.0.0's parser, plus
helpers for translating Pono's ``--show-invar`` output back into the
checker's ``s_<nid>``-named SMT-LIB form.

The canonicalizer:

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

The invariant helpers:

Pono's ``--show-invar`` prints ``INVAR: <smt-lib>`` to stderr, using
``state<nid>`` references where ``<nid>`` is the BTOR2 node id of the
state. ``build_invariant_smtlib`` translates that to the ``s_<nid>``
naming the certificate checker expects and prepends the required
``(declare-const ...)`` block.
"""

from __future__ import annotations

import re

from gurdy.core.btor2.nodes import Model, Node
from gurdy.core.btor2.parser import from_text
from gurdy.core.btor2.printer import to_text
from gurdy.core.btor2._bmc import Compiled, find_sort_for


# Pono engines that emit invariants under ``--show-invar``. ``ic3bits`` and
# ``mbic3`` don't support arrays (we have memory). ``ind`` proves but
# doesn't expose the invariant. ``ic3sa`` is the workhorse for hurdy-gurdy.
INVARIANT_ENGINES = frozenset({"ic3sa", "ic3ia"})

INVAR_RE = re.compile(r"^INVAR:\s*(.+)$", re.MULTILINE)
_STATE_REF_RE = re.compile(r"\bstate(\d+)\b")


def _sort_sexpr(sort_nid: int, comp: Compiled) -> str:
    if sort_nid in comp.sort_widths:
        return f"(_ BitVec {comp.sort_widths[sort_nid]})"
    if sort_nid in comp.array_meta:
        idx_s, elt_s = comp.array_meta[sort_nid]
        return (
            f"(Array (_ BitVec {comp.sort_widths[idx_s]}) "
            f"(_ BitVec {comp.sort_widths[elt_s]}))"
        )
    raise ValueError(f"unknown sort nid {sort_nid}")


def build_invariant_smtlib(invar_body: str, comp: Compiled) -> str:
    """Translate Pono's invariant body into our SMT-LIB+s_<nid> form."""
    state_nid_set = set(comp.state_nids)

    def _sub(m: re.Match[str]) -> str:
        nid = int(m.group(1))
        if nid not in state_nid_set:
            raise ValueError(
                f"INVAR references state{nid} but nid {nid} is not a state "
                f"in the canonical model (states: {sorted(state_nid_set)})"
            )
        return f"s_{nid}"

    body = _STATE_REF_RE.sub(_sub, invar_body)
    decls = [
        f"(declare-const s_{nid} {_sort_sexpr(find_sort_for(nid, comp), comp)})"
        for nid in comp.state_nids
    ]
    return "\n".join(decls) + "\n(assert " + body + ")\n"


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


__all__ = [
    "INVARIANT_ENGINES",
    "INVAR_RE",
    "build_invariant_smtlib",
    "canonicalize_for_pono",
]
