"""Pono-native adapter for the SOTA Pareto comparison.

Pono is the most apples-to-apples peer: it consumes BTOR2 directly,
exactly the language hurdy-gurdy emits. This adapter:

1. Loads the task's spec.json.
2. Calls hurdy-gurdy's ``compile_spec(spec)`` to produce a
   ``CompiledArtifact``.
3. Writes ``artifact.flattened`` (the BTOR2 text) to a tempfile.
4. Invokes ``pono -e bmc -k <bound> <tempfile>`` as a subprocess.
5. Parses the verdict and returns one schema row per
   ``baselines/README.md`` §3.

Comparing hurdy-gurdy's full pipeline against pono-native running
on the SAME BTOR2 isolates engine quality from translation quality.
A future iteration may add a separate "pono with its own frontend"
path (e.g. cosa-generated BTOR2 from C source) for a fully end-to-end
comparison; that requires extra tooling.

Verdict mapping:

- ``sat`` in pono output → ``reachable``
- ``unsat`` in pono output → ``unreachable``
- ``unknown`` or no verdict → ``unknown``
- Process exit non-zero with no verdict → ``error``
- Subprocess timeout → ``timeout``
- ``pono`` not on PATH → ``error notes="pono not on PATH"``
- ``compile_spec`` failure → ``error notes="compile_spec: ..."``

Usage:

    python bench/riscv-btor2/baselines/pono.py --task 0100
    python bench/riscv-btor2/baselines/pono.py --max-tasks 3
"""

from __future__ import annotations

import argparse
import json
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Allow `import gurdy.*` without depending on the package being installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from gurdy.core.tools.compile import compile_spec
from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.riscv_btor2.lift.btor2_for_pono import canonicalize_for_pono
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec


CORPUS = Path(__file__).resolve().parent.parent / "corpus"


def _load_spec(task_dir: Path) -> RiscvBtor2Spec | None:
    """Load spec.json with absolute binary.path. None if unreadable."""
    p = task_dir / "spec.json"
    if not p.exists():
        return None
    try:
        spec_obj = json.loads(p.read_text())
        fields = spec_obj.setdefault("fields", {})
        bin_field = fields.setdefault("binary", {})
        rel = bin_field.get("path", "source.elf")
        bin_field["path"] = str((task_dir / rel).resolve())
        return RiscvBtor2Spec.from_jsonable(spec_obj)
    except Exception:
        return None


def _expected_verdict(task_dir: Path) -> str:
    try:
        import tomllib  # py311+
    except Exception:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    try:
        raw = tomllib.loads((task_dir / "task.toml").read_text())
        return raw.get("expected", {}).get("verdict", "?")
    except Exception:
        return "?"


def _parse_pono_output(stdout: str, stderr: str) -> tuple[str, str]:
    """Map Pono's textual output to a schema verdict.

    Pono v2 BMC output is "sat"/"unsat"/"unknown" followed by the
    property name (e.g. "b0"). Scan all lines for the verdict keyword
    so the property-name line doesn't shadow it.
    """
    out = (stdout + "\n" + stderr).lower()
    # Scan every line for an exact verdict word; first match wins.
    for line in stdout.splitlines():
        tok = line.strip().lower()
        if tok == "unsat":
            return ("unreachable", "pono: unsat")
        if tok == "sat":
            return ("reachable", "pono: sat")
        if tok == "unknown":
            return ("unknown", "pono: unknown")
    if "error" in out:
        return ("error", "pono: error in output")
    return ("error", f"unrecognized pono output (last line: {last!r})")


