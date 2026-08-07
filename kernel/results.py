"""The result core (KERNEL.md §§1–3): schema, order, log, frontier, report.

A result is the only currency. Its value is one of::

    {"kind": "witness", "payload": ..., "depth": k}      -- replayed, always
    {"kind": "all", "bound": k | "inf", "cert": ...}     -- graded universal
    {"kind": "partial", "progress": {...}}               -- how far, and why

Results order per question — level (partial < all-below-ask < terminal),
then bound, then grade; cost is recorded, never ranked. The log is
append-only JSONL; best-per-question over an append-only log is
monotone, which is the ratchet (mechanized in kernel/mechanization/).
The report is a pure function of (benchmark, log): regenerating it is
byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import os

#: The universal grade ladder, strict naming (KERNEL.md §2): "certified"
#: is reserved for source re-discharge; a replayed witness sits at the
#: same route-independent rung. "corroborated" is an orthogonal flag.
GRADES = {"": 0, "claimed": 1, "checked": 2, "certified": 3, "replayed": 3}

_INF = 10**18  # order-key stand-in for an unbounded bound


# -- questions and benchmarks -------------------------------------------------

def load_benchmark(path: str) -> dict:
    """Load a pinned benchmark and verify every program's sha256 pin."""
    with open(path, "rb") as fh:
        bench = json.loads(fh.read())
    base = os.path.dirname(os.path.abspath(path))
    for q in bench["questions"]:
        program = os.path.join(base, q["program"])
        with open(program, "rb") as pfh:
            digest = hashlib.sha256(pfh.read()).hexdigest()
        if digest != q["sha256"]:
            raise ValueError(f"benchmark pin violated: {q['id']} "
                             f"expected {q['sha256']} got {digest}")
        q["_program_path"] = program
    return bench


# -- the order ----------------------------------------------------------------

def _bound_key(bound) -> int:
    return _INF if bound == "inf" else int(bound)


def cap(bound, caps) -> int | str:
    """The route's effective universal bound: the meet (min) of the
    claim's bound and every hop's declared ``bound_cap`` — one more
    axis of the componentwise meet (KERNEL.md §1). A hop that reifies
    an unrolling (btor2--smtlib at k=20) caps what any claim crossing
    back may say; a bound-preserving hop declares nothing and caps
    nothing."""
    best = _bound_key(bound)
    for c in caps:
        best = min(best, _bound_key(c))
    return "inf" if best >= _INF else best


def covers(bound, ask) -> bool:
    """Does a universal claim to ``bound`` cover a question asked at ``ask``?"""
    return _bound_key(bound) >= _bound_key(ask)


def terminal(question: dict, value: dict) -> bool:
    """A replayed witness decides either mode; a universal claim decides
    when it covers the asked bound."""
    if value["kind"] == "witness":
        return True
    if value["kind"] == "all":
        return covers(value["bound"], question["bound"])
    return False


def key(question: dict, record: dict) -> tuple[int, int, int]:
    """The order key: (level, bound, grade). Strictly greater = better."""
    value, grade = record["value"], record.get("grade", "")
    if terminal(question, value):
        level, bound = 2, _INF if value["kind"] == "witness" \
            else _bound_key(value["bound"])
    elif value["kind"] == "all":
        level, bound = 1, _bound_key(value["bound"])
    else:
        level = 0
        bound = int(value["progress"].get("bound_reached", -1))
    return (level, bound, GRADES[grade])


def better(question: dict, a: dict, b: dict) -> bool:
    """Strict improvement of ``a`` over ``b`` for the same question."""
    return key(question, a) > key(question, b)


# -- the log ------------------------------------------------------------------

