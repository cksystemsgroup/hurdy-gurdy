"""§9.9 determinism check.

Compiles each task's spec twice and asserts byte-equality of the
resulting `CompiledArtifact.flattened` payload. BENCHMARKING.md §7
makes this a hard pre-condition: if compilation is not deterministic
for fixed `(spec, source, schema_version)`, every cached artifact in
the §8.3 bundle is suspect and the benchmark is invalid.

Outputs a JSON object that fits manifest_schema.json's
`determinism_check` field, so the harness can splice it into the
run manifest without translation.

Usage:
    python check_determinism.py [--sample N] [--seed S] [--corpus DIR]

Exit codes:
    0 — every sampled task recompiled to identical bytes
    1 — at least one task failed; the manifest's run is invalid
    2 — bad invocation (no tasks found, malformed spec, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gurdy.core.tools.compile import compile_spec
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec


@dataclass
class Failure:
    task_id: str
    reason: str


@dataclass
class Report:
    sample_size: int
    pass_count: int
    checked_at: str
    failures: list[Failure] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "pass_count":  self.pass_count,
            "checked_at":  self.checked_at,
            "failures":    [asdict(f) for f in self.failures],
        }


def _load_spec(task_dir: Path) -> RiscvBtor2Spec:
    with (task_dir / "spec.json").open() as f:
        obj = json.load(f)
    spec = RiscvBtor2Spec.from_jsonable(obj)
    # Rewrite binary.path to an absolute path so compile_spec works
    # regardless of cwd. spec is frozen — rebuild via from_jsonable.
    elf = (task_dir / spec.binary.path).resolve()
    obj["fields"]["binary"]["path"] = str(elf)
    return RiscvBtor2Spec.from_jsonable(obj)


def _check_one(task_dir: Path) -> Failure | None:
    task_id = task_dir.name
    try:
        spec = _load_spec(task_dir)
    except Exception as e:
        return Failure(task_id, f"spec load failed: {e}")

    try:
        a = compile_spec(spec)
        b = compile_spec(spec)
    except Exception as e:
        return Failure(task_id, f"compile_spec raised: {e}")

    if a.flattened != b.flattened:
        return Failure(
            task_id,
            f"flattened bytes differ: len(a)={len(a.flattened)} len(b)={len(b.flattened)} "
            f"first_diff_at={_first_diff(a.flattened, b.flattened)}",
        )
    if a.spec_hash != b.spec_hash:
        return Failure(task_id, f"spec_hash differs: {a.spec_hash} vs {b.spec_hash}")
    return None


def _first_diff(a: bytes, b: bytes) -> int | None:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    if len(a) != len(b):
        return min(len(a), len(b))
    return None


def _discover_tasks(corpus: Path) -> list[Path]:
    return sorted(d for d in corpus.iterdir() if d.is_dir() and (d / "spec.json").is_file())


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).parent / "corpus",
        help="Corpus directory containing <task>/ subdirs.",
    )
    p.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Number of tasks to sample (0 = all). When sampling, --seed is honoured.",
    )
    p.add_argument("--seed", type=int, default=0, help="RNG seed for sampling.")
    args = p.parse_args(argv[1:])

    tasks = _discover_tasks(args.corpus)
    if not tasks:
        print(f"no tasks under {args.corpus}", file=sys.stderr)
        return 2

    if args.sample and args.sample < len(tasks):
        random.Random(args.seed).shuffle(tasks)
        tasks = sorted(tasks[: args.sample])

    failures = [f for f in (_check_one(t) for t in tasks) if f is not None]
    report = Report(
        sample_size=len(tasks),
        pass_count=len(tasks) - len(failures),
        checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        failures=failures,
    )
    print(json.dumps(report.to_jsonable(), indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
