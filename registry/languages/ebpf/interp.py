"""eBPF shared interpreter — carried over from v3 (KERNEL.md §7).

A thin CLI shim over ``gurdy.languages.ebpf``: the deterministic
eBPF executor (64-bit ALU, branches, legacy packet loads, EXIT).
Programs are ``{"insns": [<64-bit instruction words>], "entry"?}``;
input ``{"steps": n, "regs"?, "pc"?}``. Observables: the final trace
row — ``pc``, ``r0``..``r10``, ``halted`` — the names the
``ebpf--btor2`` translation gives its target states.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.ebpf.interp import BpfProgram, run    # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    with open(sys.argv[2], encoding="utf-8") as fh:
        inp = json.load(fh)
    prog = BpfProgram(insns=[int(w) for w in program["insns"]],
                      entry=int(program.get("entry", 0)))
    binding = {}
    if "regs" in inp:
        binding["regs"] = {int(r): int(v) for r, v in inp["regs"].items()}
    if "pc" in inp:
        binding["pc"] = int(inp["pc"])
    trace = run(prog, binding, max_steps=int(inp.get("steps", 1)))
    row = trace[-1] if trace else {}
    obs = {k: (int(v) if isinstance(v, bool) else v)
           for k, v in row.items()}
    print(json.dumps(obs, sort_keys=True))


if __name__ == "__main__":
    main()
