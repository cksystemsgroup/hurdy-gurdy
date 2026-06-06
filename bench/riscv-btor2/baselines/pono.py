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


def _normalize_btor2_for_pono(text: str) -> str:
    """Renumber BTOR2 nodes so that pono's init-ordering constraint is met.

    Pono requires: in ``nid init sort state_id value_id``, state_id > value_id
    (the state must have a higher nid than its initial-value expression).
    Hurdy-gurdy's emitter declares states early (small nids) and emits their
    init values later, which violates this. This function does a topological
    renumbering of all nodes that adds an extra ordering edge
    ``state_id after value_id`` for every init statement, then renumbers 1..N
    in the resulting topological order.

    Comments are stripped (pono ignores them; the artifact layer markers are
    only needed by hurdy-gurdy's own tooling).
    """
    from collections import deque

    # Parse: nid -> token list (nid at position 0)
    nodes: dict[int, list[str]] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        toks = stripped.split()
        try:
            nid = int(toks[0])
        except (ValueError, IndexError):
            continue
        nodes[nid] = toks

    if not nodes:
        return text

    # Determine nid references for a node (used to build the dependency graph).
    # Must be careful: some integer tokens are literals, not nid refs.
    def _ref_nids(toks: list[str]) -> set[int]:
        op = toks[1] if len(toks) > 1 else ""
        refs: set[int] = set()

        if op == "sort":
            kind = toks[2] if len(toks) > 2 else ""
            if kind == "bitvec":
                pass  # width integer is a dimension, not a nid
            elif kind == "array" and len(toks) >= 5:
                for t in toks[3:5]:  # index_sort_nid, elem_sort_nid
                    try:
                        refs.add(int(t))
                    except ValueError:
                        pass
        elif op in ("constd", "consth", "const"):
            # toks: [nid, op, sort_nid, value…] — value is a literal
            if len(toks) > 2:
                try:
                    refs.add(int(toks[2]))
                except ValueError:
                    pass
        else:
            # All other ops: positions 2+ are sort/operand nid refs.
            # Symbol strings fail int() and are skipped harmlessly.
            for t in toks[2:]:
                try:
                    refs.add(int(t))
                except ValueError:
                    pass

        return refs & nodes.keys()

    # Build dependency graph: deps[nid] = nids that must precede nid.
    deps: dict[int, set[int]] = {nid: set() for nid in nodes}
    for nid, toks in nodes.items():
        deps[nid].update(_ref_nids(toks))

    # Extra init-ordering edges: state must come after its init value.
    for nid, toks in nodes.items():
        op = toks[1] if len(toks) > 1 else ""
        if op == "init" and len(toks) >= 5:
            try:
                state_id, value_id = int(toks[3]), int(toks[4])
                if state_id in nodes and value_id in nodes:
                    deps[state_id].add(value_id)
            except (ValueError, IndexError):
                pass

    # Topological sort (Kahn's algorithm; break ties by original nid for
    # determinism — keeps the output stable across runs).
    rev: dict[int, set[int]] = {nid: set() for nid in nodes}
    in_deg: dict[int, int] = {nid: 0 for nid in nodes}
    for nid, d in deps.items():
        in_deg[nid] = len(d)
        for dep in d:
            rev[dep].add(nid)

    queue: deque[int] = deque(
        sorted(nid for nid, deg in in_deg.items() if deg == 0)
    )
    order: list[int] = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for dependent in sorted(rev[nid]):
            in_deg[dependent] -= 1
            if in_deg[dependent] == 0:
                queue.append(dependent)

    if len(order) != len(nodes):
        return text  # cycle in the model: bail out, let pono error

    # Build rename map: old_nid -> position in topological order (1-based).
    rename: dict[int, int] = {old: new for new, old in enumerate(order, start=1)}

    def _tok(t: str) -> str:
        """Rename a token if it is a nid reference."""
        try:
            return str(rename.get(int(t), int(t)))
        except ValueError:
            return t  # symbol string — leave unchanged

    # Rewrite tokens, respecting which positions are literals vs nid refs.
    result: list[str] = []
    for old_nid in order:
        toks = nodes[old_nid]
        op = toks[1] if len(toks) > 1 else ""
        new_nid = rename[old_nid]

        if op == "sort":
            kind = toks[2] if len(toks) > 2 else ""
            if kind == "bitvec":
                new_toks = [str(new_nid)] + toks[1:]  # width is literal
            else:  # array: rename index + elem sort nids
                new_toks = [str(new_nid), toks[1], kind]
                new_toks += [_tok(t) for t in toks[3:5]]
                new_toks += toks[5:]  # optional symbol
        elif op in ("constd", "consth", "const"):
            # sort_nid is renamed; the value token is a literal
            new_toks = [str(new_nid), op, _tok(toks[2])] + toks[3:]
        else:
            # Rename every token from position 1 onwards; symbol strings
            # survive _tok unchanged since they're not integers.
            new_toks = [str(new_nid)] + [_tok(t) for t in toks[1:]]

        result.append(" ".join(new_toks))

    return "\n".join(result) + "\n"


def _parse_pono_output(stdout: str, stderr: str) -> tuple[str, str]:
    """Map Pono's textual output to a schema verdict.

    Pono prints ``sat`` / ``unsat`` / ``unknown`` as the FIRST non-empty
    output line, then optionally ``bN`` lines listing satisfied bad
    properties. Walk from the top of stdout; fall back to stderr on silence.
    """
    for line in stdout.splitlines():
        word = line.strip().lower()
        if word == "unsat":
            return ("unreachable", "pono: unsat")
        if word == "sat":
            return ("reachable", "pono: sat")
        if word == "unknown":
            return ("unknown", "pono: unknown")
        if word:  # first non-empty non-verdict line — stop scanning
            break

    combined = (stdout + "\n" + stderr).lower()
    if "error" in combined:
        return ("error", "pono: error in output")

    first_nonempty = next(
        (l.strip() for l in stdout.splitlines() if l.strip()), "<empty>"
    )
    return ("error", f"unrecognized pono output (first line: {first_nonempty!r})")


def run_one(
    task_dir: Path,
    *,
    timeout_s: int = 60,
    memory_mb: int = 2000,
    bound: int = 20,
) -> dict[str, Any]:
    """Run pono on the task's hurdy-gurdy-emitted BTOR2; return one row."""
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

    btor2_text = artifact.flattened.decode("utf-8", errors="replace")
    btor2_text = _normalize_btor2_for_pono(btor2_text)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".btor2", delete=False
    ) as tmp:
        tmp.write(btor2_text)
        tmp_path = Path(tmp.name)

    cmd = ["pono", "-e", "bmc", "-k", str(bound), str(tmp_path)]

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
        )
        sys.stdout.write(json.dumps(row, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
