#!/usr/bin/env python3
"""Author a pinned SV-COMP benchmark from task-definition families —
the second benchmark act (FRONTIER.md §5: "SV-COMP is the natural
second act — source-level C questions down the full spine"),
ingestion per BENCHMARKS.md §4, the ``pin_family.py`` discipline over
the sv-benchmarks upstream.

    python tools/pin_svcomp.py --suite svcomp-bitvector \\
        --family c/bitvector -o benchmarks/svcomp-bitvector.json

SV-COMP differs from the HWMCC mirror in three honest ways, and each
is handled where it bites:

* **Upstream is GitLab.** github.com/sosy-lab/sv-benchmarks is
  archived at svcomp21 ("MOVED"); the live repo is
  gitlab.com/sosy-lab/benchmarking/sv-benchmarks. The default commit
  pins the ``svcomp25`` release tag by SHA (tags move, commits do
  not), listing goes through GitLab's paginated tree API — an error
  reply or a non-terminating pagination aborts, the truncation rule —
  and replay uses the ``gitlab:`` source of ``core/benchmark.py``.
* **Labels live in the suite itself.** Each task is a ``.yml``
  task definition whose ``properties`` entry for ``unreach-call.prp``
  carries ``expected_verdict`` (true = the call is unreachable).
  No external ``--labels`` channel is needed; the task file *is* the
  ground truth, so its own sha256 is recorded in the instance meta
  beside the program pin. The ymls are parsed by a strict minimal
  parser (the repo is stdlib-only) that aborts on anything outside
  the task-definition shape it knows — and cross-checks every parse
  against PyYAML whenever that is importable, a disagreement
  aborting: the parser can decline to author, never mislabel.
* **A task is two files.** The instance ``path``/``sha256`` pin the
  *program* (the bytes the loop streams and a player runs); the task
  definition's path, hash, verdict property, and declared
  ``data_model`` ride in ``meta``. Tasks without an ``unreach-call``
  property, and multi-file tasks, are *typed skips* — counted and
  printed per reason, never silently dropped (BENCHMARKS.md's
  no-silent-caps rule); an unreach-call task without a verdict is
  pinned unlabeled, the protocol's agreement-plus-replay discipline
  owning its ground truth.

Authoring stays all-or-nothing: any fetch failure, parse failure,
empty family, or overlapping family aborts before output exists, and
the final self-check replays every instance through
``core/benchmark.py::fetch`` from the shared cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import sys
from typing import Any, Callable

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gurdy.core import benchmark as bench_mod  # noqa: E402
from gurdy.core.benchmark import Benchmark, Instance, fetch  # noqa: E402
from gurdy.core.question import Question  # noqa: E402

from pin_family import _curl, assign_names, family_label  # noqa: E402

#: The live upstream (the GitHub mirror is archived at svcomp21).
SVCOMP_PROJECT = "sosy-lab/benchmarking/sv-benchmarks"
#: The ``svcomp25`` release tag, resolved to its commit 2026-07-26 —
#: pins name commits, never movable tags.
SVCOMP_COMMIT = "1e5856db49f3a4766f416cc60382aa92012b2939"

TASK_EXT = ".yml"
UNREACH_PRP = "unreach-call.prp"
#: expected_verdict → the platform's verdict vocabulary: *true* means
#: the property holds, i.e. the error call is unreachable.
VERDICT = {True: "unreachable", False: "reachable"}

FetchFn = Callable[[str], bytes]


# ---------------------------------------------------------------- listing

def list_tasks(project: str, commit: str, families: list[str],
               fetch_bytes: FetchFn = _curl,
               per_page: int = 100) -> list[tuple[str, list[str]]]:
    """The ``.yml`` task definitions of each family, via GitLab's
    paginated recursive tree API. An empty family aborts (a typo'd
    prefix must not pin an empty suite); a path claimed by two
    families aborts; an API error reply aborts — authoring never
    proceeds from a listing it cannot trust."""
    out: list[tuple[str, list[str]]] = []
    seen: dict[str, str] = {}
    enc = project.replace("/", "%2F")
    for fam in families:
        prefix = fam.rstrip("/")
        paths: list[str] = []
        page = 1
        while True:
            url = (f"https://gitlab.com/api/v4/projects/{enc}/repository/"
                   f"tree?ref={commit}&path={prefix}&recursive=true"
                   f"&per_page={per_page}&page={page}")
            reply = json.loads(fetch_bytes(url))
            if not isinstance(reply, list):
                raise RuntimeError(
                    f"tree listing for {fam!r} failed: {reply!r}")
            paths.extend(e["path"] for e in reply
                         if e.get("type") == "blob")
            if len(reply) < per_page:
                break
            page += 1
        hits = sorted(p for p in paths if p.endswith(TASK_EXT))
        if not hits:
            raise ValueError(
                f"family {fam!r}: no {TASK_EXT} task definitions at "
                "the pinned commit")
        for p in hits:
            if p in seen:
                raise ValueError(
                    f"{p} selected by both {seen[p]!r} and {fam!r} — "
                    "families must not overlap")
            seen[p] = fam
        out.append((fam, hits))
    return out


# ---------------------------------------------------------------- parsing

def _scalar(raw: str, where: str) -> Any:
    """One task-definition scalar: quoted string, bare word, or bare
    boolean. Anything fancier (flow collections, anchors, multiline)
    aborts — strict beats subtly wrong."""
    s = raw.strip()
    if not s or s.startswith("#"):
        raise ValueError(f"{where}: empty or comment-only value")
    if s[0] in "'\"":
        if len(s) < 2 or s[-1] != s[0]:
            raise ValueError(f"{where}: unterminated quote in {raw!r}")
        body = s[1:-1]
        return body.replace("''", "'") if s[0] == "'" else body
    if any(c in s for c in "[]{}&*#|>%@`\","):
        raise ValueError(
            f"{where}: unsupported YAML in {raw!r} — the strict "
            "parser refuses what it cannot be sure of")
    if s in ("true", "false"):
        return s == "true"
    return s


def parse_task(text: str, where: str = "task") -> dict[str, Any]:
    """A task definition's semantic content: ``format_version``,
    ``input_files`` (normalized to a list), ``properties`` (dicts of
    scalar keys), ``options`` (dict of scalars). Block style with
    2-space indents only — the format the suite actually uses; any
    other shape aborts. Verified against PyYAML by ``_crosscheck``
    whenever that is importable."""
    task: dict[str, Any] = {"input_files": [], "properties": [],
                            "options": {}}
    section: str | None = None
    for n, line in enumerate(text.splitlines(), 1):
        at = f"{where}:{n}"
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if "\t" in line[:indent + 1]:
            raise ValueError(f"{at}: tab indentation")
        stripped = line.strip()
        if indent == 0:
            key, colon, rest = stripped.partition(":")
            if not colon or " " in key:
                raise ValueError(f"{at}: expected 'key:' at {line!r}")
            if key == "format_version":
                task["format_version"] = _scalar(rest, at)
                section = None
            elif key == "input_files":
                section = "input_files"
                if rest.strip():
                    task["input_files"].append(_scalar(rest, at))
            elif key in ("properties", "options"):
                if rest.strip():
                    raise ValueError(f"{at}: inline {key!r} value")
                section = key
            else:
                raise ValueError(f"{at}: unknown top-level key {key!r}")
        elif section == "input_files" and stripped.startswith("- "):
            task["input_files"].append(_scalar(stripped[2:], at))
        elif section == "properties" and stripped.startswith("- "):
            key, colon, rest = stripped[2:].partition(":")
            if not colon:
                raise ValueError(f"{at}: expected '- key:' at {line!r}")
            task["properties"].append({key.strip(): _scalar(rest, at)})
        elif section == "properties" and task["properties"]:
            key, colon, rest = stripped.partition(":")
            if not colon:
                raise ValueError(f"{at}: expected 'key:' at {line!r}")
            entry = task["properties"][-1]
            if key.strip() in entry:
                raise ValueError(f"{at}: duplicate {key!r} in entry")
            entry[key.strip()] = _scalar(rest, at)
        elif section == "options":
            key, colon, rest = stripped.partition(":")
            if not colon:
                raise ValueError(f"{at}: expected 'key:' at {line!r}")
            task["options"][key.strip()] = _scalar(rest, at)
        else:
            raise ValueError(f"{at}: unexpected line {line!r}")
    if not task["input_files"]:
        raise ValueError(f"{where}: no input_files")
    return task


def _crosscheck(text: str, task: dict[str, Any], where: str) -> None:
    """Compare the strict parse against PyYAML where available — the
    belt to the parser's suspenders. A disagreement aborts authoring;
    silence when PyYAML is absent is fine because the strict parser
    already refused everything it was unsure of."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return
    ref = yaml.safe_load(text)
    files = ref.get("input_files", [])
    mine = {
        "input_files": [files] if isinstance(files, str) else list(files),
        "properties": [dict(e) for e in ref.get("properties", [])],
        "options": dict(ref.get("options", {})),
        "format_version": str(ref.get("format_version")),
    }
    got = dict(task)
    got["format_version"] = str(got.get("format_version"))
    if got != mine:
        raise RuntimeError(
            f"{where}: strict parse disagrees with PyYAML —\n"
            f"  strict: {got!r}\n  pyyaml: {mine!r}")


