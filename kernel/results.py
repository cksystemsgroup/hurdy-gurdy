"""The result core (KERNEL.md §4, §5): schema, order, gap, log, frontier.

A result is the only currency. Its value is one of::

    {"kind": "witness", "payload": ..., "depth": k}      -- replayed, always
    {"kind": "all", "bound": k | "inf", "cert": ...}     -- graded by its gap
    {"kind": "partial", "progress": {...}}               -- how far, and why

Grades are geometry (KERNEL.md §4): ``gap`` is the number of hops
between the question and the last arrival check the evidence passed —
``certified`` means gap 0, ``checked`` means gap > 0, ``claimed`` means
no check ever ran (its ``gap`` is ``null``: there is no check to
measure a distance to). ``trust`` is the residual: the lineage union
over the gap segment plus the judge that ran — each arrival check
removed everything upstream of it. A witness is certified or it is not
a result at all; its channel has never existed without its check.

Results order per question — level (partial < all-below-ask <
settled), then bound, then grade rung, then smaller gap; cost is
recorded, never ranked. The log is append-only JSONL;
best-per-question over an append-only log is monotone, which is the
ratchet. The board and the graph are pure functions of (registry,
benchmark, log): regenerating is byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import os

#: The grade ladder (KERNEL.md §4), strict: claimed < checked <
#: certified; "corroborated" is an orthogonal flag, never a rung.
GRADES = {"": 0, "claimed": 1, "checked": 2, "certified": 3}

_INF = 10**18   # order-key stand-in for an unbounded bound
_NOGAP = 10**9  # order-key stand-in when no arrival check ever ran


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
    axis of the componentwise meet (KERNEL.md §5). A hop that reifies
    an unrolling caps what any claim crossing back may say; a
    bound-preserving hop declares nothing and caps nothing."""
    best = _bound_key(bound)
    for c in caps:
        best = min(best, _bound_key(c))
    return "inf" if best >= _INF else best


def covers(bound, ask) -> bool:
    """Does a universal claim to ``bound`` cover a question asked at ``ask``?"""
    return _bound_key(bound) >= _bound_key(ask)


def settled(question: dict, value: dict) -> bool:
    """A replayed witness decides either mode; a universal claim decides
    when it covers the asked bound."""
    if value["kind"] == "witness":
        return True
    if value["kind"] == "all":
        return covers(value["bound"], question["bound"])
    return False


def key(question: dict, record: dict) -> tuple[int, int, int, int]:
    """The order key: (level, bound, grade rung, -gap). Strictly
    greater = better; a smaller gap beats a larger one at the same
    rung, so a grade-raising replay is a strict improvement."""
    value, grade = record["value"], record.get("grade", "")
    if settled(question, value):
        level, bound = 2, _INF if value["kind"] == "witness" \
            else _bound_key(value["bound"])
    elif value["kind"] == "all":
        level, bound = 1, _bound_key(value["bound"])
    else:
        level = 0
        bound = int(value["progress"].get("bound_reached", -1))
    gap = record.get("gap")
    return (level, bound, GRADES[grade],
            -(gap if isinstance(gap, int) else _NOGAP))


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
    """Best result per question. The ratchet is on the key alone —
    appending can only improve it — and among records of equal key the
    latest wins, so the board shows the most recent adjudication of an
    equally good path: a certificate re-judged under a revised judge
    (``regrade``) carries the trust the current registry derives, not
    the one a superseded judge did."""
    questions = {q["id"]: q for q in bench["questions"]}
    out: dict[str, dict] = {}
    for rec in records:
        qid = rec.get("question")
        if qid not in questions or "value" not in rec:
            continue
        if qid not in out or not better(questions[qid], out[qid], rec):
            out[qid] = rec
    return out


def frontier(bench: dict, records: list[dict]) -> list[str]:
    """Question ids whose best result is not settled (unplayed included)."""
    bests = best(bench, records)
    open_qs = []
    for q in bench["questions"]:
        rec = bests.get(q["id"])
        if rec is None or not settled(q, rec["value"]):
            open_qs.append(q["id"])
    return open_qs


def expanded(bench: dict, records: list[dict],
             baseline: list[dict]) -> list[str]:
    """Questions whose best result strictly improved over a baseline log
    — the definition of frontier expansion (level, bound, grade, or
    gap; never cost)."""
    questions = {q["id"]: q for q in bench["questions"]}
    now, then = best(bench, records), best(bench, baseline)
    moved = []
    for qid, q in questions.items():
        if qid in now and (qid not in then or better(q, now[qid], then[qid])):
            moved.append(qid)
    return moved


