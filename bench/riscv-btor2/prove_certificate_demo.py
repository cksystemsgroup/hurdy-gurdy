"""End-to-end demo of the ``proved``-path certificate prototype.

Three solver paths, two certificate kinds, one external checker per kind:

  --solver=spacer  (default): Spacer (in-process via z3-solver) emits
      an inductive invariant via the fixedpoint API.
      Cert kind: inductive invariant → verify_certificate.

  --solver=pono:   Pono v2.0.0 via local Docker, engine ic3sa, emits
      an inductive invariant via --show-invar. The BTOR2 is
      canonicalized first for Pono's stricter parser.
      Cert kind: inductive invariant → verify_certificate.

  --solver=pono-ind: Pono via local Docker, engine ind (k-induction).
      ind doesn't emit an invariant; instead the certificate is the
      bound k at which k-induction closed, parsed from Pono's ``-v 2``
      log. The model bytes are the canonicalized BTOR2.
      Cert kind: k-induction → verify_kind_certificate.

Either way, the resulting certificate is re-checked using plain z3
SMT against the published artifact bytes — no Spacer / no Pono
internals trusted.

Usage::

    python bench/riscv-btor2/prove_certificate_demo.py
    python bench/riscv-btor2/prove_certificate_demo.py --solver pono
    python bench/riscv-btor2/prove_certificate_demo.py --solver pono-ind
    python bench/riscv-btor2/prove_certificate_demo.py --task 0046-x0-stays-zero-spacer
"""

from __future__ import annotations

import argparse
import dataclasses
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
from gurdy.pairs.riscv_btor2.lift.kind_certificate import verify_kind_certificate
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
    if solver == "pono-ind":
        directive = dataclasses.replace(
            spec.analysis,
            extra_options={**(spec.analysis.extra_options or {}), "engine": "ind"},
        )
        return PonoDockerSolver().dispatch(artifact.flattened, directive)
    raise SystemExit(f"unknown solver: {solver}")


def _verify_invariant(payload: dict, artifact_bytes: bytes) -> int:
    """Print invariant-cert verification + tamper checks. Return 0/1 OK."""
    inv_text = payload["invariant_smtlib"]
    state_nids = payload["state_nid_order"]
    artifact_for_checker = payload.get("canonical_artifact", artifact_bytes)
    print(f"  invariant: {len(inv_text)} chars over {len(state_nids)} state vars")

    print()
    print("--- re-verifying invariant certificate -----------------------")
    report = verify_certificate(artifact_for_checker, inv_text, state_nids)
    print(f"  base case  (init   ⇒ Inv):    {'unsat' if report.base_case_unsat else 'SAT'}")
    print(f"  induction  (Inv∧T  ⇒ Inv'):   {'unsat' if report.inductive_step_unsat else 'SAT'}")
    print(f"  safety     (Inv    ⇒ ¬bad):   {'unsat' if report.safety_unsat else 'SAT'}")
    print(f"  → {report.summary()}")

    print()
    print("--- tamper checks (informational) ----------------------------")
    print("  Tampers SHOULD be rejected for tasks that need a non-trivial")
    print("  invariant. A vacuous tamper that still passes means the bad")
    print("  state is unreachable at the model level alone — also fine.")
    print()

    decls = [ln for ln in inv_text.splitlines() if ln.startswith("(declare-const")]
    vacuous = "\n".join(decls) + "\n(assert true)\n"
    r1 = verify_certificate(artifact_for_checker, vacuous, state_nids)
    print(f"  invariant := true        → {r1.summary()}")

    mutated = re.sub(r"#x0{15}a\b", "#x0000000000000005", inv_text)
    mutated = re.sub(r"#b0{60}1010\b", "#b" + "0" * 61 + "101", mutated)
    if mutated != inv_text:
        r2 = verify_certificate(artifact_for_checker, mutated, state_nids)
        print(f"  bound 10 → 5             → {r2.summary()}")
    else:
        print("  bound 10 → 5             → SKIP (bound constant 10 not present)")

    return 0 if report.accepted else 1


def _verify_kind(payload: dict, artifact_bytes: bytes) -> int:
    """Print k-induction-cert verification + tamper checks. Return 0/1 OK."""
    k = payload["kind_certificate_k"]
    artifact_for_checker = payload.get("canonical_artifact", artifact_bytes)
    print(f"  k = {k}")

    print()
    print("--- re-verifying k-induction certificate ---------------------")
    report = verify_kind_certificate(artifact_for_checker, k)
    print(f"  base case  (init unroll, no bad in 0..k): "
          f"{'unsat' if report.base_case_unsat else 'SAT'}")
    print(f"  step case  (k consec non-bad ⇒ next):     "
          f"{'unsat' if report.step_case_unsat else 'SAT'}")
    print(f"  → {report.summary()}")

    print()
    print("--- tamper checks (informational) ----------------------------")
    print("  Try smaller k values. Tasks needing k≥N to close fail STEP")
    print("  at any k < N; the verifier should report exactly that.")
    print()
    for kk in [max(0, k - 1), max(0, k - 2)]:
        if kk == k:
            continue
        r = verify_kind_certificate(artifact_for_checker, kk)
        print(f"  k := {kk}                 → {r.summary()}")

    return 0 if report.accepted else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument(
        "--solver", choices=("spacer", "pono", "pono-ind"), default="spacer",
        help="solver to emit the certificate",
    )
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
    if not isinstance(raw.payload, dict):
        print(f"ERROR: {args.solver} returned no certificate payload", file=sys.stderr)
        return 1

    if "invariant_smtlib" in raw.payload:
        rc = _verify_invariant(raw.payload, artifact.flattened)
    elif "kind_certificate_k" in raw.payload:
        rc = _verify_kind(raw.payload, artifact.flattened)
    else:
        print(f"ERROR: unrecognized payload shape: {list(raw.payload.keys())}",
              file=sys.stderr)
        return 1

    print()
    if rc == 0:
        print(f"PROTOTYPE OK: {args.solver} certificate accepted by the independent checker.")
    else:
        print("PROTOTYPE FAIL: certificate rejected — see diagnostic above.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
