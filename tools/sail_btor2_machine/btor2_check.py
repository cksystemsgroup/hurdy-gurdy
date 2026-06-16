"""Build a self-contained BTOR2 *validation* model: the emitted harness plus a
loaded program and a safety property, so a model checker (pono) can confirm the
emitted transition system actually executes correctly — end-to-end, not just by
construction.

We pin the initial memory to the program via ``constraint`` lines (memory is
unchanged across steps in the ALU slice, so a single constraint holds for all
steps), ``init`` pc and halted, and assert ``bad = halted & (reg != expected)``.
The program ends with a zero word, which decodes out-of-slice and latches
``halted`` while freezing pc — so when ``halted`` holds the checked register
must equal the expected post-execution value, or pono reports the trace.
"""

from __future__ import annotations

from tools.sail_btor2_machine.isa import expr as E
from tools.sail_btor2_machine import control


def build_check_model(program_words: list[int], checks: list[tuple[int, int]],
                      *, init_pc: int = 0) -> str:
    """program_words: 32-bit instruction words, loaded little-endian from
    ``init_pc``. checks: (reg_index, expected_value) asserted to hold once the
    machine halts. Returns BTOR2 text with a ``bad`` property."""
    bld = E.Btor2Builder()
    # init pc and halted via emit_harness (regfile is irrelevant: the program
    # writes before it reads; x0 is forced 0 by the model)
    h = control.emit_harness(bld, init_pc=init_pc, init_halted=0)
    S = h["sorts"]
    s1, s5, s8, s64 = S["bv1"], S["bv5"], S["bv8"], S["bv64"]
    pc, rf, mem, halted = h["pc"], h["regfile"], h["mem"], h["halted"]

    # pin memory to the program bytes (little-endian)
    prog = bytearray()
    for w in program_words:
        prog += bytes([(w >> (8 * i)) & 0xFF for i in range(4)])
    for i, byte in enumerate(prog):
        addr = bld.emit("constd {} {}", s64, init_pc + i)
        rd_byte = bld.raw("read {} {} {}", s8, mem, addr)
        want = bld.emit("constd {} {}", s8, byte)
        bld.raw("constraint {}", bld.emit("eq {} {} {}", s1, rd_byte, want))

    # bad = halted & OR_k (regfile[k] != expected_k)
    diff = None
    for idx, expected in checks:
        ridx = bld.emit("constd {} {}", s5, idx)
        rv = bld.raw("read {} {} {}", s64, rf, ridx)
        exp = bld.emit("constd {} {}", s64, expected)
        ne = bld.emit("neq {} {} {}", s1, rv, exp)
        diff = ne if diff is None else bld.emit("or {} {} {}", s1, diff, ne)
    bad_cond = bld.emit("and {} {} {}", s1, halted, diff)
    bld.raw("bad {}", bad_cond)

    return "; BTOR2 validation model (harness + program + safety property)\n" + \
        "\n".join(bld.lines) + "\n"


# ---------------------------------------------------------------------------
# Reproducible end-to-end check: emitted BTOR2 == Sail, via pono.
# ---------------------------------------------------------------------------
# Run inside the bench image (has both sail_riscv_sim and pono):
#   python3 -m tools.sail_btor2_machine.btor2_check
_PROGRAM = """
  addi x18, x0, 5
  addi x19, x0, 7
  add  x20, x18, x19
  sub  x21, x19, x18
  mul  x22, x20, x21
  slli x23, x18, 3
  srli x24, x22, 2
"""
_CHECK_REGS = (18, 19, 20, 21, 22, 23, 24)


def _pono_finds_bug(model_text: str, pono: str, k: int = 16) -> bool:
    import subprocess
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.btor2"
        p.write_text(model_text)
        out = subprocess.run([pono, "-e", "bmc", "-k", str(k), str(p)],
                             capture_output=True, text=True).stdout
    return out.strip().splitlines()[0].strip() == "sat" if out.strip() else False


def main() -> int:
    """Assemble a program with Sail, build the emitted BTOR2 model loaded with
    it, and model-check (pono) that the model's halted state matches Sail's
    registers — plus a positive control that a wrong expectation is caught."""
    import shutil
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.sail_btor2_machine import sail_cross

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

    n = _PROGRAM.strip().count("\n") + 1
    projs = oracle.run(oracle.assemble(_PROGRAM, with_halt=False), max_steps=n)
    words = [p.instr for p in projs[:n]]
    final = projs[n - 1].regs
    checks = [(i, final[i]) for i in _CHECK_REGS]

    good = build_check_model(words + [0], checks)
    bad_checks = [(i, (v + 1) if i == 22 else v) for i, v in checks]
    bad = build_check_model(words + [0], bad_checks)

    ok_good = not _pono_finds_bug(good, pono)
    ok_bad = _pono_finds_bug(bad, pono)
    print(f"  correct model -> pono finds no bug : {ok_good}")
    print(f"  wrong model    -> pono finds bug    : {ok_bad}")
    if ok_good and ok_bad:
        print("BTOR2 MODEL VALIDATED: emitted transition matches Sail (pono BMC)")
        return 0
    print("BTOR2 MODEL VALIDATION FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
