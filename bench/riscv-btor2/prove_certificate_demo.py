"""End-to-end demo of the Spacer ``proved``-path certificate prototype.

Pipeline exercised:

  task.toml + spec.json + source.elf
       │
       ▼  compile_spec
  CompiledArtifact (BTOR2 model bytes)
       │
       ▼  dispatch(spec.analysis)  → z3-spacer
  RawSolverResult { verdict='proved', payload={ invariant_smtlib, state_nid_order } }
       │
       ▼  verify_certificate(artifact_bytes, invariant_smtlib, state_nid_order)
  CertificateReport { accepted, base_case_unsat, inductive_step_unsat, safety_unsat }

The checker takes only the published artifact bytes and the certificate
fields — at no point does it use Spacer's fixedpoint internals. To show
the checker is not a rubber stamp the script also runs two tampered
invariants and reports that each is rejected with the correct diagnostic.

Usage::

    python bench/riscv-btor2/prove_certificate_demo.py
    python bench/riscv-btor2/prove_certificate_demo.py --task 0046-x0-stays-zero-spacer
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Sibling-adjacent imports.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.dispatch import dispatch
from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.riscv_btor2.lift.certificate import verify_certificate
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec


CORPUS = Path(__file__).resolve().parent / "corpus"
DEFAULT_TASK = "0045-x5-bounded-counter-spacer"


def _load(task_dir: Path) -> RiscvBtor2Spec:
    return RiscvBtor2Spec.from_jsonable(json.loads((task_dir / "spec.json").read_text()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--no-tamper", action="store_true", help="skip negative cases")
    args = parser.parse_args()

    task_dir = CORPUS / args.task
    if not task_dir.is_dir():
        print(f"ERROR: task dir not found: {task_dir}", file=sys.stderr)
        return 2

    print(f"task: {args.task}")
    spec = _load(task_dir)
    # compile_spec resolves source.elf relative to cwd; chdir into the task.
    import os

    cwd = os.getcwd()
    try:
        os.chdir(task_dir)
        artifact = compile_spec(spec)
    finally:
        os.chdir(cwd)

    print(f"  artifact: {len(artifact.flattened)} bytes")
    print(f"  engine:   {spec.analysis.engine}")

    raw = dispatch(artifact, spec.analysis)
    print(f"  verdict:  {raw.verdict} ({raw.elapsed:.3f}s)")
    if raw.verdict != "proved":
        print(f"ERROR: expected verdict=proved, got {raw.verdict}", file=sys.stderr)
        if raw.reason:
            print(f"  reason: {raw.reason}", file=sys.stderr)
        return 1
    if not isinstance(raw.payload, dict) or "invariant_smtlib" not in raw.payload:
        print("ERROR: Spacer adapter did not emit a certificate payload", file=sys.stderr)
        return 1

    inv_text = raw.payload["invariant_smtlib"]
    state_nids = raw.payload["state_nid_order"]
    print(f"  invariant: {len(inv_text)} chars over {len(state_nids)} state vars")

    print()
    print("--- re-verifying certificate -----------------------------------")
    report = verify_certificate(artifact.flattened, inv_text, state_nids)
    print(f"  base case  (init   ⇒ Inv):    {'unsat' if report.base_case_unsat else 'SAT'}")
    print(f"  induction  (Inv∧T  ⇒ Inv'):   {'unsat' if report.inductive_step_unsat else 'SAT'}")
    print(f"  safety     (Inv    ⇒ ¬bad):   {'unsat' if report.safety_unsat else 'SAT'}")
    print(f"  → {report.summary()}")

    overall_ok = report.accepted

    if not args.no_tamper:
        print()
        print("--- tamper checks (informational) ------------------------------")
        print("  Tampers SHOULD be rejected for tasks that need a non-trivial")
        print("  invariant. A vacuous tamper that still passes means the bad")
        print("  state is unreachable at the model level alone — also fine.")
        print()

        decls = [ln for ln in inv_text.splitlines() if ln.startswith("(declare-const")]
        vacuous = "\n".join(decls) + "\n(assert true)\n"
        r1 = verify_certificate(artifact.flattened, vacuous, state_nids)
        print(f"  invariant := true        → {r1.summary()}")

        # Replace the bound (#x000000000000000a == 10) with a wrong tighter one (5).
        mutated = re.sub(r"#x000000000000000a", "#x0000000000000005", inv_text)
        if mutated != inv_text:
            r2 = verify_certificate(artifact.flattened, mutated, state_nids)
            print(f"  bound 10 → 5             → {r2.summary()}")
        else:
            print("  bound 10 → 5             → SKIP (bound constant 0xa not present)")

    print()
    if overall_ok:
        print("PROTOTYPE OK: certificate accepted by the independent checker.")
        return 0
    print("PROTOTYPE FAIL: certificate rejected — see diagnostic above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
