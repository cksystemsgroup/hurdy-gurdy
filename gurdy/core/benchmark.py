"""The benchmark — a pinned suite of questions (FRONTIER.md §1.1;
BENCHMARKS.md §4).

A benchmark is data: a ``suite`` id, a source naming the pinned
snapshot (``github:owner/repo@commit`` for streamed-with-pin
ingestion, or ``dir:/abs/path`` for a local corpus), and instances
each carrying a path within the snapshot, a sha256 pin, a question
(the one type, core/question.py — ``(p, φ)`` with ``program`` set to
the instance name), and an optional expected label. It is JSON in and
JSON out, so a benchmark can be pinned in a file, shipped in a repo,
and named on the command line (``gurdy saturation``).

Fetch is streamed-with-pin: one instance at a time, cached, sha256
verified — a hash mismatch is an error, never a silent substitution;
a network failure returns ``None`` (offline is honest, not fatal).
This generalizes what ``tools/abstraction_bench.py`` did privately
for the HWMCC slice; that harness now expresses its slice as a
``Benchmark`` with identical pins and cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any

from .question import Question

_CACHE_ENV = "GURDY_BENCH_CACHE"


@dataclass(frozen=True)
class Instance:
    """One pinned instance: where it lives in the snapshot, its pin,
    its question, and — where the suite is labeled — the expected
    verdict."""

    name: str
    path: str
    sha256: str
    question: Question
    expected: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Benchmark:
    """A pinned, finite set of questions with recorded provenance."""

    suite: str
    source: str  # "github:owner/repo@commit" | "dir:/abs/path"
    instances: tuple[Instance, ...]

    def provenance(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "source": self.source,
            "instances": len(self.instances),
            "sha256": {i.name: i.sha256 for i in self.instances},
        }

    def to_json(self) -> str:
        return json.dumps({
            "suite": self.suite,
            "source": self.source,
            "instances": [{
                "name": i.name, "path": i.path, "sha256": i.sha256,
                "question": i.question.asdict(),
                **({"expected": i.expected} if i.expected else {}),
                **({"meta": i.meta} if i.meta else {}),
            } for i in self.instances],
        }, indent=2, sort_keys=True) + "\n"

    @staticmethod
    def from_json(text: str) -> "Benchmark":
        d = json.loads(text)
        instances = []
        for e in d["instances"]:
            q = dict(e["question"])
            obs = q.pop("observables", None)
            q.pop("verdict", None)  # a spent verdict is a record, not a pin
            instances.append(Instance(
                name=e["name"], path=e["path"], sha256=e["sha256"],
                question=Question(
                    observables=tuple(obs) if obs is not None else None, **q),
                expected=e.get("expected"), meta=e.get("meta", {}),
            ))
        return Benchmark(suite=d["suite"], source=d["source"],
                         instances=tuple(instances))


def _cache_dir(override: str | None = None) -> str:
    d = override or os.environ.get(_CACHE_ENV) or os.path.join(
        tempfile.gettempdir(), "hurdy-bench-cache")
    os.makedirs(d, exist_ok=True)
    return d


def fetch(bench: Benchmark, name: str,
          cache_dir: str | None = None) -> bytes | None:
    """Fetch (or reuse the cached copy of) one pinned instance; verify
    the sha256 pin. Returns the bytes, or ``None`` when a remote source
    is unreachable. A hash mismatch is an ``AssertionError`` — never a
    silent substitution."""
    inst = next(i for i in bench.instances if i.name == name)
    if bench.source.startswith("dir:"):
        p = os.path.join(bench.source[len("dir:"):], inst.path)
        with open(p, "rb") as f:
            data = f.read()
    elif bench.source.startswith("github:"):
        cached = os.path.join(_cache_dir(cache_dir),
                              f"{bench.suite}-{name}")
        if os.path.exists(cached):
            with open(cached, "rb") as f:
                data = f.read()
        else:
            repo, _, commit = bench.source[len("github:"):].partition("@")
            url = (f"https://raw.githubusercontent.com/{repo}/"
                   f"{commit}/{inst.path}")
            r = subprocess.run(["curl", "-sf", "--max-time", "30", url],
                               capture_output=True)
            if r.returncode != 0:
                return None
            data = r.stdout
            with open(cached, "wb") as f:
                f.write(data)
    else:
        raise ValueError(f"unknown benchmark source: {bench.source!r}")
    got = hashlib.sha256(data).hexdigest()
    if got != inst.sha256:
        raise AssertionError(
            f"{bench.suite}/{name}: sha256 mismatch ({got})")
    return data
