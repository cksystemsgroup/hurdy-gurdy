"""tools/additivity.py — the syntactic additivity checker (SCALING.md §6, Lane A).

Decides whether a change to a **shared-layer** file (``gurdy/languages/*``,
``gurdy/core/*``, ``gurdy/solvers/*``) is an *additive extension*: an AST diff
that only **inserts** new statements/branches and leaves every pre-existing code
path behaviour-unchanged.

Why syntactic, not byte-diff-on-corpus: a corpus check is only as strong as its
coverage and misses breakage on untested inputs. Syntactic additivity is a proof
*by construction* — if every old statement is present, in order, with an
identical AST subtree, the change cannot alter an existing verdict, on any input,
tested or not. That is exactly the ratchet's extension test (Prop 4.7) made
mechanical.

Two lanes (SCALING.md §6):

* **Lane A — additive extension (auto-integrable).** Only insertions of new
  statements/branches (new ``def``, new ``if`` block, new top-level binding),
  plus two behaviour-inert allowances: a shared **version bump** (a module-level
  ``*_VERSION = "..."`` string re-binding — the *mechanism* of Lane A, which
  re-stamps evidence) and **docstring / string-comment** edits (they never
  execute). Lane A merges with no human.
* **Lane B — non-additive change (coordinated).** Any edit to an existing path:
  a modified statement, a changed function signature, a deleted/moved statement,
  a re-bound aggregate (``_OPS = ... | NEW``), a folded dispatch tuple. Lane B
  needs the coordinator's re-validation fan-out.

AST equality is used as the equivalence on existing paths. It is *sound* for the
ratchet: identical AST ⇒ identical behaviour. It is deliberately slightly looser
than textual identity — it tolerates whitespace/comment reflow, which cannot
change behaviour — so a reformat of an untouched branch does not force Lane B.

Usage::

    python tools/additivity.py --base origin/main         # classify the PR diff
    python tools/additivity.py --base origin/main --json   # machine-readable
    python tools/additivity.py --base origin/main --require-lane-a  # exit 1 on B

The core (:func:`classify_source`) is pure ``(old_src, new_src) -> verdict`` and
needs no git, so it is directly unit-testable.
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import subprocess
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The shared layer (mirrors tools/pr_manifest.py::_scope). Pair-local files
# (gurdy/pairs/*) are governed by their own pair gate, not this checker.
_SHARED_PREFIXES = ("gurdy/languages/", "gurdy/core/", "gurdy/solvers/")


def is_shared(path: str) -> bool:
    return any(path.startswith(p) for p in _SHARED_PREFIXES) and path.endswith(".py")


# --- AST helpers -------------------------------------------------------------

def _norm(node: ast.AST) -> str:
    """A structural fingerprint that ignores line/column (no attributes)."""
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def _is_string_expr(stmt: ast.stmt) -> bool:
    """A bare string statement — a docstring or a string 'comment'. Inert."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _strip_inert(body: list[ast.stmt]) -> list[ast.stmt]:
    """Drop docstrings / bare string statements before aligning — editing them
    can never change behaviour, so they are not an 'existing path'."""
    return [s for s in body if not _is_string_expr(s)]


def _name_target(stmt: ast.stmt) -> str | None:
    """The single bound Name of an assignment, else None."""
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(
            stmt.targets[0], ast.Name):
        return stmt.targets[0].id
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return stmt.target.id
    return None


def _is_version_assign(stmt: ast.stmt) -> bool:
    """A module-level ``*VERSION* = "..."`` string re-binding: the Lane-A version
    bump that re-stamps evidence. Behaviour-inert for the ratchet's purposes."""
    name = _name_target(stmt)
    if name is None or "VERSION" not in name.upper():
        return False
    value = stmt.value if isinstance(stmt, ast.Assign) else getattr(stmt, "value", None)
    return isinstance(value, ast.Constant) and isinstance(value.value, str)


