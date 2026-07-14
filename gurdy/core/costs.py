"""Host-local cost ledger — the measured fourth axis of the route report
(ROUTES.md §6; the other three, fidelity / direction / loss, compose from
declarations; cost is empirical or it is nothing).

Opt-in observability, never semantics: records are written only when a
ledger path is configured (the ``GURDY_COST_LEDGER`` environment variable,
or ``configure()``), and nothing here may touch a deterministic output, a
verdict, or an artifact byte — a record is written *beside* the work, keyed
by the same content address the cache uses, after the work succeeded.
Failed work is not recorded (a profile is "what this costs when it runs",
not an error census; failures stay first-class results elsewhere).

Records are **host-specific** — timings do not transfer between machines —
so the ledger is a local file, not a repo artifact, and ``profile()``
filters to the current host by default. The record format is one JSON
object per line, append-only::

    {"kind": "translate"|"decide"|"cross_check", "key": <content hash>,
     "wall_s": ..., "cpu_s": ..., "host": ..., "ts": ...,
     ...meta: pair/engine/version/language/k/size/verdict...}
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import time
from contextlib import contextmanager
from typing import Any, Iterator

_ENV = "GURDY_COST_LEDGER"
_path_override: str | None = None


def configure(path: str | None) -> None:
    """Set (or with ``None`` clear) the ledger path programmatically;
    overrides the environment variable. Tests point this at a temp file."""
    global _path_override
    _path_override = path


def ledger_path() -> str | None:
    return _path_override or os.environ.get(_ENV) or None


def enabled() -> bool:
    return ledger_path() is not None


def host_id() -> str:
    """A coarse host fingerprint: profiles must not silently mix machines."""
    return f"{platform.system()}-{platform.machine()}-cpus{os.cpu_count()}"


def record(kind: str, key: str, *, wall_s: float, cpu_s: float | None = None,
           **meta: Any) -> None:
    """Append one cost record. No-op unless a ledger is configured."""
    path = ledger_path()
    if path is None:
        return
    rec: dict[str, Any] = {
        "kind": kind,
        "key": key,
        "wall_s": round(float(wall_s), 6),
        "host": host_id(),
        "ts": round(time.time(), 3),
    }
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

        with costs.timed("translate", key, pair=pid) as extra:
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
                continue  # a torn line never poisons the profile
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
    """Summarize matching records: ``{n, wall_median_s, wall_p90_s,
    wall_total_s}``, or ``None`` when nothing matches — the honest
    "unmeasured", never a guessed zero. ``host="local"`` (default) keeps
    profiles single-machine; pass ``host=None`` to pool across hosts."""
    want_host = host_id() if host == "local" else host
    walls = [r["wall_s"] for r in _records(path)
             if (kind is None or r.get("kind") == kind)
             and (want_host is None or r.get("host") == want_host)
             and all(r.get(k) == v for k, v in match.items())]
    return _summary(walls) if walls else None


def profiles_by(field: str, kind: str | None = None, *,
                host: str | None = "local", path: str | None = None,
                **match: Any) -> dict[str, dict[str, Any]]:
    """Per-value profiles grouped by ``field`` (e.g. decide profiles by
    ``engine``). Records missing the field are skipped."""
    want_host = host_id() if host == "local" else host
    groups: dict[str, list[float]] = {}
    for r in _records(path):
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


def _reset() -> None:
    """Test helper: forget the programmatic override."""
    global _path_override
    _path_override = None
