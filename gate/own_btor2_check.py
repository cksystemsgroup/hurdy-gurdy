"""Reproducible end-to-end validation of the pair's OWN BTOR2 lowering vs Sail.

The agent's own lowering (``gurdy/hops/riscv_btor2/btor2.py``) emits a
specialized BTOR2 transition system; this gate-side harness model-checks that
the emitted model executes a real program to exactly Sail's register state,
with pono. A wrong expectation is a positive control. Run inside the bench
image (which has both sail_riscv_sim and pono):

    python3 -m gate.own_btor2_check

This lives in the GATE, not the hop package — it uses Sail, which the pair is
sandboxed from (so it must not appear in the audited hop sources).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_PROGRAM = """
  li x5, 123456789
  li x6, -987654321
  li x7, 42
  add  x18, x5, x6
  sub  x19, x6, x5
  mul  x20, x7, x5
  xor  x21, x5, x6
  sll  x22, x7, x5
  slt  x23, x5, x6
  divu x24, x5, x7
  remu x25, x6, x7
  addw x26, x5, x6
"""
_CHECK_REGS = range(1, 32)


def _pono_finds_bug(model_text: str, pono: str, k: int) -> bool:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.btor2"
        p.write_text(model_text)
        out = subprocess.run([pono, "-e", "bmc", "-k", str(k), str(p)],
                             capture_output=True, text=True).stdout
    head = out.strip().splitlines()[0].strip() if out.strip() else ""
    return head == "sat"


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.sail_btor2_machine import sail_cross
    from gurdy.hops.riscv_btor2 import btor2, decode, elf

    pono = shutil.which("pono")
    if pono is None:
        print("SKIP: pono not on PATH (run inside the bench image)")
        return 0
    oracle = sail_cross._load_oracle()
    try:
        oracle.sail_binary()
    except oracle.SailUnavailable as e:
        print(f"SKIP: {e}")
        return 0

    elf_bytes = oracle.assemble(_PROGRAM, with_halt=False)
    loaded = elf.load(elf_bytes)
    ops = decode.decode_program(loaded)
    sail = oracle.run(elf_bytes, max_steps=len(ops))[-1].regs
    mask = (1 << 64) - 1
    checks = [(k, sail.get(k, 0) & mask) for k in _CHECK_REGS]

    k = len(ops) + 3
    good = btor2.lower(ops, loaded.entry, checks=checks).text
    bad = btor2.lower(ops, loaded.entry,
                      checks=[(20, (sail.get(20, 0) + 1) & mask)]).text

    ok_good = not _pono_finds_bug(good, pono, k)
    ok_bad = _pono_finds_bug(bad, pono, k)
    print(f"  program: {len(ops)} instrs, BMC k={k}")
    print(f"  correct model -> pono finds no bug : {ok_good}")
    print(f"  wrong model    -> pono finds bug    : {ok_bad}")
    if ok_good and ok_bad:
        print("OWN BTOR2 VALIDATED: specialized lowering executes == Sail (pono BMC)")
        return 0
    print("OWN BTOR2 VALIDATION FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
