"""RISC-V shared interpreter — carried over from v3 (KERNEL.md §7).

A thin CLI shim over ``gurdy.languages.riscv``: the deterministic
RV64IMC user-ISA interpreter (machine-mode CSR/trap handling out of
scope; the dev image's step-for-step differential against
``sail_riscv_sim`` is its Era-3 corroboration). A program is JSON
``{"words": [<32-bit instruction words>], "base"?, "entry"?}`` — the
instruction stream as words, the ELF loader's concern factored out.
Input: ``{"steps": n, "regs"?: {"<idx>": v}, "pc"?: v}``. The run
halts on ECALL/EBREAK, on leaving the code region, or at ``steps``.

Observables: the final trace row — ``pc``, ``x1``..``x31``, and
``halted`` — the same names the ``riscv--btor2`` translation gives
its target states, which is what closes that square.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.riscv.interp import (             # noqa: E402
    image_from_words, run)


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    with open(sys.argv[2], encoding="utf-8") as fh:
        inp = json.load(fh)
    image = image_from_words([int(w) for w in program["words"]],
                             base=int(program.get("base", 0)),
                             entry=program.get("entry"))
    binding = {}
    if "regs" in inp:
        binding["regs"] = {int(r): int(v) for r, v in inp["regs"].items()}
    if "pc" in inp:
        binding["pc"] = int(inp["pc"])
    trace = run(image, binding, max_steps=int(inp.get("steps", 1)))
    row = trace[-1] if trace else {}
    obs = {k: (int(v) if isinstance(v, bool) else v)
           for k, v in row.items()}
    print(json.dumps(obs, sort_keys=True))


if __name__ == "__main__":
    main()
