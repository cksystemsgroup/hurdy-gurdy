"""Self-test: run generate -> verify and print the MachineFidelityReport.

Run from the v3 root:

    python3 -m tools.sail_btor2_machine.selftest

It exercises the real z3 proof of every implemented RV64I/M ALU instruction
against the reference semantics, emits model.btor2 + decode_map.json +
provenance.json into the realization directory, and prints a per-instruction
PROVEN/FAILED table plus the report. Exits non-zero if any lemma fails (a
divergence) — but NOT because the report is non-green: green is expected to be
False here (the harness lemma is the next slice).
"""

from __future__ import annotations

import sys
from pathlib import Path

V3 = Path(__file__).resolve().parents[2]
if str(V3) not in sys.path:
    sys.path.insert(0, str(V3))

from tools.sail_btor2_machine.generate import generate
from tools.sail_btor2_machine.harness import ISAConfig
from tools.sail_btor2_machine.verify import _load_reference, _prove_instr, verify
from tools.sail_btor2_machine.isa import rv64_alu as ISA


def main() -> int:
    out_dir = V3 / "semantics" / "sail-riscv" / "realizations" / "btor2-machine"
    sail_dir = V3 / "semantics" / "sail-riscv" / "model"   # absent; placeholder path

    cfg = ISAConfig(isa="rv64")
    print("== generate ==")
    machine = generate(sail_dir, cfg, out_dir=out_dir)
    print(f"  model.btor2     -> {machine.model_path}")
    print(f"  decode_map.json -> {out_dir / 'decode_map.json'}  ({len(machine.decode_map)} instrs)")
    print(f"  provenance.json -> {out_dir / 'provenance.json'}")
    nlines = machine.model_path.read_text().count("\n")
    print(f"  model.btor2 lines: {nlines}")

    print("\n== verify (z3, per-instruction QF_BV lemma vs reference) ==")
    ref = _load_reference()
    failed = []
    for spec in ISA.ALL_SPECS:
        ok, detail = _prove_instr(ref, spec)
        status = "PROVEN" if ok else "FAILED"
        print(f"  {status:7s} {spec.name:7s}  {detail if not ok else ''}".rstrip())
        if not ok:
            failed.append(spec.name)

    report = verify(machine, sail_dir, idf_allowlist=[])
    print("\n== MachineFidelityReport ==")
    print(f"  realization          : {report.realization}")
    print(f"  instructions_total   : {report.instructions_total}")
    print(f"  instructions_proven  : {report.instructions_proven}")
    print(f"  harness_lemma_ok     : {report.harness_lemma_ok}  (next slice — fetch/decode dispatch)")
    print(f"  idf_subtracted       : {report.idf_subtracted}")
    print(f"  divergences          : {report.divergences or 'none'}")
    print(f"  green                : {report.green}  (expected False — slice incomplete, reference != Sail)")
    print(f"\n  QF_BV lemmas discharged by z3: {report.instructions_proven}/{report.instructions_total}")

    # write the report JSON next to the model so the gate can load it later
    import dataclasses, json
    rp = out_dir / "MachineFidelityReport.json"
    rp.write_text(json.dumps(dataclasses.asdict(report), indent=2))
    print(f"  wrote {rp}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
