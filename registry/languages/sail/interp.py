"""Sail (RISC-V model) shared interpreter — carried over from v3
(KERNEL.md §7). A **derived** language: registered together with the
exact pair ``riscv--sail``, so its semantics is checked against the
parent's, program by program, and it adds nothing to the trusted
base. The executor concretely evaluates each instruction's
Sail-derived ``Expr`` tree (``gurdy/languages/sail/rv64.py``) —
independent of the hand-written rules of the riscv interpreter,
which is what makes a Sail-mediated route a real cross-check of the
direct one. Programs are the Sail object JSON
(``{"words","lengths","entry","init_regs","mem"}``); input
(``{"steps", "regs"?, "pc"?}``) and observables (final row: ``pc``,
``x1``..``x31``, ``halted``) match the riscv entry.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.sail.interp import run            # noqa: E402


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    with open(sys.argv[2], encoding="utf-8") as fh:
        inp = json.load(fh)
    binding = {}
    if "regs" in inp:
        binding["regs"] = {int(r): int(v) for r, v in inp["regs"].items()}
    if "pc" in inp:
        binding["pc"] = int(inp["pc"])
    trace = run(program, binding, max_steps=int(inp.get("steps", 1)))
    row = trace[-1] if trace else {}
    obs = {k: (int(v) if isinstance(v, bool) else v)
           for k, v in row.items()}
    print(json.dumps(obs, sort_keys=True))


if __name__ == "__main__":
    main()
