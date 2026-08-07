"""EVM shared interpreter — carried over from v3 (KERNEL.md §7).

A thin CLI shim over ``gurdy.languages.evm``: the deterministic EVM
executor (stack machine over raw bytecode; ``status`` records why a
run halted). Programs are ``{"code": [<bytes>], "entry"?}``; input
``{"steps": n, "pc"?}``. Observables: the final trace row's named
machine states — ``pc``, ``sp``, ``halted``, ``status``,
``s0``..``s{top}`` — the names the ``evm--btor2`` translation gives
its target states.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.evm.interp import EvmProgram, run     # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    with open(sys.argv[2], encoding="utf-8") as fh:
        inp = json.load(fh)
    prog = EvmProgram(code=bytes(program["code"]),
                      entry=int(program.get("entry", 0)))
    binding = {}
    if "pc" in inp:
        binding["pc"] = int(inp["pc"])
    trace = run(prog, binding, max_steps=int(inp.get("steps", 1)))
    row = trace[-1] if trace else {}
    obs = {k: (int(v) if isinstance(v, bool) else v)
           for k, v in row.items() if not k.startswith("m")}
    print(json.dumps(obs, sort_keys=True))


if __name__ == "__main__":
    main()