def append(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def load(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def best(bench: dict, records: list[dict]) -> dict[str, dict]:
    """Best result per question — earliest record wins ties, so the map
    is deterministic and appending can only improve it."""
    questions = {q["id"]: q for q in bench["questions"]}
    out: dict[str, dict] = {}
    for rec in records:
        qid = rec.get("question")
        if qid not in questions or "value" not in rec:
            continue
        if qid not in out or better(questions[qid], rec, out[qid]):
            out[qid] = rec
    return out


def frontier(bench: dict, records: list[dict]) -> list[str]:
    """Question ids whose best result is not terminal (unplayed included)."""
    bests = best(bench, records)
    open_qs = []
    for q in bench["questions"]:
        rec = bests.get(q["id"])
        if rec is None or not terminal(q, rec["value"]):
            open_qs.append(q["id"])
    return open_qs


def expanded(bench: dict, records: list[dict],
             baseline: list[dict]) -> list[str]:
    """Questions whose best result strictly improved over a baseline log —
    the definition of frontier expansion (level, bound, or grade; not
    cost)."""
    questions = {q["id"]: q for q in bench["questions"]}
    now, then = best(bench, records), best(bench, baseline)
    moved = []
    for qid, q in questions.items():
        if qid in now and (qid not in then or better(q, now[qid], then[qid])):
            moved.append(qid)
    return moved


def corroborated(bench: dict, records: list[dict]) -> set[str]:
    """Question ids whose settled verdict two records of **disjoint**
    recorded lineage agree on — the orthogonal flag of KERNEL.md §2.
    The flag belongs to the verdict, not to a record: any two terminal
    results of the best's kind whose lineages share nothing corroborate
    it. Lineages are stamped into records by the driver; a record
    without one never counts (btormc beside pono does not qualify:
    both descend from boolector, and the declarations say so)."""
    questions = {q["id"]: q for q in bench["questions"]}
    bests = best(bench, records)
    out: set[str] = set()
    for qid, rec in bests.items():
        q = questions[qid]
        if not terminal(q, rec["value"]):
            continue
        pool = [set(r["lineage"]) for r in records
                if r.get("question") == qid and "value" in r
                and r.get("lineage")
                and r["value"]["kind"] == rec["value"]["kind"]
                and terminal(q, r["value"])]
        if any(not (a & b)
               for i, a in enumerate(pool) for b in pool[i + 1:]):
            out.add(qid)
    return out


def contradictions(bench: dict, records: list[dict]) -> list[dict]:
    """A replayed witness beside a universal claim covering its depth.
    The witness is authoritative (replay is ground truth); the universal's
    certification chain is thereby falsified. Never silently resolved."""
    questions = {q["id"]: q for q in bench["questions"]}
    found = []
    by_q: dict[str, list[dict]] = {}
    for rec in records:
        if rec.get("question") in questions and "value" in rec:
            by_q.setdefault(rec["question"], []).append(rec)
    for qid, recs in by_q.items():
        witnesses = [r for r in recs if r["value"]["kind"] == "witness"]
        universals = [r for r in recs if r["value"]["kind"] == "all"]
        for w in witnesses:
            depth = int(w["value"].get("depth", 0))
            for u in universals:
                if covers(u["value"]["bound"], depth):
                    found.append({"question": qid, "witness": w,
                                  "universal": u})
    return found


# -- the report ---------------------------------------------------------------

def _show_value(value: dict) -> str:
    if value["kind"] == "witness":
        return f"witness (depth {value.get('depth', '?')})"
    if value["kind"] == "all":
        return f"all (bound {value['bound']})"
    note = value["progress"].get("note", "")
    return f"partial ({note})" if note else "partial"


def report(bench: dict, records: list[dict]) -> str:
    """The frontier summary — a pure function of (benchmark, log)."""
    bests = best(bench, records)
    open_qs = set(frontier(bench, records))
    contras = contradictions(bench, records)
    corrob = corroborated(bench, records)
    lines = [f"# Frontier — `{bench['name']}`", ""]
    n = len(bench["questions"])
    lines.append(f"{n - len(open_qs)} of {n} terminal; "
                 f"frontier holds {len(open_qs)}.")
    lines.append("")
    lines.append("| question | best result | grade | route | spent (s) |")
    lines.append("|---|---|---|---|---|")
    for q in sorted(bench["questions"], key=lambda q: q["id"]):
        rec = bests.get(q["id"])
        if rec is None:
            lines.append(f"| {q['id']} | — unplayed | | | |")
            continue
        grade = rec.get("grade", "")
        if q["id"] in corrob:
            grade += " +corroborated"
        spent = rec.get("budget", {}).get("spent_s", "")
        spent = f"{spent:.1f}" if isinstance(spent, float) else spent
        lines.append(f"| {q['id']} | {_show_value(rec['value'])} | {grade} "
                     f"| {'>'.join(rec.get('route', []))} | {spent} |")
    if open_qs:
        lines += ["", "## The frontier", ""]
        for qid in sorted(open_qs):
            rec = bests.get(qid)
            if rec is None:
                lines.append(f"- `{qid}` — unplayed")
            else:
                progress = rec["value"].get("progress", rec["value"])
                lines.append(f"- `{qid}` via `{'>'.join(rec['route'])}` — "
                             f"{json.dumps(progress, sort_keys=True)}")
    if contras:
        lines += ["", "## Contradictions (certification chain falsified)", ""]
        for c in contras:
            lines.append(f"- `{c['question']}`: replayed witness at depth "
                         f"{c['witness']['value'].get('depth')} vs universal "
                         f"to bound {c['universal']['value']['bound']} via "
                         f"`{'>'.join(c['universal'].get('route', []))}`")
    lines.append("")
    return "\n".join(lines)
