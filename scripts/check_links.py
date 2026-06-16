#!/usr/bin/env python3
"""Check that every relative markdown link in the repo resolves.

The architecture is a web of cross-referencing docs; this guards against the
links rotting. Exits non-zero (for CI) if any relative link is broken.
External (http/https) and pure-anchor (#...) links are ignored.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)]+)\)")


def main() -> int:
    md = [p for p in ROOT.rglob("*.md") if ".git" not in p.parts]
    broken: list[tuple[str, str]] = []
    checked = 0
    for f in md:
        for m in LINK.finditer(f.read_text(encoding="utf-8")):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://", "#")):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            checked += 1
            if not (f.parent / path_part).resolve().exists():
                broken.append((str(f.relative_to(ROOT)), target))
    print(f"checked {checked} relative links across {len(md)} markdown files")
    if broken:
        print("BROKEN:")
        for src, target in broken:
            print(f"  {src} -> {target}")
        return 1
    print("all relative links resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