# --------------------------------------------------------------- selection

def select_unreach(task: dict[str, Any],
                   where: str) -> tuple[str | None, str | None]:
    """``(verdict, skip_reason)`` — exactly one is set, except the
    unlabeled-but-selected case ``(None, None)``. Selection means the
    task asks the reachability question of a single program file;
    every rejection is a named reason the caller must report."""
    unreach = [e for e in task["properties"]
               if str(e.get("property_file", "")).endswith(UNREACH_PRP)]
    if not unreach:
        return None, "no-unreach-call-property"
    if len(unreach) > 1:
        raise ValueError(f"{where}: {len(unreach)} unreach-call entries")
    if len(task["input_files"]) != 1:
        return None, "multi-file-task"
    lang = task["options"].get("language")
    if lang is not None and lang != "C":
        return None, f"language-{lang}"
    verdict = unreach[0].get("expected_verdict")
    if verdict is None:
        return None, None  # pinned unlabeled — the protocol labels it
    if not isinstance(verdict, bool):
        raise ValueError(f"{where}: non-boolean expected_verdict "
                         f"{verdict!r}")
    return VERDICT[verdict], None


def program_path(yml_path: str, input_file: str) -> str:
    """The program's repo path, resolved relative to its task
    definition; escaping the repository root aborts."""
    p = posixpath.normpath(
        posixpath.join(posixpath.dirname(yml_path), input_file))
    if p.startswith("../") or p.startswith("/"):
        raise ValueError(f"{yml_path}: input file {input_file!r} "
                         "escapes the repository")
    return p


