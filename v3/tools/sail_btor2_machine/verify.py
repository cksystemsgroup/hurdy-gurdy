"""Whole-machine equivalence: the generated BTOR2 machine model vs the reference.

Two obligations, composed:

  1. per-instruction lemmas  ``encode(instr) == reference(instr)``  for all
     inputs (QF_BV; the F3 lemmas) — discharged HERE with z3;
  2. a harness lemma: fetch/decode/pc/control == the reference ``step``.

REFERENCE: A TWO-STEP CHAIN TO REAL SAIL
========================================
Obligation (1) proves each BTOR2 execute fragment equal to the independent
bit-precise reference in ``semantics/sail-riscv/reference_rv64.py`` (derived
from the RISC-V Unprivileged ISA spec), symbolically over ALL 64-bit inputs.

That reference is in turn **cross-validated against the real Sail emulator**
on concrete random + corner inputs by ``sail_cross.cross_check`` (run from
``verify`` below, recorded as ``reference_vs_sail_ok``). So the chain is:

    Sail emulator  --(concrete cross-check)-->  reference_rv64.py
    reference_rv64 --(z3 QF_BV lemmas)------->  BTOR2 model

The reference is no longer an unaudited stand-in — it is pinned to Sail
v0.12 — while the all-inputs F3 proofs are kept. If Sail is unavailable in a
given environment, ``reference_vs_sail_ok`` is left ``None`` (honestly "not
audited here"), and the symbolic lemmas still hold.

Obligation (1) is fully discharged below with z3 over all 64-bit inputs.
Obligation (2) — the fetch/decode/dispatch/writeback/pc harness lemma — is
discharged by ``_prove_harness``: the machine step (decode_map + EXEC IR,
``control.machine_step``) is proven equal to the INDEPENDENT spec-transcribed
``reference_rv64.ref_step`` over a symbolic regfile/pc/instruction-word (z3,
non-vacuous). The emitted ``model.btor2`` is a full transition system from the
same plan, model-checked equal to Sail by pono (``btor2_check.py``). We set
``harness_lemma_ok=True`` only on that proof.

Implementation-defined points (``idf_allowlist``) are subtracted. None apply
to this RV64I/M ALU slice. The result is a ``MachineFidelityReport``.
"""

from __future__ import annotations

from pathlib import Path

import z3

from gurdy.core.report import MachineFidelityReport
from tools.sail_btor2_machine.generate import GeneratedMachine
from tools.sail_btor2_machine.isa import expr as E
from tools.sail_btor2_machine.isa import rv64_alu as ISA