def _ident(stmt: ast.stmt):
    """A cross-version identity key: same key ⇒ 'the same declaration', which
    may be *additively modified* (a container body) or *edited* (a rebind)."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return ("def", stmt.name)
    name = _name_target(stmt)
    if name is not None:
        return ("bind", name)
    return ("stmt", _norm(stmt))   # match plain statements structurally


def _signature(fn) -> str:
    return _norm(fn.args) + "|" + "|".join(_norm(d) for d in fn.decorator_list)


def _desc(stmt: ast.stmt) -> str:
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"def {stmt.name}"
    if isinstance(stmt, ast.ClassDef):
        return f"class {stmt.name}"
    name = _name_target(stmt)
    if name is not None:
        return f"bind {name}"
    return f"{type(stmt).__name__}@L{getattr(stmt, 'lineno', '?')}"


# --- the additivity comparison ----------------------------------------------

@dataclass
class Verdict:
    reasons: list[str] = field(default_factory=list)   # non-additive findings
    additions: list[str] = field(default_factory=list)  # inserted symbols/branches

    @property
    def additive(self) -> bool:
        return not self.reasons

    def merge(self, other: "Verdict") -> None:
        self.reasons += other.reasons
        self.additions += other.additions


def _compare_bodies(old_body, new_body, qual: str) -> Verdict:
    """Align two statement lists. Every old statement must reappear, in order,
    either AST-identical or additively-modified; new statements in the gaps are
    insertions. A missing/edited old statement is a non-additive finding."""
    v = Verdict()
    old = _strip_inert(old_body)
    new = _strip_inert(new_body)
    j = 0
    for os_ in old:
        key = _ident(os_)
        k = next((i for i in range(j, len(new)) if _ident(new[i]) == key), None)
        if k is None:
            v.reasons.append(f"{qual}: removed or moved {_desc(os_)}")
            continue
        for ins in new[j:k]:
            v.additions.append(f"{qual}: + {_desc(ins)}")
        v.merge(_compare_matched(os_, new[k], qual))
        j = k + 1
    for ins in new[j:]:
        v.additions.append(f"{qual}: + {_desc(ins)}")
    return v


def _compare_matched(old: ast.stmt, new: ast.stmt, qual: str) -> Verdict:
    """Two statements sharing an identity key. Decide if the edit (if any) is
    additive."""
    v = Verdict()
    if _norm(old) == _norm(new):
        return v                                   # identical existing path

    if isinstance(old, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(
            new, type(old)):
        if _signature(old) != _signature(new):
            v.reasons.append(f"{qual}.{old.name}: signature or decorators changed")
            return v
        return _compare_bodies(old.body, new.body, f"{qual}.{old.name}")

    if isinstance(old, ast.ClassDef) and isinstance(new, ast.ClassDef):
        if _norm_bases(old) != _norm_bases(new):
            v.reasons.append(f"{qual}.{old.name}: base classes or decorators changed")
            return v
        return _compare_bodies(old.body, new.body, f"{qual}.{old.name}")

    if _name_target(old) is not None:              # an existing binding, re-bound
        if _is_version_assign(old) and _is_version_assign(new):
            v.additions.append(f"{qual}: version bump {_name_target(new)}")
            return v
        v.reasons.append(
            f"{qual}: {_desc(old)} rebound (existing value modified)")
        return v

    v.reasons.append(f"{qual}: {_desc(old)} modified (existing path changed)")
    return v


def _norm_bases(cls: ast.ClassDef) -> str:
    return "|".join(_norm(b) for b in cls.bases) + "||" + "|".join(
        _norm(d) for d in cls.decorator_list)


# --- public API --------------------------------------------------------------

def classify_source(old_src: str | None, new_src: str, path: str = "<mem>") -> dict:
    """Classify one file's change. ``old_src`` None/empty ⇒ a brand-new shared
    file (purely additive). Returns a JSON-able verdict dict."""
    try:
        new_tree = ast.parse(new_src)
    except SyntaxError as exc:
        return {"path": path, "additive": False,
                "reasons": [f"{path}: new source does not parse ({exc})"],
                "additions": []}
    if not (old_src or "").strip():
        adds = [f"{path}: + {_desc(s)}" for s in _strip_inert(new_tree.body)]
        return {"path": path, "additive": True, "reasons": [], "additions": adds}
    try:
        old_tree = ast.parse(old_src)
    except SyntaxError as exc:
        return {"path": path, "additive": False,
                "reasons": [f"{path}: base source does not parse ({exc})"],
                "additions": []}
    v = _compare_bodies(old_tree.body, new_tree.body, path)
    return {"path": path, "additive": v.additive,
            "reasons": v.reasons, "additions": v.additions}


# --- git driver --------------------------------------------------------------

def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout
    except Exception:
        return ""


def _show_blob(rev: str, path: str) -> str | None:
    """The file's content at ``rev``, or None if the blob is *unavailable* (e.g. a
    shallow clone missing the base commit) — distinct from a genuinely empty file,
    which returns ``""``. The distinction is what keeps the fail-safe honest: an
    unverifiable base must go to Lane B, not be mistaken for a new (additive) file."""
    proc = subprocess.run(["git", "cat-file", "-p", f"{rev}:{path}"],
                          cwd=ROOT, capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def _merge_base(base_ref: str | None) -> str:
    head = _git("rev-parse", "HEAD").strip()
    for ref in ([base_ref] if base_ref else ["origin/main", "main"]):
        mb = _git("merge-base", ref, "HEAD").strip() if ref else ""
        if mb and mb != head:
            return mb
    return _git("rev-parse", "HEAD~1").strip()


def _name_status(mb: str) -> list[tuple[str, str]]:
    out = _git("diff", "--name-status", "-M", mb, "HEAD")
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0], parts[-1]))   # (status, path) — path is dest for renames
    return rows


def classify_diff(base_ref: str | None) -> dict:
    """Classify every shared-layer file changed vs. the base ref. Aggregate lane
    is A iff there is no shared change or every shared change is additive."""
    mb = _merge_base(base_ref)
    files: list[dict] = []
    for status, path in _name_status(mb):
        if not is_shared(path):
            continue
        if status.startswith("D"):
            files.append({"path": path, "additive": False,
                          "reasons": [f"{path}: shared file deleted (existing paths removed)"],
                          "additions": []})
            continue
        if status.startswith("R"):
            files.append({"path": path, "additive": False,
                          "reasons": [f"{path}: shared module renamed (importers affected)"],
                          "additions": []})
            continue
        if status.startswith("A"):
            old_src: str | None = ""              # a genuinely new file
        else:
            old_src = _show_blob(mb, path)
            if old_src is None:                   # base unverifiable -> fail safe to B
                files.append({"path": path, "additive": False,
                              "reasons": [f"{path}: base content unavailable — cannot "
                                          "verify additivity (shallow clone?)"],
                              "additions": []})
                continue
        new_src = _show_blob("HEAD", path)
        if new_src is None:                       # head unverifiable -> fail safe to B
            files.append({"path": path, "additive": False,
                          "reasons": [f"{path}: head content unavailable"],
                          "additions": []})
            continue
        files.append(classify_source(old_src, new_src, path))
    additive = all(f["additive"] for f in files)
    return {
        "schema": "hg-additivity/v1",
        "base": mb,
        "commit": _git("rev-parse", "HEAD").strip(),
        "shared_files_changed": len(files),
        "lane": "A" if additive else "B",
        "files": files,
    }


# --- rendering ---------------------------------------------------------------

def _render(report: dict) -> str:
    lines = [f"additivity vs {report['base'][:12]} (commit {report['commit'][:12]})",
             f"shared files changed: {report['shared_files_changed']}"]
    for f in report["files"]:
        tag = "ADDITIVE" if f["additive"] else "NON-ADDITIVE"
        extra = f"  (+{len(f['additions'])})" if f["additive"] else ""
        lines.append(f"  {f['path']:<40} {tag}{extra}")
        for r in f["reasons"]:
            lines.append(f"       - {r}")
    if report["lane"] == "A":
        lines.append("lane: A  (auto-integrable — additive extension; re-stamp + "
                     "version bump, no human)")
    else:
        lines.append("lane: B  (coordinated — needs the coordinator re-validation "
                     "fan-out, SCALING.md §6)")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None, help="base ref (default origin/main)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--require-lane-a", action="store_true",
                    help="exit 1 if any shared change is non-additive (Lane B)")
    args = ap.parse_args()
    report = classify_diff(args.base)
    print(json.dumps(report, indent=2) if args.json else _render(report))
    if args.require_lane_a and report["lane"] != "A":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
