"""The result core (KERNEL.md §§1–3, §5): schema, order, log, frontier.

A result is the only currency. Its value is one of::

    {"kind": "witness", "payload": ..., "depth": k}      -- replayed, always
    {"kind": "all", "bound": k | "inf", "cert": ...}     -- graded universal
    {"kind": "partial", "progress": {...}}               -- how far, and why

A result that decides its question — a replayed witness, or a universal
claim covering the asked bound — is **settled** (a question settles at
a terminal; the entity holds the name, the predicate holds this one).
Results order per question — level (partial < all-below-ask <
settled), then bound, then grade; cost is recorded, never ranked. The
log is append-only JSONL; best-per-question over an append-only log is
monotone, which is the ratchet. The board and the graph are pure
functions of (registry, benchmark, log): regenerating is byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import os

#: The universal grade ladder, strict naming (KERNEL.md §3): "certified"
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


def key(question: dict, record: dict) -> tuple[int, int, int]:
    """The order key: (level, bound, grade). Strictly greater = better."""
    value, grade = record["value"], record.get("grade", "")
    if settled(question, value):
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
    recorded lineage agree on — the orthogonal flag of KERNEL.md §3.
    The flag belongs to the verdict, not to a record: any two settled
    results of the best's kind whose lineages share nothing corroborate
    it. Lineages are stamped into records by the driver; a record
    without one never counts — two terminals generated from the same
    ancestor procedure declare so, and do not qualify."""
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


# -- the board ----------------------------------------------------------------

def _show_value(value: dict) -> str:
    if value["kind"] == "witness":
        return f"witness (depth {value.get('depth', '?')})"
    if value["kind"] == "all":
        return f"all (bound {value['bound']})"
    note = value["progress"].get("note", "")
    return f"partial ({note})" if note else "partial"


def report(bench: dict, records: list[dict]) -> str:
    """The board — a pure function of (benchmark, log)."""
    bests = best(bench, records)
    open_qs = set(frontier(bench, records))
    contras = contradictions(bench, records)
    corrob = corroborated(bench, records)
    lines = [f"# Frontier — `{bench['name']}`", ""]
    n = len(bench["questions"])
    lines.append(f"{n - len(open_qs)} of {n} settled; "
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


# -- the graph ----------------------------------------------------------------

def dot(reg: dict, bench: dict, records: list[dict]) -> str:
    """The frontier drawn (KERNEL.md §5): the registry graph with the
    benchmark's best paths overlaid, as Graphviz DOT. Languages are
    nodes (a root carrying questions is annotated with its open count),
    admitted pairs are edges, admitted terminals are the sinks — every
    one of them drawn for every domain, because availability is
    universal (KERNEL.md §4) and an unreachable terminal is a visible
    conjecture: the dotted gap says which missing pair would connect
    it. An edge is bold where every question whose best path crosses it
    is settled, solid while one of them is still open, and dotted where
    no best path runs. A pure function of (registry, benchmark, log):
    regenerating it is byte-identical."""
    bests = best(bench, records)
    open_qs = set(frontier(bench, records))
    crossing: dict[str, list[str]] = {}
    for qid in sorted(bests):
        for eid in bests[qid].get("route", []):
            crossing.setdefault(eid, []).append(qid)
    asked: dict[str, list[str]] = {}
    for q in bench["questions"]:
        asked.setdefault(q["language"], []).append(q["id"])

    def style(eid: str) -> tuple[str, str]:
        qs = crossing.get(eid, [])
        if not qs:
            return "dotted", eid
        if any(qid in open_qs for qid in qs):
            return "solid", f"{eid} ({len(qs)})"
        return "bold", f"{eid} ({len(qs)})"

    n = len(bench["questions"])
    lines = [f'digraph "{bench["name"]}" {{',
             "  rankdir=LR; labelloc=t;",
             f'  label="{bench["name"]}: {n - len(open_qs)} of {n} '
             f'settled; frontier holds {len(open_qs)}";',
             "  node [shape=box];"]
    # Benchmark roots draw even before their language is registered,
    # so the empty-kernel bootstrap (KERNEL.md §6) has a graph too.
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
        s, label = style(pid)
        lines.append(f'  "{m["src"]}" -> "{m["tgt"]}" '
                     f'[style={s}, label="{label}"];')
    for name in sorted(reg["terminals"]):
        m = reg["terminals"][name]
        if "admission" not in m:
            continue
        lines.append(f'  "terminal:{name}" [shape=doubleoctagon, '
                     f'label="{name}"];')
        s, label = style(name)
        lines.append(f'  "{m["language"]}" -> "terminal:{name}" '
                     f'[style={s}, label="{label}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"
