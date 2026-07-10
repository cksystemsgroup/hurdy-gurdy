#!/usr/bin/env python3
"""The PR manifest emitter — Phase 1 of the automated-scaling rollout
(SCALING.md §12.1, §4).

Runs the *fast* per-change gate and writes a machine-readable manifest the
coordinator (SCALING.md §7) reads to decide integration:

- **scope** — which files changed, which pairs / languages that touches, and
  whether it reaches the shared layer or a *protected* instrument (inventories
  / probes), which the builder is not allowed to weaken (SCALING.md §9).
- **pairs** — per registered pair, Definition 4.6's coverage in both readings
  (accepted; conjoined where a square exists), the typed-``unsupported`` gap
  count, and — for a *touched* pair — a twice-and-diff determinism check
  (AGENTS.md §4; determinism is non-negotiable).
- **verdict** — the hard, gating signals: every pair measured without error,
  and no touched pair's translator is non-deterministic.

The manifest is deliberately the *fast* subset (interpreters only, no solver
portfolio, no route-grader): those heavier composed / branch-agreement checks
run at a lower cadence (BENCHMARKS.md §6, a later rollout phase). It is
byte-deterministic (no wall-clock) so it can itself be twice-and-diffed.

Usage: ``python tools/pr_manifest.py [--out .hg/pr.yaml]``. Exit non-zero iff a
pair failed to measure or a touched pair failed determinism — the fast gate.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gurdy.core import registry            # noqa: E402
from gurdy.core.coverage import measure    # noqa: E402
from gurdy.core.errors import Unsupported  # noqa: E402


# --- populate the registry --------------------------------------------------

def _import_all_pairs() -> None:
    """Import every ``gurdy.pairs.<id>`` module so its ``register_pair`` runs.
    Iterating the package keeps this correct as pairs are added."""
    import gurdy.pairs as pairs_pkg
    for mod in pkgutil.iter_modules(pairs_pkg.__path__):
        importlib.import_module(f"gurdy.pairs.{mod.name}")


# --- git scope --------------------------------------------------------------

def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return ""


def _changed_files(base_ref: str | None) -> list[str]:
    """Files changed vs. the base. Tries the merge-base with the base ref
    (default ``origin/main``), then the previous commit; never raises."""
    head = _git("rev-parse", "HEAD")
    for ref in ([base_ref] if base_ref else ["origin/main", "main"]):
        mb = _git("merge-base", ref, "HEAD") if ref else ""
        if mb and mb != head:
            out = _git("diff", "--name-only", mb, "HEAD")
            if out:
                return sorted(out.splitlines())
    out = _git("diff", "--name-only", "HEAD~1", "HEAD")
    return sorted(out.splitlines()) if out else []


def _dir_to_pair_id(seg: str) -> str:
    # gurdy/pairs/riscv_btor2/ -> pair id riscv-btor2
    return seg.replace("_", "-")


def _scope(changed: list[str]) -> dict[str, Any]:
    touched_pairs: set[str] = set()
    touched_languages: set[str] = set()
    touches_protected: list[str] = []
    touches_shared = False
    for f in changed:
        parts = f.split("/")
        if len(parts) >= 3 and parts[0] == "gurdy" and parts[1] == "pairs":
            touched_pairs.add(_dir_to_pair_id(parts[2]))
        if len(parts) >= 3 and parts[0] == "gurdy" and parts[1] == "languages":
            touched_languages.add(parts[2])
            touches_shared = True            # interpreters/inventories are shared
            if parts[-1] == "inventory.py":
                touches_protected.append(f)  # the yardstick — protected (§9)
        if len(parts) >= 2 and parts[0] == "gurdy" and parts[1] in (
                "core", "solvers"):
            touches_shared = True
    return {
        "changed_files": changed,
        "touched_pairs": sorted(touched_pairs),
        "touched_languages": sorted(touched_languages),
        "touches_shared_layer": touches_shared,
        "touches_protected": sorted(touches_protected),
    }


# --- per-pair gate ----------------------------------------------------------

def _twice_and_diff(translate: Any, probes: dict[str, Any]) -> bool:
    """Determinism: translate every accepted probe twice; bytes must match."""
    for program in probes.values():
        try:
            a = translate(program)
        except Unsupported:
            continue
        b = translate(program)
        if a != b:
            return False
    return True


def _pair_row(pid: str, pair: Any, touched: bool) -> tuple[dict[str, Any], str | None]:
    row: dict[str, Any] = {
        "id": pid, "source": pair.source, "target": pair.target,
        "fidelity": pair.fidelity, "status": pair.status.value,
        "translator_version": str(pair.translator_version),
    }
    error: str | None = None
    if pair.probes:
        try:
            acc = measure(pair.translator, pair.probes)
            row["accepted"] = [len(acc.covered), acc.total]
            row["gaps"] = len(acc.histogram)
            if pair.square is not None:
                conj = measure(pair.translator, pair.probes, faithful=pair.square)
                row["conjoined"] = [len(conj.covered), conj.total]
            else:
                row["conjoined"] = None      # predicted-grade: per-run (§6.1)
            row["determinism_ok"] = (
                _twice_and_diff(pair.translator, pair.probes) if touched else None)
        except Exception as exc:             # a pair that cannot even be measured
            error = f"{pid}: {type(exc).__name__}: {exc}"
            row["accepted"] = None
            row["conjoined"] = None
            row["determinism_ok"] = None
    else:                                     # e.g. the reproducible C head
        row["accepted"] = None
        row["conjoined"] = None
        row["determinism_ok"] = None
    return row, error


# --- minimal, dependency-free YAML writer -----------------------------------

def _yaml(value: Any, indent: int = 0) -> list[str]:
    pad = "  " * indent
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            if _is_block(v):
                lines.append(f"{pad}{k}:")
                lines += _yaml(v, indent + 1)
            else:                             # scalar, empty, or scalar-list
                lines.append(f"{pad}{k}: {_scalar(v)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                inner = _yaml(item, indent + 1)
                inner[0] = f"{pad}- {inner[0].lstrip()}"
                lines += inner
            else:
                lines.append(f"{pad}- {_scalar(item)}")
        return lines
    return [f"{pad}{_scalar(value)}"]


def _is_block(v: Any) -> bool:
    """A dict renders as a block; a list renders as a block only if it holds a
    dict or nested list (a list of scalars stays inline, e.g. ``[27, 33]``)."""
    if isinstance(v, dict):
        return bool(v)
    if isinstance(v, list):
        return any(isinstance(x, (dict, list)) for x in v)
    return False


def _scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):                   # inline empty / scalar lists
        return "[" + ", ".join(_scalar(x) for x in v) + "]"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


# --- build ------------------------------------------------------------------

def build_manifest(base_ref: str | None = None) -> tuple[dict[str, Any], int]:
    _import_all_pairs()
    changed = _changed_files(base_ref)
    scope = _scope(changed)
    touched = set(scope["touched_pairs"])

    pair_rows, errors = [], []
    for pid, pair in sorted(registry.list_pairs().items()):
        row, err = _pair_row(pid, pair, pid in touched)
        pair_rows.append(row)
        if err:
            errors.append(err)

    det_failures = [r["id"] for r in pair_rows if r.get("determinism_ok") is False]
    manifest = {
        "schema": "hg-pr-manifest/v1",
        "commit": _git("rev-parse", "HEAD") or "unknown",
        "base": (_git("merge-base", base_ref or "origin/main", "HEAD")
                 or "unknown"),
        "scope": scope,
        "pairs": pair_rows,
        "verdict": {
            "coverage_measured": not errors,
            "measurement_errors": errors,
            "determinism_failures": det_failures,
            "protected_change": bool(scope["touches_protected"]),
            "shared_change": scope["touches_shared_layer"],
        },
    }
    # The fast gate fails iff a pair could not be measured or a touched pair is
    # non-deterministic. Coverage *regression* gating is the route-grader's job
    # (a later phase); this phase gates measurability and determinism only.
    exit_code = 1 if (errors or det_failures) else 0
    return manifest, exit_code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=".hg/pr.yaml",
                    help="where to write the manifest (default .hg/pr.yaml)")
    ap.add_argument("--base", default=None,
                    help="base ref for the change diff (default origin/main)")
    args = ap.parse_args()

    manifest, code = build_manifest(args.base)
    text = "\n".join(_yaml(manifest)) + "\n"
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(text)
    v = manifest["verdict"]
    if code:
        print(f"FAST GATE FAILED — errors={v['measurement_errors']} "
              f"determinism_failures={v['determinism_failures']}", file=sys.stderr)
    else:
        print(f"fast gate OK — {len(manifest['pairs'])} pairs measured; "
              f"scope: {len(manifest['scope']['changed_files'])} files, "
              f"pairs touched={manifest['scope']['touched_pairs']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
