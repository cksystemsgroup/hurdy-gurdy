#!/usr/bin/env python3
"""Check that every relative markdown link in the repo resolves.

The architecture is a web of cross-referencing docs; this guards against the
links rotting. Exits non-zero (for CI) if any relative link is broken.
External (http/https) and pure-anchor (#...) links are ignored.

Markdown **code** is skipped before scanning — both fenced blocks (``` / ~~~)
and inline spans (`...`) — because a real link never lives inside code, while
the docs are full of bracket/paren math (e.g. `slice[64:64](zext(a,65))`) that
would otherwise be misread as a `[text](target)` link.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)]+)\)")
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")


def strip_code(text: str) -> str:
    """Blank out fenced code blocks and inline code spans (length-preserving
    per line is unnecessary — we only run a link regex over the result)."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            out.append("")  # drop the fence line itself
            continue
        if in_fence:
            out.append("")  # drop fenced content
        else:
            out.append(INLINE_CODE.sub(lambda m: " " * len(m.group(0)), line))
    return "\n".join(out)


def main() -> int:
    md = [p for p in ROOT.rglob("*.md") if ".git" not in p.parts]
    broken: list[tuple[str, str]] = []
    checked = 0
    for f in md:
        text = strip_code(f.read_text(encoding="utf-8"))
        for m in LINK.finditer(text):
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
