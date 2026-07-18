#!/usr/bin/env python3
"""Author a pinned benchmark from families of a mirror snapshot — the
widening step of the pre-registered protocol (FRONTIER.md §5; the
paper's §6.3 "widens by families, one pinned extension at a time"),
ingestion per BENCHMARKS.md §4.

    python tools/pin_family.py --suite hwmcc-sosylab-beem \\
        --family bv/2024/sosylab --family bv/2019/beem \\
        -o benchmarks/hwmcc-sosylab-beem.json

Pinning is authoring: list the requested families at the pinned commit
(one git-tree call), fetch each instance once — one at a time,
released before the next (the RAM discipline) — hash it, and emit the
suite as a ``core/benchmark.py`` Benchmark JSON, the one input both
``gurdy saturation`` and ``tools/frontier_loop.py`` consume. Honesty
rules, in the order they bite:

* **Authoring requires the bytes.** Any fetch failure aborts without
  writing output — a partially pinned suite would claim coverage it
  does not have. (Offline-is-honest applies to *replaying* a pin,
  ``core/benchmark.py::fetch``, never to authoring one.)
* **Labels only where they exist.** Instances whose paths overlap the
  hand-pinned slice (``tools/abstraction_bench.py``) inherit its
  expected verdicts, and their bytes must hash to the standing pins —
  a mismatch aborts. ``--labels`` (JSON: instance name → verdict)
  adds external ground truth, e.g. harvested competition results; a
  label naming an unknown instance aborts, and so does one
  contradicting an inherited label. Everything else is emitted
  unlabeled — agreement plus witness replay is its ground-truth
  discipline, per the protocol.
* **The cache is the loop's cache.** Fetched bytes land in the shared
  streamed-with-pin cache under the emitted suite's keys, and a final
  self-check re-reads every instance through ``fetch`` — the pin
  round-trips through the exact ingestion the loop uses before the
  output file is written.

The mirror also ships the official per-year competition selections
(``bv/benchmark_set_hwmcc24`` …); selecting by those files instead of
by family is a straightforward extension once a campaign wants
competition-set identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from typing import Any, Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gurdy.core import benchmark as bench_mod  # noqa: E402
from gurdy.core.benchmark import Benchmark, Instance, fetch  # noqa: E402
from gurdy.core.question import Question  # noqa: E402

from abstraction_bench import HWMCC, HWMCC_COMMIT, HWMCC_REPO  # noqa: E402

BTOR2_EXT = ".btor2"

#: The standing pins, keyed by mirror path — inherited labels and the
#: hash agreement the tool enforces against the hand-pinned slice.
KNOWN_PINS: dict[str, dict[str, Any]] = {
    meta["path"]: {k: meta[k] for k in ("sha256", "expected", "note")
                   if k in meta}
    for meta in HWMCC.values()}

FetchFn = Callable[[str], bytes]


def _curl(url: str) -> bytes:
    """Fetch one URL or die — authoring requires the bytes."""
    r = subprocess.run(["curl", "-sfL", "--retry", "3",
                        "--max-time", "60", url], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"fetch failed ({r.returncode}): {url}")
    return r.stdout


def list_blobs(repo: str, commit: str,
               fetch_bytes: FetchFn = _curl) -> list[str]:
    """Every blob path at the pinned commit, from one git-tree call.
    A truncated listing aborts — it could hide part of a family."""
    url = (f"https://api.github.com/repos/{repo}/git/trees/"
           f"{commit}?recursive=1")
    tree = json.loads(fetch_bytes(url))
    if tree.get("truncated"):
        raise RuntimeError(
            f"tree listing for {repo}@{commit} is truncated — "
            "refusing to author from a partial listing")
    return [e["path"] for e in tree.get("tree", [])
            if e.get("type") == "blob"]


def select(paths: list[str],
           families: list[str]) -> list[tuple[str, list[str]]]:
    """The ``.btor2`` instances of each family, sorted. An empty
    family aborts (a typo'd prefix must not pin an empty suite); a
    path claimed by two families aborts (overlapping prefixes would
    double-count an instance)."""
    out: list[tuple[str, list[str]]] = []
    seen: dict[str, str] = {}
    for fam in families:
        prefix = fam.rstrip("/") + "/"
        hits = sorted(p for p in paths
                      if p.startswith(prefix) and p.endswith(BTOR2_EXT))
        if not hits:
            raise ValueError(
                f"family {fam!r}: no {BTOR2_EXT} instances at the "
                "pinned commit")
        for p in hits:
            if p in seen:
                raise ValueError(
                    f"{p} selected by both {seen[p]!r} and {fam!r} — "
                    "families must not overlap")
            seen[p] = fam
        out.append((fam, hits))
    return out


def family_label(prefix: str) -> str:
    """``bv/2024/sosylab`` → ``sosylab'24`` — the slice's family
    convention; without a year segment, just the family name."""
    segs = [s for s in prefix.split("/") if s]
    year = next((s[-2:] for s in segs if len(s) == 4 and s.isdigit()),
                None)
    return f"{segs[-1]}'{year}" if year else segs[-1]


def assign_names(paths: list[str]) -> dict[str, str]:
    """Deterministic instance names (path → name): the basename
    without ``.btor2``, parent-qualified only as far as collisions
    force — every member of a colliding group is qualified, so a name
    never silently means "the other one"."""
    stems = {p: (p[:-len(BTOR2_EXT)] if p.endswith(BTOR2_EXT) else p)
             .split("/") for p in paths}
    depth = {p: 1 for p in paths}
    while True:
        groups: dict[str, list[str]] = {}
        for p in paths:
            groups.setdefault("-".join(stems[p][-depth[p]:]),
                              []).append(p)
        clashes = [ps for ps in groups.values() if len(ps) > 1]
        if not clashes:
            return {p: "-".join(stems[p][-depth[p]:]) for p in paths}
        for ps in clashes:
            for p in ps:
                if depth[p] >= len(stems[p]):
                    raise ValueError(f"cannot disambiguate {p!r}")
                depth[p] += 1


def pin(*, suite: str, repo: str, commit: str, families: list[str],
        fetch_bytes: FetchFn = _curl,
        labels: dict[str, str] | None = None,
        known: dict[str, dict[str, Any]] | None = None,
        cache_dir: str | None = None,
        progress: Callable[[str], None] | None = None) -> Benchmark:
    """Fetch, hash, and assemble the suite. Pure but for the fetch and
    the optional cache writes; any failure raises before anything is
    returned, so a caller never holds a partial pin."""
    known = KNOWN_PINS if known is None else known
    selected = select(list_blobs(repo, commit, fetch_bytes), families)
    fam_of = {p: fam for fam, hits in selected for p in hits}
    paths = sorted(fam_of)
    names = assign_names(paths)

    expected: dict[str, str] = {}
    for p in paths:
        if p in known and "expected" in known[p]:
            expected[names[p]] = known[p]["expected"]
    for name, verdict in (labels or {}).items():
        if name not in set(names.values()):
            raise ValueError(f"--labels names unknown instance {name!r}")
        if expected.get(name, verdict) != verdict:
            raise ValueError(
                f"--labels contradicts the standing pin for {name!r} "
                f"({verdict!r} vs {expected[name]!r})")
        expected[name] = verdict

    total = len(paths)
    instances = []
    for i, p in enumerate(paths, 1):
        url = f"https://raw.githubusercontent.com/{repo}/{commit}/{p}"
        data = fetch_bytes(url)
        digest = hashlib.sha256(data).hexdigest()
        k = known.get(p)
        if k and k.get("sha256") and k["sha256"] != digest:
            raise AssertionError(
                f"{p}: sha256 {digest} disagrees with the standing "
                f"pin {k['sha256']} (tools/abstraction_bench.py)")
        name = names[p]
        if cache_dir is not None:
            with open(os.path.join(cache_dir, f"{suite}-{name}"),
                      "wb") as f:
                f.write(data)
        meta: dict[str, Any] = {"family": family_label(fam_of[p])}
        if k and "note" in k:
            meta["note"] = k["note"]
        instances.append(Instance(
            name=name, path=p, sha256=digest,
            question=Question(source="btor2", shape="reachability",
                              program=name),
            expected=expected.get(name), meta=meta))
        if progress is not None:
            progress(f"pinned {name} ({i}/{total})")
        del data  # one instance fully, then release

    return Benchmark(suite=suite, source=f"github:{repo}@{commit}",
                     instances=tuple(instances))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--suite", required=True)
    ap.add_argument("--family", action="append", required=True,
                    dest="families", metavar="PREFIX",
                    help="mirror path prefix, e.g. bv/2024/sosylab "
                         "(repeatable)")
    ap.add_argument("-o", "--out", required=True,
                    help="benchmark JSON to write")
    ap.add_argument("--repo", default=HWMCC_REPO)
    ap.add_argument("--commit", default=HWMCC_COMMIT)
    ap.add_argument("--labels",
                    help="JSON file: instance name → expected verdict")
    ap.add_argument("--cache",
                    help="cache dir (default: the shared "
                         "streamed-with-pin cache)")
    args = ap.parse_args()

    labels = None
    if args.labels:
        with open(args.labels, encoding="utf-8") as f:
            labels = json.load(f)

    cache = bench_mod._cache_dir(args.cache)
    bench = pin(suite=args.suite, repo=args.repo, commit=args.commit,
                families=args.families, labels=labels, cache_dir=cache,
                progress=print)

    # Self-check: every instance back through the loop's own ingestion
    # (cache hit, sha256 re-verified) before the output exists.
    for inst in bench.instances:
        data = fetch(bench, inst.name, cache_dir=cache)
        if data is None:
            raise RuntimeError(f"self-check could not re-read "
                               f"{inst.name}")
        del data

    os.makedirs(os.path.dirname(os.path.abspath(args.out)),
                exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(bench.to_json())

    labeled = sum(1 for i in bench.instances if i.expected)
    fams: dict[str, int] = {}
    for i in bench.instances:
        fams[i.meta["family"]] = fams.get(i.meta["family"], 0) + 1
    print(f"{args.out}: suite {bench.suite} — "
          f"{len(bench.instances)} instances "
          f"({', '.join(f'{n} {f}' for f, n in sorted(fams.items()))}), "
          f"{labeled} labeled; source {bench.source}")
    print(f"next: python tools/frontier_loop.py {args.out} WORKDIR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
