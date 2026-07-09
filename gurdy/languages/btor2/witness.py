"""BTOR2 witness (``.wit``) parsing and replay — the shared BTOR2 witness
checker (languages/btor2 brief; SOLVERS.md §4).

A native model checker (``btormc`` / ``pono``) emits a ``.wit`` on a ``sat``
verdict: the reaching run as frame-by-frame state and input assignments. The
*positive*-side check of a ``reachable`` claim is to **replay that witness
through the shared BTOR2 interpreter** and confirm a ``bad`` actually fires — the
commuting square on the witness (this is what makes a native solver's ``sat``
trustworthy, the analogue of the SMT ``model`` replay in ``btor2-smtlib.lift``).

The btor2tools / btorsim format (as emitted by ``btormc``)::

    sat
    b0                         <- violated bad/justice properties
    #0                         <- state frame 0 (initial state)
    0 000 count#0              <- <state-index> <binary-value> <symbol>#<frame>
    @0                         <- input frame 0
    0 0010 turn@0              <- <input-index> <binary-value> <symbol>@<frame>
    ...
    .                          <- end

Array assignments carry an address: ``<index> [<addr-bin>] <value-bin> <sym>``.
Identifiers are resolved by **symbol** first (robust across tools), falling back
to the declaration-order **index**.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ...core.types import Trace
from .eval import interpret
from .model import System, from_text

_SUFFIX = re.compile(r"[#@]\d+$")  # the trailing frame tag on a witness symbol


def _basename(symbol: str | None) -> str | None:
    return _SUFFIX.sub("", symbol) if symbol else symbol


def _as_system(system: Any) -> System:
    if isinstance(system, System):
        return system
    text = system.decode("utf-8") if isinstance(system, (bytes, bytearray)) else str(system)
    return from_text(text)


# A single assignment: (declaration index, base symbol, value). ``value`` is an
# int for a bit-vector, or a ``{addr: val, "default": 0}`` map for an array.
Assign = tuple[int | None, str | None, Any]


@dataclass
class Witness:
    bads: list[int] = field(default_factory=list)
    states: list[Assign] = field(default_factory=list)         # frame-0 state
    inputs: dict[int, list[Assign]] = field(default_factory=dict)  # frame -> inputs
    frames: int = 1                                            # highest frame + 1


def _value(toks: list[str]) -> tuple[Any, str | None]:
    """Parse the value (and trailing symbol) of an assignment line's tokens
    *after* the leading index token. Bit-vector -> int; array -> ``{addr: val}``."""
    if toks and toks[0].startswith("["):
        addr = int(toks[0].strip("[]"), 2)
        val = int(toks[1], 2)
        sym = _basename(toks[2]) if len(toks) > 2 else None
        return {addr: val, "default": 0}, sym
    val = int(toks[0], 2)
    sym = _basename(toks[1]) if len(toks) > 1 else None
    return val, sym


def parse_witness(text: str | bytes) -> Witness:
    s = text.decode("utf-8") if isinstance(text, (bytes, bytearray)) else text
    lines = [ln.strip() for ln in s.splitlines()]
    i = 0
    while i < len(lines) and lines[i].lower() != "sat":
        i += 1
    if i == len(lines):
        raise ValueError("not a 'sat' BTOR2 witness")
    i += 1

    w = Witness()
    section: str | None = None  # "#" (state) or "@" (input)
    frame = 0
    in_props = True
    for ln in lines[i:]:
        if not ln:
            continue
        if ln == ".":
            break
        if ln[0] in "#@":
            section, in_props = ln[0], False
            frame = int(ln[1:])
            w.frames = max(w.frames, frame + 1)
            w.inputs.setdefault(frame, []) if section == "@" else None
            continue
        if in_props:  # property header: b<j> / j<j>, possibly several per line
            w.bads += [int(t[1:]) for t in ln.split() if t[:1] == "b" and t[1:].isdigit()]
            continue
        toks = ln.split()
        idx = int(toks[0])
        val, sym = _value(toks[1:])
        if section == "#" and frame == 0:
            w.states.append((idx, sym, val))
        elif section == "@":
            w.inputs.setdefault(frame, []).append((idx, sym, val))
    return w


def _resolve(nodes: list, idx: int | None, sym: str | None):
    if sym is not None:
        for n in nodes:
            if n.symbol == sym:
                return n
    if idx is not None and 0 <= idx < len(nodes):
        return nodes[idx]
    return None


def replay(system: Any, witness: Witness | str | bytes, k: int | None = None) -> Trace:
    """Replay a ``.wit`` through the shared interpreter; returns the BTOR2
    behavior. ``k`` (the run length) defaults to the witness's own frame span."""
    sys = _as_system(system)
    w = witness if isinstance(witness, Witness) else parse_witness(witness)
    if k is None:
        k = w.frames - 1

    states = sys.states()
    input_nodes = [n for n in sys.nodes.values() if n.op == "input"]

    state_binding: dict[str, Any] = {}
    for idx, sym, val in w.states:
        node = _resolve(states, idx, sym)
        if node is not None:
            state_binding[node.symbol or f"n{node.id}"] = val

    input_binding: dict[int, dict[int, int]] = {}
    for fr, rows in w.inputs.items():
        row: dict[int, int] = {}
        for idx, sym, val in rows:
            node = _resolve(input_nodes, idx, sym)
            if node is not None and not isinstance(val, dict):
                row[node.id] = val
        if row:
            input_binding[fr] = row

    return interpret(sys, {"steps": k + 1, "state": state_binding, "inputs": input_binding})


def check_witness(system: Any, witness: Witness | str | bytes, k: int | None = None) -> bool:
    """Does replaying the witness actually reach a ``bad``? The positive-side
    validation of a native ``reachable`` claim (SOLVERS.md §4)."""
    trace = replay(system, witness, k)
    return any(v == 1 for row in trace for key, v in row.items() if key.startswith("bad"))


def corroborate_unreach(system: Any, k: int,
                        samples: int = 8, seed: int = 0xC0FFEE) -> bool:
    """Interpreter-replay corroboration of a bounded-UNREACHABLE verdict —
    the tested surrogate for the correspondence between the solver's artifact
    and the target semantics (the paper's Thm 4.9 hypothesis (iii)/(iv)
    boundary; SOLVERS.md §5): run the strict shared interpreter for ``k``
    steps and confirm no ``bad`` fires. If the system carries free ``input``
    nodes, additionally run ``samples`` seeded random input assignments (one
    value per input per cycle); a system with no inputs is deterministic and
    the single run is the whole check. Returns True iff no run fires any
    ``bad`` within ``k`` steps.

    This corroborates — it cannot entail (sampling is not a proof); a
    REACHABLE system must return False on a witnessing assignment, which is
    the caller's available negative control."""
    import random as _random

    sys_ = _as_system(system)
    inputs = [n for n in sys_.nodes.values() if n.op == "input"]

    def _clean(binding: dict) -> bool:
        trace = interpret(sys_, binding)
        return not any(v == 1 for row in trace
                       for key, v in row.items() if key.startswith("bad"))

    if not _clean({"steps": k + 1}):
        return False
    rng = _random.Random(seed)
    for _ in range(samples if inputs else 0):
        per_cycle = {
            c: {n.id: rng.getrandbits(sys_.sorts[n.sort].width)
                for n in inputs}
            for c in range(k + 1)}
        if not _clean({"steps": k + 1, "inputs": per_cycle}):
            return False
    return True
