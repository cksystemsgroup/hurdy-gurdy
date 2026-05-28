"""End-to-end demo of the ``proved``-path certificate prototype.

Two solver paths, same checker:

  --solver=spacer  (default): Spacer (in-process via z3-solver) emits
      the inductive invariant via the fixedpoint API.

  --solver=pono:   Pono v2.0.0 (via local Docker, engine ic3sa) emits
      the inductive invariant via --show-invar; the BTOR2 model is
      canonicalized first to satisfy Pono's stricter parser.

Either way, the resulting certificate is fed to verify_certificate,
which re-checks the three Horn obligations (init⇒Inv, Inv∧T⇒Inv',
Inv⇒¬bad) using plain z3 SMT against the published artifact bytes —
no Spacer / no Pono internals trusted.

Usage::

    python bench/riscv-btor2/prove_certificate_demo.py
    python bench/riscv-btor2/prove_certificate_demo.py --solver pono
    python bench/riscv-btor2/prove_certificate_demo.py --task 0046-x0-stays-zero-spacer
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.dispatch import dispatch
from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.riscv_btor2.lift.certificate import verify_certificate
from gurdy.pairs.riscv_btor2.solvers.pono_docker import PonoDockerSolver
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec


CORPUS = Path(__file__).resolve().parent / "corpus"
DEFAULT_TASK = "0045-x5-bounded-counter-spacer"


def _load(task_dir: Path) -> RiscvBtor2Spec:
    return RiscvBtor2Spec.from_jsonable(json.loads((task_dir / "spec.json").read_text()))


def _compile(task_dir: Path, spec: RiscvBtor2Spec):
    cwd = os.getcwd()
    try:
        os.chdir(task_dir)
        return compile_spec(spec)
    finally:
        os.chdir(cwd)


def _dispatch(solver: str, artifact, spec):
    if solver == "spacer":
        return dispatch(artifact, spec.analysis)
    if solver == "pono":
        return PonoDockerSolver().dispatch(artifact.flattened, spec.analysis)
    raise SystemExit(f"unknown solver: {solver}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument(
        "--solver", choices=("spacer", "pono"), default="spacer",
        help="solver to emit the inductive invariant",
    )
    parser.add_argument("--no-tamper", action="store_true", help="skip negative cases")
    args = parser.parse_args()

    task_dir = CORPUS / args.task
    if not task_dir.is_dir():
        print(f"ERROR: task dir not found: {task_dir}", file=sys.stderr)
        return 2

    print(f"task:   {args.task}")
    print(f"solver: {args.solver}")
    spec = _load(task_dir)
    artifact = _compile(task_dir, spec)
    print(f"  artifact: {len(artifact.flattened)} bytes")

    raw = _dispatch(args.solver, artifact, spec)
    print(f"  verdict:  {raw.verdict} ({raw.elapsed:.3f}s)")
    if raw.verdict != "proved":
        print(f"ERROR: expected verdict=proved, got {raw.verdict}", file=sys.stderr)
        if raw.reason:
            print(f"  reason: {raw.reason}", file=sys.stderr)
        return 1
    if not isinstance(raw.payload, dict) or "invariant_smtlib" not in raw.payload:
        print(
            f"ERROR: {args.solver} adapter did not emit a certificate payload",
            file=sys.stderr,
        )
        return 1

    inv_text = raw.payload["invariant_smtlib"]
    state_nids = raw.payload["state_nid_order"]
    artifact_for_checker = raw.payload.get("canonical_artifact", artifact.flattened)
    print(f"  invariant: {len(inv_text)} chars over {len(state_nids)} state vars")

    print()
    print("--- re-verifying certificate -----------------------------------")
    report = verify_certificate(artifact_for_checker, inv_text, state_nids)
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
        r1 = verify_certificate(artifact_for_checker, vacuous, state_nids)
        print(f"  invariant := true        → {r1.summary()}")

        # Try both hex (Spacer) and binary (Pono ic3sa) forms of the bound.
        mutated = re.sub(r"#x0{15}a\b", "#x0000000000000005", inv_text)
        mutated = re.sub(r"#b0{60}1010\b", "#b" + "0" * 61 + "101", mutated)
        if mutated != inv_text:
            r2 = verify_certificate(artifact_for_checker, mutated, state_nids)
            print(f"  bound 10 → 5             → {r2.summary()}")
        else:
            print("  bound 10 → 5             → SKIP (bound constant 10 not present)")

    print()
    if overall_ok:
        print(f"PROTOTYPE OK: {args.solver} certificate accepted by the independent checker.")
        return 0
    print("PROTOTYPE FAIL: certificate rejected — see diagnostic above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