def run_one(
    task_dir: Path,
    *,
    timeout_s: int = 60,
    memory_mb: int = 2000,
    bound: int = 20,
    engine: str = "ic3sa",
) -> dict[str, Any]:
    """Run pono on the task's hurdy-gurdy-emitted BTOR2; return one row.

    ``engine`` defaults to ``ic3sa`` (same as pono_docker.py) since IC3SA can
    prove both reachable and unreachable verdicts.  BMC would only produce
    ``unknown`` on unreachable tasks.  On complex C-source BTOR2 models,
    IC3SA may time out — that shows up as ``timeout`` in the Pareto table.
    """
    task_id = task_dir.name
    expected = _expected_verdict(task_dir)

    if shutil.which("pono") is None:
        return {
            "tool": "pono-native",
            "task": task_id,
            "verdict": "error",
            "wall_s": 0.0,
            "rss_mb": 0.0,
            "expected": expected,
            "correct": None,
            "cmd": "",
            "raw_excerpt": "",
            "notes": "pono not on PATH",
        }

    spec = _load_spec(task_dir)
    if spec is None:
        return {
            "tool": "pono-native",
            "task": task_id,
            "verdict": "skip",
            "wall_s": 0.0,
            "rss_mb": 0.0,
            "expected": expected,
            "correct": None,
            "cmd": "",
            "raw_excerpt": "",
            "notes": "no spec.json",
        }

    # Materialize the BTOR2 to a tempfile.
    try:
        artifact = compile_spec(spec)
    except Exception as exc:
        return {
            "tool": "pono-native",
            "task": task_id,
            "verdict": "error",
            "wall_s": 0.0,
            "rss_mb": 0.0,
            "expected": expected,
            "correct": None,
            "cmd": "",
            "raw_excerpt": "",
            "notes": f"compile_spec: {type(exc).__name__}: {exc}",
        }

    # Pono v2.0.0 requires sorted state IDs; apply the same canonicalization
    # that pono_docker.py uses so pono can parse our BTOR2 output.
    try:
        canon_bytes = canonicalize_for_pono(
            artifact.flattened.decode("utf-8", errors="replace")
        )
    except Exception as exc:
        return {
            "tool": "pono-native",
            "task": task_id,
            "verdict": "error",
            "wall_s": 0.0,
            "rss_mb": 0.0,
            "expected": expected,
            "correct": None,
            "cmd": "",
            "raw_excerpt": "",
            "notes": f"canonicalize: {type(exc).__name__}: {exc}",
        }

    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".btor2", delete=False
    ) as tmp:
        tmp.write(canon_bytes)
        tmp_path = Path(tmp.name)

    cmd = ["pono", "-e", engine, "-k", str(bound), str(tmp_path)]

    def _set_limits():
        bytes_cap = memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (bytes_cap, bytes_cap))
        except Exception:
            pass

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            preexec_fn=_set_limits,
        )
        wall = time.monotonic() - t0
        verdict, notes = _parse_pono_output(proc.stdout, proc.stderr)
        raw = (proc.stdout + "\n----\n" + proc.stderr)[:4096]
    except subprocess.TimeoutExpired:
        wall = time.monotonic() - t0
        verdict = "timeout"
        notes = f"timeout after {timeout_s}s"
        raw = ""
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass

    correct: bool | None
    if verdict in ("reachable", "unreachable"):
        correct = (verdict == expected)
    else:
        correct = None

    return {
        "tool": "pono-native",
        "task": task_id,
        "verdict": verdict,
        "wall_s": round(wall, 3),
        "rss_mb": 0.0,
        "expected": expected,
        "correct": correct,
        "cmd": " ".join(cmd),
        "raw_excerpt": raw,
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pono-native baseline adapter")
    p.add_argument("--task", help="run only one task by id (substring match)")
    p.add_argument("--corpus", default=str(CORPUS))
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--memory-mb", type=int, default=2000)
    p.add_argument("--bound", type=int, default=20)
    p.add_argument("--engine", default="ic3sa",
                   help="pono engine: ic3sa (default), bmc, ind, ic3bits, ic3ia")
    p.add_argument("--max-tasks", type=int, default=3)
    args = p.parse_args(argv)

    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"corpus not found: {corpus}", file=sys.stderr)
        return 2

    candidates = sorted(
        d
        for d in corpus.iterdir()
        if d.is_dir() and (d / "task.toml").exists() and (d / "spec.json").exists()
    )
    if args.task:
        candidates = [d for d in candidates if args.task in d.name]
    if len(candidates) > args.max_tasks:
        print(
            f"{len(candidates)} candidate tasks; --max-tasks={args.max_tasks}"
            f" caps this run",
            file=sys.stderr,
        )
        candidates = candidates[: args.max_tasks]

    for d in candidates:
        row = run_one(
            d,
            timeout_s=args.timeout,
            memory_mb=args.memory_mb,
            bound=args.bound,
            engine=args.engine,
        )
        sys.stdout.write(json.dumps(row, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
