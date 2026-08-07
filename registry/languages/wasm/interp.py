"""WebAssembly shared interpreter — carried over from v3
(KERNEL.md §7). A thin CLI shim over ``gurdy.languages.wasm``: the
deterministic single-function executor. Programs are
``{"body": [[<asm builder name>, args...], ...], "nlocals": n,
"local_types"?}`` — each item resolved through the v3 assembler's
named builders (an unknown name hard-aborts; structured ``if_`` stays
out of the flat carrier for now). Input ``{"steps": n, "pc"?}``.
Observables: the final row's named machine states — ``pc``, ``sp``,
``halted``, locals ``l*``, stack slots ``s*`` — the names the
``wasm--btor2`` translation gives its target states.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.wasm import asm                       # noqa: E402
from gurdy.languages.wasm.interp import module, run        # noqa: E402


def build(program: dict):
    body = [getattr(asm, item[0])(*item[1:]) for item in program["body"]]
    return module(body, nlocals=int(program.get("nlocals", 0)),
                  local_types=program.get("local_types"))


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    with open(sys.argv[2], encoding="utf-8") as fh:
        inp = json.load(fh)
    binding = {}
    if "pc" in inp:
        binding["pc"] = int(inp["pc"])
    if "locals" in inp:
        binding["locals"] = {int(k): int(v)
                             for k, v in inp["locals"].items()}
    trace = run(build(program), binding,
                max_steps=int(inp.get("steps", 1)))
    row = trace[-1] if trace else {}
    obs = {}
    for k, v in row.items():
        if k == "locals":
            obs.update({f"l{i}": x for i, x in enumerate(v)})
        elif k == "stack":
            obs.update({f"s{i}": x for i, x in enumerate(v)})
        else:
            obs[k] = int(v) if isinstance(v, bool) else v
    print(json.dumps(obs, sort_keys=True))


if __name__ == "__main__":
    main()
