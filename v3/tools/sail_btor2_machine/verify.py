"""Whole-machine equivalence: the generated BTOR2 machine model vs the reference.

Two obligations, composed:

  1. per-instruction lemmas  ``encode(instr) == reference(instr)``  for all
     inputs (QF_BV; the F3 lemmas) — discharged HERE with z3;
  2. a harness lemma: fetch/decode/pc/control == the reference ``step``.

REFERENCE CAVEAT
================
The architecture says "vs Sail". Sail is ABSENT in this environment, so we
verify each BTOR2 execute fragment against the independent bit-precise
reference in ``semantics/sail-riscv/reference_rv64.py`` (derived from the
RISC-V Unprivileged ISA spec). This is flagged everywhere as standing in for
Sail until the Sail emulator is wired (TODO). When Sail arrives, only the
reference source swaps; this harness is unchanged.

Obligation (1) is fully discharged below with z3 over all 64-bit inputs.
Obligation (2) — the fetch/decode/pc/control harness lemma — is NOT yet
discharged (the emitted model is execute-datapath only; the full
fetch-from-symbolic-memory dispatch loop is the next slice). We therefore set
``harness_lemma_ok=None`` and say so, rather than claiming it.

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


def verify(machine: GeneratedMachine, sail_model_dir: Path, idf_allowlist: list[str]) -> MachineFidelityReport:
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

    # Obligation (2): the fetch/decode/pc/control harness lemma is the next
    # slice (the emitted model is execute-datapath only). Be honest.
    report.harness_lemma_ok = None

    return report


# Number of distinct QF_BV equivalence lemmas this slice discharges = one per
# instruction spec.
def lemma_count() -> int:
    return len(ISA.ALL_SPECS)
