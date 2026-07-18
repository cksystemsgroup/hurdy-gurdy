#!/usr/bin/env python3
"""Check that every relative markdown link in the repo resolves — and that
every cross-doc section citation (`[X.md](./X.md) §N[.M]`) names a section
that exists in the cited doc.

The architecture is a web of cross-referencing docs; this guards against the
links — and the § numbers riding on them — rotting. Exits non-zero (for CI)
if any relative link is broken or any citation names a missing section.
External (http/https) and pure-anchor (#...) links are ignored.

Markdown **code** is skipped before scanning — both fenced blocks (``` / ~~~)
and inline spans (`...`) — because a real link never lives inside code, while
the docs are full of bracket/paren math (e.g. `slice[64:64](zext(a,65))`) that
would otherwise be misread as a `[text](target)` link.

A citation `§N.M` passes if the cited doc has a heading numbered `N.M`, or —
because sub-numbers are often numbered list items under a parent heading
(e.g. SCALING.md §12.1 under `## 12`) — a heading numbered `N`. Citations
whose section id is not purely numeric (e.g. INTERFACE.md §2A) are skipped,
not failed."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)]+)\)")
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
# a numbered heading: "## 12. Title", "### 1.6 Title", "## §3 ..."
HEADING = re.compile(r"^#{1,6}\s*(?:§\s*)?(\d+(?:\.\d+)*)(?=[.\s)]|$)")
# a link to a .md file followed by a section number: "[...](./X.md) §N[.M]"
# ("§§4–6" cites a range; the first number is what we check)
CITE = re.compile(r"\]\(([^)]+\.md)\)\s*§+\s*(\d+(?:\.\d+)*)")


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


def headings(path: pathlib.Path) -> set[str]:
    """The numbered-section ids a doc's headings declare."""
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        m = HEADING.match(line)
        if m:
            ids.add(m.group(1))
    return ids


def main() -> int:
    md = [p for p in ROOT.rglob("*.md") if ".git" not in p.parts]
    broken: list[tuple[str, str]] = []
    bad_cites: list[tuple[str, str]] = []
    heading_cache: dict[pathlib.Path, set[str]] = {}
    checked = cited = 0
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
        for m in CITE.finditer(text):
            doc = (f.parent / m.group(1).strip()).resolve()
            sec = m.group(2)
            if not doc.exists():
                continue  # the link check reports it
            if doc not in heading_cache:
                heading_cache[doc] = headings(doc)
            cited += 1
            ids = heading_cache[doc]
            if sec not in ids and sec.split(".")[0] not in ids:
                bad_cites.append((str(f.relative_to(ROOT)),
                                  f"{m.group(1).strip()} §{sec}"))
    print(f"checked {checked} relative links and {cited} section citations "
          f"across {len(md)} markdown files")
    if broken:
        print("BROKEN LINKS:")
        for src, target in broken:
            print(f"  {src} -> {target}")
    if bad_cites:
        print("BAD SECTION CITATIONS:")
        for src, cite in bad_cites:
            print(f"  {src} cites {cite} — no such section")
    if broken or bad_cites:
        return 1
    print("all relative links resolve; all section citations exist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
