#!/usr/bin/env python3
"""Build the anonymized review artifact (double-blind submission).

Produces ``dist/hurdy-gurdy-anon-artifact.zip`` from ``git archive HEAD``:
the full tracked tree (tool name kept, per the submission decision), with
author/organization identifiers scrubbed:

- ``.git`` never ships (``git archive``); an anonymized commit history
  (hashes + subjects only — no authors, emails, or dates) is exported to
  ``GIT_HISTORY.txt`` so the paper's commit-level evidence pointers stay
  checkable inside the artifact.
- ``HANDOFF.md`` (internal dev log) and ``paper/main.pdf`` (the submission
  itself; regenerable) are dropped.
- ``README.md`` loses its Lineage section (names the group's other
  project); the paper cites that lineage in the third person instead.
- The Docker Hub image owner and issue-tracker URLs are anonymized; the
  LICENSE copyright holder becomes "the authors of this artifact".

A grep gate then asserts no identifying token survives anywhere in the
tree; the build fails loudly if one does.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ZIP = DIST / "hurdy-gurdy-anon-artifact.zip"

# This script drops ITSELF from the artifact: its replacement table and
# grep-gate token list are author-identifying by construction.
DROP = ["HANDOFF.md", "paper/main.pdf", "paper/reviews",
        "scripts/make_anon_artifact.py"]

REPLACEMENTS = [
    ("christophkirsch/hurdy-gurdy-bench", "ANONYMIZED/hurdy-gurdy-bench"),
    ("https://github.com/cksystemsgroup/hurdy-gurdy/issues/",
     "https://ANONYMIZED.example/issues/"),
    ("github.com/cksystemsgroup/hurdy-gurdy", "ANONYMIZED.example/hurdy-gurdy"),
    ("Copyright (c) 2026 Computational Systems Group",
     "Copyright (c) 2026 the authors of this artifact"),
]

# Case-insensitive tokens that must NOT survive anywhere in the artifact.
# (christoph\b, not christoph: "Christopher" appears in third-party
# citations and is not identifying.)
FORBIDDEN = re.compile(
    r"kirsch|christoph\b|cksystems|ckirsch|selfie|/Users/ck\b", re.IGNORECASE)


def sh(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd or ROOT, check=True,
                          capture_output=True, text=True).stdout


def strip_lineage(readme: Path) -> None:
    text = readme.read_text()
    lines = text.split("\n")
    out, skipping = [], False
    for ln in lines:
        if ln.startswith("## "):
            skipping = ln.strip() == "## Lineage"
        if not skipping:
            out.append(ln)
    readme.write_text("\n".join(out))


def main() -> int:
    DIST.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "hurdy-gurdy"
        stage.mkdir()
        # Tracked tree only, no .git.
        tar = Path(td) / "tree.tar"
        with open(tar, "wb") as f:
            subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, check=True,
                           stdout=f)
        subprocess.run(["tar", "-xf", str(tar), "-C", str(stage)], check=True)

        for rel in DROP:
            p = stage / rel
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()

        strip_lineage(stage / "README.md")

        # Anonymized history: hashes + subjects only.
        history = sh("git", "log", "--reverse", "--format=%h %s")
        (stage / "GIT_HISTORY.txt").write_text(
            "# Commit history of this artifact (hashes + subjects only;\n"
            "# authorship withheld for double-blind review).\n" + history)

        # String scrub across every text file.
        for p in stage.rglob("*"):
            if not p.is_file():
                continue
            try:
                t = p.read_text()
            except (UnicodeDecodeError, PermissionError):
                continue
            orig = t
            for a, b in REPLACEMENTS:
                t = t.replace(a, b)
            if t != orig:
                p.write_text(t)

        # Grep gate: nothing identifying may survive. Third-person
        # citations are policy-compliant, so the bibliography is exempt.
        hits = []
        for p in sorted(stage.rglob("*")):
            if not p.is_file():
                continue
            if p.relative_to(stage) == Path("paper/references.bib"):
                continue  # third-person citations are policy-compliant
            try:
                t = p.read_text()
            except (UnicodeDecodeError, PermissionError):
                continue
            for i, ln in enumerate(t.split("\n"), 1):
                if FORBIDDEN.search(ln):
                    hits.append(f"{p.relative_to(stage)}:{i}: {ln.strip()[:100]}")
        if hits:
            print("ANONYMIZATION GATE FAILED — identifying tokens remain:")
            for h in hits:
                print(" ", h)
            return 1

        # Deterministic-ish zip (sorted entries).
        if ZIP.exists():
            ZIP.unlink()
        with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(stage.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(stage.parent))
        print(f"anonymized artifact: {ZIP}"
              f" ({ZIP.stat().st_size // 1024} KiB); gate clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