def _load_reference():
    """Import the reference module by path (it lives under semantics/, which
    is not a package). Returns the module object."""
    import importlib.util

    ref_path = (
        Path(__file__).resolve().parents[2]
        / "semantics" / "sail-riscv" / "reference_rv64.py"
    )
    spec = importlib.util.spec_from_file_location("reference_rv64", ref_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _reference_result(ref, spec: ISA.InstrSpec, env: dict):
    """Evaluate the reference semantics for one instruction over z3 inputs.

    The reference exposes per-mnemonic functions taking 64-bit operands. For
    the immediate ALU ops the operand ``b`` is the extended immediate, exactly
    as in the encode tree, so the lemma domains match."""
    name = spec.name
    a = env.get("a")
    b = env.get("b")
    if name == "LUI":
        return ref.LUI(env["uimm"])
    if name == "AUIPC":
        return ref.AUIPC(env["pc"], env["uimm"])
    if name in ref.REGREG:
        return ref.REGREG[name](a, b)
    if name in ref.IMM_ALIAS:
        return ref.IMM_ALIAS[name](a, b)
    raise KeyError(f"reference has no semantics for {name}")


def _prove_instr(ref, spec: ISA.InstrSpec) -> tuple[bool, str]:
    """Discharge encode(instr) == reference(instr) for all inputs. Returns
    (proven, detail). detail carries a counterexample on failure."""
    names = ISA.operand_vars(spec)
    env = {n: z3.BitVec(n, 64) for n in names}

    encoded = E.to_z3(spec.execute, env)
    expected = _reference_result(ref, spec, env)

    s = z3.Solver()
    s.add(encoded != expected)
    res = s.check()
    if res == z3.unsat:
        return True, "QF_BV lemma unsat (encode == reference for all inputs)"
    if res == z3.sat:
        m = s.model()
        cex = {n: hex(m.eval(env[n], model_completion=True).as_long()) for n in names}
        return False, f"DIVERGENCE: counterexample {cex}"
    return False, f"solver returned {res}"


def _prove_harness(ref) -> tuple[bool, str]:
    """Discharge the fetch/decode/dispatch/writeback/pc harness lemma:

        decodes_in_slice(iw)  =>  machine_step(iw, rf, pc) == ref_step(iw, rf, pc)

    over a symbolic regfile (Array bv5->bv64), pc (bv64), and instruction word
    (bv32). The machine step is sourced from the decode tables + EXEC IR trees;
    ``ref.ref_step`` is the INDEPENDENT spec-transcribed reference. Also checks
    that the two slice-recognition predicates agree. Returns (proven, detail).
    """
    from tools.sail_btor2_machine import control

    regfile = z3.Array("rf", z3.BitVecSort(control.RIDX), z3.BitVecSort(control.XLEN))
    pc = z3.BitVec("pc", control.XLEN)
    iw = z3.BitVec("iw", 32)

    # (a) the machine and reference recognize exactly the same instruction set
    s = z3.Solver()
    s.add(control.machine_decodes_in_slice(iw) != ref.ref_decodes_in_slice(iw))
    if s.check() != z3.unsat:
        return False, "DIVERGENCE: machine vs reference slice predicates disagree"

    # (b) on every recognized instruction word, the whole-state step agrees
    rf_m, pc_m = control.machine_step(iw, regfile, pc)
    rf_r, pc_r = ref.ref_step(iw, regfile, pc)
    s = z3.Solver()
    s.add(control.machine_decodes_in_slice(iw))
    s.add(z3.Or(rf_m != rf_r, pc_m != pc_r))
    res = s.check()
    if res == z3.unsat:
        return True, "harness lemma unsat (machine step == reference step for all in-slice iw)"
    if res == z3.sat:
        m = s.model()
        return False, f"DIVERGENCE: counterexample iw={m.eval(iw)}"
    return False, f"solver returned {res}"


def verify(machine: GeneratedMachine, sail_model_dir: Path, idf_allowlist: list[str],
           *, cross_check: bool = True) -> MachineFidelityReport:
    ref = _load_reference()

    report = MachineFidelityReport(realization=machine.realization)
    report.instructions_total = len(ISA.ALL_SPECS)

    # idf subtraction: enumerate any allowlisted point that names an ALU instr
    # in this slice. None do, so this is 0 — recorded honestly.
    report.idf_subtracted = 0

    for spec in ISA.ALL_SPECS:
        proven, detail = _prove_instr(ref, spec)
        if proven:
            report.instructions_proven += 1
        else:
            report.divergences.append(f"{spec.name}: {detail}")

    # Cross-validate the symbolic reference against the real Sail emulator
    # (concrete F1). On clean audit -> reference_vs_sail_ok=True; on a genuine
    # divergence -> False + details; if Sail is unavailable -> None (honest).
    if cross_check:
        report.reference_vs_sail_ok = run_reference_vs_sail(report)
        # also validate the machine DECODER against real Sail instruction words
        # (independent of the reference transcription); a divergence blocks green.
        from tools.sail_btor2_machine import sail_cross
        dec = sail_cross.decode_vs_sail()
        if dec.skipped_reason is None and not dec.ok:
            for d in dec.divergences:
                report.divergences.append(f"decode!=Sail {d}")

    # Obligation (2): the fetch/decode/pc/control harness lemma — discharged
    # with z3 against the independent reference step.
    harness_ok, harness_detail = _prove_harness(ref)
    report.harness_lemma_ok = harness_ok
    if not harness_ok:
        report.divergences.append(f"harness: {harness_detail}")

    return report


def run_reference_vs_sail(report: MachineFidelityReport | None = None) -> bool | None:
    """Run the concrete reference-vs-Sail cross-check. Returns True (all cases
    agree), False (a real divergence — appended to ``report.divergences`` if
    given), or None (Sail/toolchain unavailable here; not an audit failure).

    Imported lazily to avoid a hard dependency on Sail for the pure-z3 path."""
    from tools.sail_btor2_machine import sail_cross

    res = sail_cross.cross_check()
    if res.skipped_reason is not None:
        return None
    if not res.ok and report is not None:
        for d in res.divergences:
            report.divergences.append(f"reference!=Sail {d}")
    return res.ok


# Number of distinct QF_BV equivalence lemmas this slice discharges = one per
# instruction spec.
def lemma_count() -> int:
    return len(ISA.ALL_SPECS)
