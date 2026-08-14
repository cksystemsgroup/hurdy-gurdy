"""CRN (chemical reaction network) shared interpreter — carried over
from v3 (KERNEL.md §7; reconciliation carry-over, 2026-08-14).

A thin CLI shim over ``gurdy.languages.crn``: the deterministic
discrete (Petri-net) executor. A program is JSON ``{"crn": "<network
text>", "target"?: {species: count}, "k"?: n}`` — the network text
(``species`` / ``init`` / ``rxn`` lines) plus, riding along for the
``crn--smtlib`` translation, the reachability question it will be
asked. Input: ``{"steps"?, "schedule"?: [reaction index | null per
step], "marking"?: {species: count}}``.

Observables: the final marking (one integer per species), and — when
the program names a ``target`` — ``reached``: did the run's marking
equal the target (on the target's named species) at some step
``0..steps``, the same event the ``crn--smtlib`` unrolling makes
``sat``.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.crn.eval import step              # noqa: E402
from gurdy.languages.crn.model import from_text        # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    with open(sys.argv[2], encoding="utf-8") as fh:
        inp = json.load(fh)
    net = from_text(program["crn"])
    binding = {k: inp[k] for k in ("steps", "schedule", "marking")
               if k in inp}
    trace = step(net, binding)
    obs = dict(trace[-1]) if trace else dict(net.init_map)
    target = program.get("target")
    if target:
        rows = [net.init_map] + list(trace)
        obs["reached"] = int(any(
            all(row.get(s) == int(c) for s, c in target.items())
            for row in rows))
    print(json.dumps(obs, sort_keys=True))


if __name__ == "__main__":
    main()