# ---------------------------------------------------------------- pinning

def pin(*, suite: str, project: str, commit: str, families: list[str],
        fetch_bytes: FetchFn = _curl, cache_dir: str | None = None,
        per_page: int = 100,
        progress: Callable[[str], None] | None = None,
        ) -> tuple[Benchmark, dict[str, int]]:
    """Fetch, parse, select, hash, and assemble the suite, plus the
    skip census by reason. Pure but for the fetch and the optional
    cache writes; any failure raises before anything is returned, so
    a caller never holds a partial pin."""
    selected = list_tasks(project, commit, families, fetch_bytes,
                          per_page=per_page)
    fam_of = {p: fam for fam, hits in selected for p in hits}
    ymls = sorted(fam_of)
    names = assign_names(ymls, ext=TASK_EXT)

    raw_url = f"https://gitlab.com/{project}/-/raw/{commit}"
    total = len(ymls)
    instances = []
    skips: dict[str, int] = {}
    for i, yml_path in enumerate(ymls, 1):
        yml_bytes = fetch_bytes(f"{raw_url}/{yml_path}")
        task = parse_task(yml_bytes.decode("utf-8"), where=yml_path)
        _crosscheck(yml_bytes.decode("utf-8"), task, where=yml_path)
        expected, skip = select_unreach(task, where=yml_path)
        if skip is not None:
            skips[skip] = skips.get(skip, 0) + 1
            if progress is not None:
                progress(f"skipped {yml_path} ({skip}) ({i}/{total})")
            continue
        prog = program_path(yml_path, task["input_files"][0])
        data = fetch_bytes(f"{raw_url}/{prog}")
        name = names[yml_path]
        if cache_dir is not None:
            with open(os.path.join(cache_dir, f"{suite}-{name}"),
                      "wb") as f:
                f.write(data)
        meta: dict[str, Any] = {
            "family": family_label(fam_of[yml_path]),
            "task": yml_path,
            "task_sha256": hashlib.sha256(yml_bytes).hexdigest(),
            "property": "unreach-call",
        }
        if "data_model" in task["options"]:
            meta["data_model"] = task["options"]["data_model"]
        instances.append(Instance(
            name=name, path=prog,
            sha256=hashlib.sha256(data).hexdigest(),
            question=Question(source="c", shape="reachability",
                              program=name),
            expected=expected, meta=meta))
        if progress is not None:
            progress(f"pinned {name} ({i}/{total})")
        del data, yml_bytes  # one task fully, then release

    if not instances:
        raise ValueError(
            f"no task selected — skips by reason: {skips!r}")
    return (Benchmark(suite=suite, source=f"gitlab:{project}@{commit}",
                      instances=tuple(instances)), skips)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--suite", required=True)
    ap.add_argument("--family", action="append", required=True,
                    dest="families", metavar="PREFIX",
                    help="repo path prefix, e.g. c/bitvector "
                         "(repeatable)")
    ap.add_argument("-o", "--out", required=True,
                    help="benchmark JSON to write")
    ap.add_argument("--project", default=SVCOMP_PROJECT)
    ap.add_argument("--commit", default=SVCOMP_COMMIT)
    ap.add_argument("--cache",
                    help="cache dir (default: the shared "
                         "streamed-with-pin cache)")
    args = ap.parse_args()

    cache = bench_mod._cache_dir(args.cache)
    bench, skips = pin(suite=args.suite, project=args.project,
                       commit=args.commit, families=args.families,
                       cache_dir=cache, progress=print)

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
          f"{labeled} labeled; "
          f"skips {skips or '{}'}; source {bench.source}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
