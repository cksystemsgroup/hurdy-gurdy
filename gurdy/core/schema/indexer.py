"""SCHEMA.md indexer.

A pair's ``SCHEMA.md`` is a Markdown file structured by H2/H3 headings.
The indexer parses it once, builds a topic table, and serves entries
through ``describe(topic, pair)``.

Topics are looked up by:

- exact heading match (case-insensitive)
- normalized heading slug (lowercase, non-alphanumeric -> '-')
- partial substring match (with hint suggestions)

Each entry returns the heading text, its rendered body, and the list
of subsection headings beneath it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class SchemaSection:
    """A section in the schema document."""

    level: int
    heading: str
    slug: str
    body: str = ""
    subsections: list["SchemaSection"] = field(default_factory=list)


@dataclass
class SchemaEntry:
    """One result returned by ``describe``.

    The ``schema_version`` and ``interpreter_version`` fields carry
    pair-level metadata: which translation contract produced this
    entry, and whether the pair declares deterministic interpreters
    (and thus supports the interpreter-layer tool surface). They are
    attached at the ``describe`` call site, not by the indexer, so an
    indexer constructed in isolation leaves them empty.
    """

    pair: str
    heading: str
    slug: str
    body: str
    subheadings: tuple[str, ...]
    hint: str | None = None
    schema_version: str = ""
    interpreter_version: str = ""


def slugify(heading: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9]+", "-", heading.strip().lower())
    return out.strip("-")


def parse_schema(text: str) -> list[SchemaSection]:
    """Parse a schema markdown into a list of top-level sections.

    Only ``##`` and ``###`` (and deeper) are treated as topic headings.
    A ``#`` heading is the document title; if present, the H2s inside
    it are returned at the top level. Any text under the title before
    the first H2 becomes the title's body but is not exposed as an
    entry.
    """

    lines = text.splitlines()
    # Use a synthetic root at level 0 below H1; any H1 we see attaches
    # there but its H2 children are flattened up to the top level.
    root = SchemaSection(level=0, heading="<root>", slug="")
    stack: list[SchemaSection] = [root]
    body_buf: list[str] = []

    def flush_body() -> None:
        if not body_buf:
            return
        b = "\n".join(body_buf).strip()
        if b:
            stack[-1].body = (
                stack[-1].body + "\n" + b if stack[-1].body else b
            )
        body_buf.clear()

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            flush_body()
            level = len(m.group(1))
            heading = m.group(2).strip()
            sec = SchemaSection(
                level=level, heading=heading, slug=slugify(heading)
            )
            while stack and stack[-1].level >= level:
                stack.pop()
            stack[-1].subsections.append(sec)
            stack.append(sec)
        else:
            body_buf.append(line)
    flush_body()

    # If the doc has a single H1, expose the H2s beneath it as the
    # top-level entry list (the H1 is the document title, not a topic).
    top = root.subsections
    h1s = [s for s in top if s.level == 1]
    if len(h1s) == 1 and len(top) == 1:
        return list(h1s[0].subsections)
    return top


def _walk(sections: Iterable[SchemaSection]):
    for s in sections:
        yield s
        yield from _walk(s.subsections)


@dataclass
class SchemaIndex:
    """Index of one pair's SCHEMA.md."""

    pair: str
    schema_path: Path
    sections: list[SchemaSection]

    def topics(self) -> tuple[str, ...]:
        return tuple(s.heading for s in _walk(self.sections))

    def describe(self, topic: str) -> SchemaEntry | None:
        norm = topic.strip().lower()
        slug = slugify(topic)
        candidates = list(_walk(self.sections))
        # 1. exact heading match
        for s in candidates:
            if s.heading.strip().lower() == norm:
                return _entry(self.pair, s)
        # 2. slug match
        for s in candidates:
            if s.slug == slug:
                return _entry(self.pair, s)
        # 3. substring
        partial = [s for s in candidates if norm in s.heading.lower()]
        if len(partial) == 1:
            return _entry(self.pair, partial[0])
        if partial:
            hint = (
                "ambiguous topic; matches: "
                + ", ".join(repr(s.heading) for s in partial[:8])
            )
            return SchemaEntry(
                pair=self.pair,
                heading=topic,
                slug=slug,
                body="",
                subheadings=(),
                hint=hint,
            )
        # 4. miss with hint
        first_words = norm.split()
        if first_words:
            related = [
                s.heading
                for s in candidates
                if any(w in s.heading.lower() for w in first_words)
            ][:6]
        else:
            related = []
        hint = (
            "no entry; closest topics: "
            + ", ".join(repr(h) for h in related)
            if related
            else "no entry; available topics: "
            + ", ".join(repr(s.heading) for s in candidates[:8])
        )
        return SchemaEntry(
            pair=self.pair, heading=topic, slug=slug, body="", subheadings=(), hint=hint
        )


def _entry(pair: str, section: SchemaSection) -> SchemaEntry:
    return SchemaEntry(
        pair=pair,
        heading=section.heading,
        slug=section.slug,
        body=section.body,
        subheadings=tuple(s.heading for s in section.subsections),
    )


def load_index(pair: str, path: Path | str) -> SchemaIndex:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    return SchemaIndex(pair=pair, schema_path=p, sections=parse_schema(text))


__all__ = [
    "SchemaSection",
    "SchemaEntry",
    "SchemaIndex",
    "parse_schema",
    "load_index",
    "slugify",
]
