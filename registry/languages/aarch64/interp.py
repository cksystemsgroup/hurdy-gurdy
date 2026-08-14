"""AArch64 (A64) shared interpreter — carried over from v3 (KERNEL.md
§7; reconciliation carry-over, 2026-08-14).

A thin CLI shim over ``gurdy.languages.aarch64``: the deterministic
A64 user-level interpreter (interpreter version 0.6 — the ALU
immediates, MOVZ/MOVN/MOVK, the SUBS/ADDS flag packs, the full B.cond
table, B/BL, 64-bit unsigned-offset LDR/STR with the little-endian
byte memory, and the 32-bit W forms; everything else hard-aborts
typed). A program is JSON ``{"words": [<32-bit instruction words>],
"entry"?, "init_regs"?: {"<field>": v} (field 31 = sp), "init_sp"?,
"init_nzcv"?, "init_mem"?: {"<byte addr>": byte}}`` — the initial
state rides in the program, so a translation of the program carries
the same initial state and the square compares like with like. Input:
``{"steps": n, "regs"?, "pc"?, "sp"?, "nzcv"?}`` (overrides, for
witness carry-back). The run halts on leaving the code region or at
``steps``.

Observables: the final trace row — ``pc``, ``x0``..``x30``, ``sp``,
``nzcv``, the fixed memory window ``m0``..``m63``, and ``halted`` —
the same names the ``aarch64--btor2`` translation gives its target
states, which is what closes that square.
"""

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.aarch64.interp import (           # noqa: E402
    program_from_words, run)


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        program = json.load(fh)
    with open(sys.argv[2], encoding="utf-8") as fh:
        inp = json.load(fh)
    prog = program_from_words([int(w) for w in program["words"]],
                              entry=int(program.get("entry", 0)))
    binding = {
        "regs": {int(r): int(v)
                 for r, v in program.get("init_regs", {}).items()},
        "nzcv": int(program.get("init_nzcv", 0)),
        "mem": {int(a): int(v)
                for a, v in program.get("init_mem", {}).items()},
    }
    if "init_sp" in program:
        binding["sp"] = int(program["init_sp"])
    for r, v in inp.get("regs", {}).items():        # witness carry-back
        binding["regs"][int(r)] = int(v)
    for key in ("pc", "sp", "nzcv"):
        if key in inp:
            binding[key] = int(inp[key])
    trace = run(prog, binding, max_steps=int(inp.get("steps", 1)))
    row = trace[-1] if trace else {}
    obs = {k: (int(v) if isinstance(v, bool) else v)
           for k, v in row.items()}
    print(json.dumps(obs, sort_keys=True))


if __name__ == "__main__":
    main()