def corroborated(bench: dict, records: list[dict]) -> set[str]:
    """Question ids whose settled verdict two records of **disjoint**
    recorded descent agree on — the orthogonal flag of KERNEL.md §4.
    The flag belongs to the verdict, not to a record: any two settled
    results of the best's kind whose lineages share nothing corroborate
    it. Lineages are stamped into records by the driver — the full
    generated descent of the route, distinct from the residual
    ``trust`` — and a record without one never counts: two searches
    grown from the same ancestor procedure declare so, and do not
    qualify."""
    questions = {q["id"]: q for q in bench["questions"]}
    bests = best(bench, records)
    out: set[str] = set()
    for qid, rec in bests.items():
        q = questions[qid]
        if not settled(q, rec["value"]):
            continue
        pool = [set(r["lineage"]) for r in records
                if r.get("question") == qid and "value" in r
                and r.get("lineage")
                and r["value"]["kind"] == rec["value"]["kind"]
                and settled(q, r["value"])]
        if any(not (a & b)
               for i, a in enumerate(pool) for b in pool[i + 1:]):
            out.add(qid)
    return out


def contradictions(bench: dict, records: list[dict]) -> list[dict]:
    """A replayed witness beside a universal claim covering its depth.
    The witness is authoritative (replay is ground truth); the
    universal's entire chain — evidence, checks, and every transport it
    crossed — is thereby falsified. Never silently resolved."""
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


# -- the board ----------------------------------------------------------------

def _show_value(value: dict) -> str:
    if value["kind"] == "witness":
        return f"witness (depth {value.get('depth', '?')})"
    if value["kind"] == "all":
        return f"all (bound {value['bound']})"
    note = value["progress"].get("note", "")
    return f"partial ({note})" if note else "partial"


def _show_gap(record: dict) -> str:
    gap = record.get("gap")
    return str(gap) if isinstance(gap, int) else "—"


def _show_trust(record: dict) -> str:
    trust = record.get("trust")
    if not trust:
        # a graded result resting on nothing but its judge says so; an
        # ungraded one has nothing to rest on yet
        return "judge only" if record.get("grade") else "—"
    return " ".join(trust)


def _ledger_rows(bench: dict, records: list[dict]) -> list[str]:
    """One row per question with any ledger beside a path (KERNEL.md
    §5): the tightest witness-surprisal lower bound any search
    reported, and the largest stimulus space any universal claim
    cleared with the clearance rate of the path that cleared it.
    Read off the log, never ranked."""
    rows = []
    for q in sorted(bench["questions"], key=lambda q: q["id"]):
        recs = [r for r in records if r.get("question") == q["id"]
                and isinstance(r.get("ledger"), dict)]
        if not recs:
            continue
        s_min = max((r["ledger"]["S_bits_min"] for r in recs
                     if isinstance(r["ledger"].get("S_bits_min"),
                                   (int, float))), default=None)
        cleared = [r for r in recs
                   if r["ledger"].get("B_bits") is not None]
        if not cleared and s_min is None:
            continue
        b_show, rate, via = "—", "—", "—"
        if cleared:
            top = max(cleared, key=lambda r: (
                _bound_key(r["ledger"]["B_bits"]),
                -r.get("budget", {}).get("spent_s", 0.0)))
            b = top["ledger"]["B_bits"]
            spent = top.get("budget", {}).get("spent_s", 0.0)
            b_show = str(b)
            if b != "inf" and isinstance(spent, (int, float)) and spent > 0:
                rate = f"{b / spent:.0f}"
            elif b == "inf":
                rate = "∞"
            via = ">".join(top.get("route", []))
        rows.append(f"| {q['id']} | "
                    f"{'—' if s_min is None else f'{s_min:.1f}'} | "
                    f"{b_show} | {rate} | {via} |")
    return rows


