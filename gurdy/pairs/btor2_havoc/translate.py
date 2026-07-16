"""The ``btor2-havoc`` translator — localization abstraction over BTOR2.

Input: ``{"system": <BTOR2 text/bytes>, "havoc": <state symbols or ids>}``.
For each named state the translator deletes the state's ``next`` line and
appends a fresh ``input`` (symbol ``havoc_<label>``) plus a ``next`` feeding
that input to the state — the state's update becomes unconstrained while its
``init`` (if any) and every other *live* line are preserved verbatim. Value
nodes that only the deleted ``next`` lines referenced are swept (v0.2): the
whole point of localization is that the abstraction *ships without* the
update logic it freed, so leaving the orphaned expression trees in the
emission would hand every downstream encoder — the SMT bridge unrolls each
value node per step — the very cost the havoc removed (surfaced by the
abstraction benchmark's artifact measurements). Sorts, states, inputs, and
every remaining directive are kept verbatim; the sweep never changes a
trace row. The result is
an **over-approximation**: every behavior of the source system is a behavior
of the abstraction (drive each fresh input with the value the deleted next
function would have produced — exactly the pair's witness embedding).

The havoc set is a **caller parameter**, never a heuristic: which states to
abstract is the player's refinement decision (ARCHITECTURE.md §4 — a choice a
translator would otherwise make heuristically becomes a parameter). Entries
are resolved deterministically, processed in ascending state-id order, and
fresh ids are assigned sequentially past the largest existing id, so the
output bytes are a pure function of the input.

Array-sorted states are out of scope (typed ``Unsupported``): the shared
BTOR2 interpreter has no array-valued inputs. An unknown state name is a
caller error (``ValueError``), not a coverage gap.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.model import Bitvec, Node, System, from_text

__all__ = ["translate", "havoc_plan"]


def _text(system: Any) -> str:
    if isinstance(system, (bytes, bytearray)):
        return system.decode("utf-8")
    return str(system)


def _label(node: Node) -> str:
    return node.symbol or f"n{node.id}"


def _resolve(sys: System, havoc: Any) -> list[Node]:
    """Resolve havoc entries (state symbols or ids) to state nodes, deduped,
    in ascending state-id order."""
    by_label = {_label(s): s for s in sys.states()}
    chosen: dict[int, Node] = {}
    for entry in tuple(havoc or ()):
        if isinstance(entry, int):
            node = sys.nodes.get(entry)
            if node is None or node.op != "state":
                raise ValueError(f"btor2-havoc: no state with id {entry}")
        else:
            node = by_label.get(str(entry))
            if node is None:
                raise ValueError(f"btor2-havoc: no such state: {entry!r}")
        if not isinstance(sys.sorts.get(node.sort), Bitvec):
            raise Unsupported("btor2-havoc", "havoc.array-state")
        chosen[node.id] = node
    return [chosen[i] for i in sorted(chosen)]


def _max_id(text: str) -> int:
    top = 0
    for line in text.split("\n"):
        toks = line.split()
        if toks and toks[0].isdigit():
            top = max(top, int(toks[0]))
    return top


def havoc_plan(program: dict[str, Any]) -> tuple[System, str, list[tuple[Node, int, int]]]:
    """The deterministic rewrite plan: the parsed source system, its text, and
    per havocked state the fresh ``(input id, next id)``. Shared by the
    translator and the witness embedding so the embedding never depends on the
    (possibly mutated) translator output."""
    text = _text(program["system"])
    sys = from_text(text)
    states = _resolve(sys, program.get("havoc", ()))
    base = _max_id(text) + 1
    plan = [(s, base + 2 * i, base + 2 * i + 1) for i, s in enumerate(states)]
    return sys, text, plan


_DIRECTIVES = ("init", "next", "bad", "constraint", "output")
_INTERFACE = ("state", "input")


def _live_ids(sys: System, havoc_ids: set[int]) -> set[int]:
    """The node ids still referenced once the havocked states' ``next``
    lines are gone: every remaining directive's operands, closed
    transitively through value-node references (``abs``: a negated
    reference reads the same node). States and inputs are interface and
    always live."""
    live: set[int] = set()
    stack: list[int] = []
    for n in sys.nodes.values():
        if n.op in _INTERFACE:
            live.add(n.id)
        elif n.op in _DIRECTIVES:
            if n.op == "next" and n.refs and n.refs[0] in havoc_ids:
                continue  # this directive is being deleted
            stack.extend(abs(r) for r in n.refs)
    while stack:
        nid = stack.pop()
        if nid in live or nid not in sys.nodes:
            continue
        live.add(nid)
        node = sys.nodes[nid]
        if node.op not in _INTERFACE:
            stack.extend(abs(r) for r in node.refs)
    return live


def translate(program: dict[str, Any]) -> bytes:
    sys, text, plan = havoc_plan(program)
    if not plan:  # empty havoc set: the identity rewrite
        return text.encode("utf-8")
    havoc_ids = {s.id for s, _, _ in plan}
    live = _live_ids(sys, havoc_ids)
    kept: list[str] = []
    for line in text.split("\n"):
        toks = line.split()
        if (len(toks) >= 4 and toks[1] == "next" and toks[3].isdigit()
                and int(toks[3]) in havoc_ids):
            continue
        if toks and toks[0].isdigit() and len(toks) >= 2:
            nid, op = int(toks[0]), toks[1]
            if (op not in _INTERFACE and op not in _DIRECTIVES
                    and op != "sort" and nid in sys.nodes
                    and nid not in live):
                continue  # dead value node: only deleted nexts read it
        kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    for state, input_id, next_id in plan:
        kept.append(f"{input_id} input {state.sort} havoc_{_label(state)}")
        kept.append(f"{next_id} next {state.sort} {state.id} {input_id}")
    return ("\n".join(kept) + "\n").encode("utf-8")
