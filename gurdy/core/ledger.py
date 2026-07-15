"""The ledger — the platform's books, where the economy of scale is kept
(ROUTES.md §6-7; AGENTS.md §1; POTENTIAL.md §3).

One append-only, opt-in, host-local file holds two kinds of record:

* **cost records** (``translate`` / ``decide`` / ``cross_check``) — what
  answering actually costs, written beside the work by the instrumented
  call sites, host-tagged because timings do not transfer between
  machines. They feed the measured axis of the route report.
* **demand records** (``demand``) — questions the platform could *not*
  satisfy, written by the diagnosis calls (``why_not``, ``trust_options``)
  with the generating question verbatim, the failing obstacle, the named
  generation target, and an **origin** tag (an organic player session vs
  a synthetic campaign — auditable, never just countable). They are the
  evidence a pair recommendation rests on: a pair is recommended by the
  demand that names it, and it pays by removing a named obstacle —
  **connectivity** or **shape** (new capability), **loss** (wider
  coverage), **cost** (better performance), **trust** (an independent
  anchor). One taxonomy, use to evolution: the obstacle that failed a
  question is the good the next pair sells. A registration brief cites
  its evidence (AGENTS.md §1).

Opt-in observability, never semantics: records are written only when a
ledger path is configured (``GURDY_LEDGER``; the older
``GURDY_COST_LEDGER`` is still honored; or ``configure()``), and nothing
here may touch a deterministic output, a verdict, or an artifact byte —
a record is written *beside* the work. Failed work records no cost (a
profile is "what this costs when it runs"); unmet demand records no
answer. The format is one JSON object per line, append-only.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import statistics
import time
from contextlib import contextmanager
from typing import Any, Iterator

_ENV = "GURDY_LEDGER"
_ENV_OLD = "GURDY_COST_LEDGER"  # honored for compatibility
_path_override: str | None = None


def configure(path: str | None) -> None:
    """Set (or with ``None`` clear) the ledger path programmatically;
    overrides the environment. Tests point this at a temp file."""
    global _path_override
    _path_override = path


def ledger_path() -> str | None:
    return (_path_override or os.environ.get(_ENV)
            or os.environ.get(_ENV_OLD) or None)


def enabled() -> bool:
    return ledger_path() is not None


def host_id() -> str:
    """A coarse host fingerprint: cost profiles must not silently mix
    machines (demand records carry it too, but pool regardless — a
    question is a question everywhere)."""
    return f"{platform.system()}-{platform.machine()}-cpus{os.cpu_count()}"


def record(kind: str, key: str, *, wall_s: float | None = None,
           cpu_s: float | None = None, **meta: Any) -> None:
    """Append one record. No-op unless a ledger is configured."""
    path = ledger_path()
    if path is None:
        return
    rec: dict[str, Any] = {
        "kind": kind,
        "key": key,
        "host": host_id(),
        "ts": round(time.time(), 3),
    }
    if wall_s is not None:
        rec["wall_s"] = round(float(wall_s), 6)
    if cpu_s is not None:
        rec["cpu_s"] = round(float(cpu_s), 6)
    for k, v in meta.items():
        if v is not None:
            rec[k] = v
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


@contextmanager
def timed(kind: str, key: str, **meta: Any) -> Iterator[dict[str, Any]]:
    """Time a block and record it on *success* (an exception records
    nothing). Yields a dict the block may fill with extra meta discovered
    mid-flight (output ``size``, the ``verdict``, ...)::

        with ledger.timed("translate", key, pair=pid) as extra:
            out = translator(program)
            extra["size"] = len(out)
    """
    extra: dict[str, Any] = {}
    if not enabled():
        yield extra
        return
    w0 = time.perf_counter()
    c0 = time.process_time()
    yield extra
    record(kind, key,
           wall_s=time.perf_counter() - w0,
           cpu_s=time.process_time() - c0,
           **{**meta, **extra})


def _records(path: str | None = None) -> list[dict[str, Any]]:
    p = path or ledger_path()
    if p is None or not os.path.exists(p):
        return []
    out: list[dict[str, Any]] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # a torn line never poisons the books
    return out


def _summary(walls: list[float]) -> dict[str, Any]:
    walls = sorted(walls)
    p90 = walls[-1] if len(walls) < 2 else statistics.quantiles(walls, n=10)[8]
    return {
        "n": len(walls),
        "wall_median_s": round(statistics.median(walls), 6),
        "wall_p90_s": round(p90, 6),
        "wall_total_s": round(sum(walls), 6),
    }


def profile(kind: str | None = None, *, host: str | None = "local",
            path: str | None = None, **match: Any) -> dict[str, Any] | None:
    """Summarize matching *cost* records: ``{n, wall_median_s, wall_p90_s,
    wall_total_s}``, or ``None`` when nothing matches — the honest
    "unmeasured", never a guessed zero. ``host="local"`` (default) keeps
    profiles single-machine; pass ``host=None`` to pool across hosts."""
    want_host = host_id() if host == "local" else host
    walls = [r["wall_s"] for r in _records(path)
             if r.get("wall_s") is not None
             and (kind is None or r.get("kind") == kind)
             and (want_host is None or r.get("host") == want_host)
             and all(r.get(k) == v for k, v in match.items())]
    return _summary(walls) if walls else None


def profiles_by(field: str, kind: str | None = None, *,
                host: str | None = "local", path: str | None = None,
                **match: Any) -> dict[str, dict[str, Any]]:
    """Per-value cost profiles grouped by ``field`` (e.g. decide profiles
    by ``engine``). Records missing the field or a timing are skipped."""
    want_host = host_id() if host == "local" else host
    groups: dict[str, list[float]] = {}
    for r in _records(path):
        if r.get("wall_s") is None:
            continue
        if kind is not None and r.get("kind") != kind:
            continue
        if want_host is not None and r.get("host") != want_host:
            continue
        if not all(r.get(k) == v for k, v in match.items()):
            continue
        val = r.get(field)
        if val is None:
            continue
        groups.setdefault(str(val), []).append(r["wall_s"])
    return {v: _summary(w) for v, w in sorted(groups.items())}


# --- the demand side of the books ---------------------------------------

# The five obstacles (whynot.py; trust is the fifth) are the single
# demand taxonomy: the obstacle that failed a question names what the
# next pair pays for. No parallel "currency" vocabulary.
OBSTACLES = ("connectivity", "loss", "shape", "cost", "trust")


def question_key(question: dict[str, Any]) -> str:
    """The identity of a question: distinct-question counts dedup on it."""
    return hashlib.sha256(
        json.dumps(question, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def demand(question: dict[str, Any], obstacle: str,
           target: dict[str, Any] | None, *, origin: str = "organic") -> None:
    """Record one unmet demand: the question verbatim, the first failing
    obstacle, and the generation target it names. ``origin`` separates an
    ``organic`` player session from a synthetic ``campaign`` — displayed
    apart, so a generator cannot launder manufactured demand into
    evidence. No-op unless a ledger is configured."""
    record("demand", question_key(question), question=question,
           obstacle=obstacle, target=target, origin=origin)


def _target_signature(target: dict[str, Any] | None) -> str:
    if not target:
        return "(none)"
    sig = {k: v for k, v in target.items() if k != "note"}
    return json.dumps(sig, sort_keys=True, default=str)


def demand_summary(path: str | None = None) -> list[dict[str, Any]]:
    """The books' demand side, aggregated per generation target: how many
    distinct questions name it (dedup by question identity), through
    which obstacles, from which origins, over what period. Sorted by distinct
    question count — evidence *volume*, not a value judgment: choosing
    what to build stays the human act of AGENTS.md §1."""
    groups: dict[str, dict[str, Any]] = {}
    for r in _records(path):
        if r.get("kind") != "demand":
            continue
        sig = _target_signature(r.get("target"))
        g = groups.setdefault(sig, {
            "target": r.get("target"),
            "obstacles": set(),
            "questions": set(),
            "origins": {},
            "first_ts": r.get("ts"),
            "last_ts": r.get("ts"),
        })
        g["obstacles"].add(r.get("obstacle"))
        g["questions"].add(r.get("key"))
        origin = r.get("origin", "organic")
        g["origins"][origin] = g["origins"].get(origin, 0) + 1
        ts = r.get("ts")
        if ts is not None:
            g["first_ts"] = min(g["first_ts"] or ts, ts)
            g["last_ts"] = max(g["last_ts"] or ts, ts)
    out = []
    for g in groups.values():
        out.append({
            "target": g["target"],
            "obstacles": sorted(o for o in g["obstacles"] if o),
            "distinct_questions": len(g["questions"]),
            "origins": dict(sorted(g["origins"].items())),
            "first_ts": g["first_ts"],
            "last_ts": g["last_ts"],
        })
    out.sort(key=lambda e: (-e["distinct_questions"],
                            _target_signature(e["target"])))
    return out


def _reset() -> None:
    """Test helper: forget the programmatic override."""
    global _path_override
    _path_override = None
