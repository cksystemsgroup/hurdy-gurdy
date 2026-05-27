"""evm-btor2 benchmark harness (P7).

Drives seed corpus tasks through the AlignmentOracle and reports
verdict / witness_step per task.

Usage (from repo root):
    python bench/evm-btor2/harness.py [seed-dir ...]

With no arguments, all seeds under bench/evm-btor2/corpus/seed/ are run.
Each seed directory must contain a task.spec.json file.

Output columns: seed_dir  bad_fired  witness_step  error
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from gurdy.pairs.evm_btor2.oracle import AlignmentOracle, AlignmentResult
from gurdy.pairs.evm_btor2.spec import EvmBtor2Spec

_CORPUS_ROOT = Path(__file__).parent / "corpus" / "seed"


def _load_spec(spec_path: Path) -> EvmBtor2Spec:
    raw = json.loads(spec_path.read_text())
    return EvmBtor2Spec.from_jsonable(raw)


def _run_seed(seed_dir: Path, oracle: AlignmentOracle) -> dict:
    spec_path = seed_dir / "task.spec.json"
    if not spec_path.exists():
        return {"seed": seed_dir.name, "error": "missing task.spec.json"}
    try:
        spec = _load_spec(spec_path)
        t0 = time.monotonic()
        result: AlignmentResult = oracle.check(spec)
        wall = time.monotonic() - t0
        return {
            "seed": seed_dir.name,
            "bad_fired": result.bad_fired,
            "witness_step": result.witness_step,
            "wall_seconds": round(wall, 3),
            "error": None,
        }
    except Exception as exc:
        return {"seed": seed_dir.name, "error": str(exc)}


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args:
        seed_dirs = [Path(a) for a in args]
    else:
        seed_dirs = (
            sorted(p for p in _CORPUS_ROOT.iterdir() if p.is_dir())
            if _CORPUS_ROOT.exists()
            else []
        )

    oracle = AlignmentOracle()
    header = f"{'seed':<40}  {'bad_fired':<10}  {'witness_step':<13}  {'wall_s':<8}  error"
    print(header)
    print("-" * len(header))

    exit_code = 0
    for sd in seed_dirs:
        row = _run_seed(sd, oracle)
        if row.get("error"):
            print(f"{row['seed']:<40}  {'':10}  {'':13}  {'':8}  ERROR: {row['error']}")
            exit_code = 1
        else:
            wstep = str(row["witness_step"]) if row["witness_step"] is not None else "-"
            print(
                f"{row['seed']:<40}  {str(row['bad_fired']):<10}  {wstep:<13}"
                f"  {row['wall_seconds']:<8}  -"
            )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