def report(bench: dict, records: list[dict]) -> str:
    """The board — a pure function of (benchmark, log): one row per
    question, its best graded path — result, grade, gap, residual
    trust, route, cost (KERNEL.md §5)."""
    bests = best(bench, records)
    open_qs = set(frontier(bench, records))
    contras = contradictions(bench, records)
    corrob = corroborated(bench, records)
    lines = [f"# Frontier — `{bench['name']}`", ""]
    n = len(bench["questions"])
    lines.append(f"{n - len(open_qs)} of {n} settled; "
                 f"frontier holds {len(open_qs)}.")
    lines.append("")
    lines.append("| question | best result | grade | gap | trust | route "
                 "| spent (s) |")
    lines.append("|---|---|---|---|---|---|---|")
    for q in sorted(bench["questions"], key=lambda q: q["id"]):
        rec = bests.get(q["id"])
        if rec is None:
            lines.append(f"| {q['id']} | — unplayed | | | | | |")
            continue
        grade = rec.get("grade", "")
        if q["id"] in corrob:
            grade += " +corroborated"
        spent = rec.get("budget", {}).get("spent_s", "")
        spent = f"{spent:.1f}" if isinstance(spent, float) else spent
        lines.append(f"| {q['id']} | {_show_value(rec['value'])} | {grade} "
                     f"| {_show_gap(rec)} | {_show_trust(rec)} "
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
    ledger = _ledger_rows(bench, records)
    if ledger:
        lines += ["", "## Ledger (bits bought; profiling, never a grade)",
                  "", "| question | S ≥ (bits) | B (bits) | B/spent "
                  "(bits/s) | via |", "|---|---|---|---|---|"]
        lines += ledger
    if contras:
        lines += ["", "## Contradictions (chain falsified)", ""]
        for c in contras:
            lines.append(f"- `{c['question']}`: replayed witness at depth "
                         f"{c['witness']['value'].get('depth')} vs universal "
                         f"to bound {c['universal']['value']['bound']} via "
                         f"`{'>'.join(c['universal'].get('route', []))}` — "
                         "the universal's evidence, checks, and every "
                         "transport it crossed are falsified")
    lines.append("")
    return "\n".join(lines)


# -- the graph ----------------------------------------------------------------

def dot(reg: dict, bench: dict, records: list[dict]) -> str:
    """The frontier drawn (KERNEL.md §5): the registry graph with the
    benchmark's best paths overlaid, as Graphviz DOT. Languages are
    nodes (a root carrying questions is annotated with its open count),
    admitted pairs are edges labeled with their channel set — grades
    being geometry, a missing channel is a visible conjecture: the
    label says which carry-back would move a grade — and admitted
    searches are the stops, every one of them drawn for every domain,
    because availability is universal (KERNEL.md §7) and an unreachable
    stop is a visible conjecture too. An edge is bold where every
    question whose best path crosses it is settled, solid while one of
    them is still open, and dotted where no best path runs. A pure
    function of (registry, benchmark, log): regenerating it is
    byte-identical."""
    bests = best(bench, records)
    open_qs = set(frontier(bench, records))
    crossing: dict[str, list[str]] = {}
    for qid in sorted(bests):
        for eid in bests[qid].get("route", []):
            crossing.setdefault(eid, []).append(qid)
    asked: dict[str, list[str]] = {}
    for q in bench["questions"]:
        asked.setdefault(q["language"], []).append(q["id"])

    def style(eid: str, label: str) -> tuple[str, str]:
        qs = crossing.get(eid, [])
        if not qs:
            return "dotted", label
        if any(qid in open_qs for qid in qs):
            return "solid", f"{label} ({len(qs)})"
        return "bold", f"{label} ({len(qs)})"

    n = len(bench["questions"])
    lines = [f'digraph "{bench["name"]}" {{',
             "  rankdir=LR; labelloc=t;",
             f'  label="{bench["name"]}: {n - len(open_qs)} of {n} '
             f'settled; frontier holds {len(open_qs)}";',
             "  node [shape=box];"]
    # Benchmark roots draw even before their language is registered,
    # so the empty-kernel bootstrap (KERNEL.md §8) has a graph too.
    for name in sorted(set(reg["languages"]) | set(asked)):
        qs = asked.get(name, [])
        if qs:
            k = sum(1 for qid in qs if qid in open_qs)
            lines.append(f'  "{name}" [peripheries=2, '
                         f'label="{name}\\n{len(qs)} questions, '
                         f'{k} open"];')
        else:
            lines.append(f'  "{name}";')
    for pid in sorted(reg["pairs"]):
        m = reg["pairs"][pid]
        if "admission" not in m:
            continue
        chans = " ".join(c for c in ("prog", "wit", "obs", "claim",
                                     "cert", "hint")
                         if c in m.get("channels", []))
        s, label = style(pid, f"{pid}\\n[{chans}]")
        lines.append(f'  "{m["src"]}" -> "{m["tgt"]}" '
                     f'[style={s}, label="{label}"];')
    for name in sorted(reg["searches"]):
        m = reg["searches"][name]
        if "admission" not in m:
            continue
        lines.append(f'  "search:{name}" [shape=doubleoctagon, '
                     f'label="{name}"];')
        s, label = style(name, name)
        lines.append(f'  "{m["language"]}" -> "search:{name}" '
                     f'[style={s}, label="{label}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"
