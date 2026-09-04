"""The board (frontier.md), the graph (frontier.dot) and the trusted base,
as text -- pure functions of (registry, benchmark, log).

The exact textual formats are not fixed by KERNEL.md; they were learned
from the committed runs/*/frontier.{md,dot} and the first kernel's CLI
output, and reproduced byte for byte.
"""

import json

from . import results as R

EM_DASH = "—"


def _bound_text(x):
    return "inf" if x == "inf" or x is R.INF else str(x)


def describe(record):
    """The 'best result' cell of a played question."""
    value = record["value"]
    kind = R.value_kind(record)
    if kind == "witness":
        return f"witness (depth {value.get('depth')})"
    if kind == "all":
        return f"all (bound {_bound_text(value.get('bound'))})"
    progress = value.get("progress")
    note = progress.get("note") if isinstance(progress, dict) else None
    return f"partial ({note})" if note else "partial"


def _spent_text(record):
    """An int spent prints verbatim, a float through %.1f, none as empty."""
    budget = record.get("budget") if isinstance(record.get("budget"), dict) else {}
    spent = budget.get("spent_s")
    if spent is None or isinstance(spent, bool):
        return ""
    if isinstance(spent, int):
        return str(spent)
    if isinstance(spent, float):
        return "%.1f" % spent
    return str(spent)


def _rate_text(b, spent):
    if b == R.INF:
        return "∞"
    if spent is None or spent <= 0:
        return EM_DASH
    return str(round(b / spent))


def _int_text(x):
    if x == R.INF:
        return "inf"
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def summarize(benchmark, log):
    questions, per = R.results_by_question(benchmark, log)
    best = R.best_per_question(questions, per)
    ids = sorted(questions)
    settled = [q for q in ids if best[q] is not None and R.settled(best[q], questions[q])]
    return {
        "questions": questions,
        "per": per,
        "best": best,
        "ids": ids,
        "settled": set(settled),
        "total": len(ids),
        "n_settled": len(settled),
        "n_open": len(ids) - len(settled),
    }


def board(registry, benchmark, log):
    s = summarize(benchmark, log)
    name = benchmark.get("name")
    lines = [
        f"# Frontier {EM_DASH} `{name}`",
        "",
        f"{s['n_settled']} of {s['total']} settled; frontier holds {s['n_open']}.",
        "",
        "| question | best result | grade | gap | trust | route | spent (s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for qid in s["ids"]:
        r = s["best"][qid]
        if r is None:
            lines.append(f"| {qid} | {EM_DASH} unplayed | | | | | |")
            continue
        raw_grade = r.get("grade") if isinstance(r.get("grade"), str) else ""
        grade = raw_grade
        if R.corroborated(s["questions"][qid], s["per"][qid], r):
            grade = (grade + " +corroborated").strip()
        gap = r.get("gap")
        gap_text = str(gap) if isinstance(gap, (int, float)) and not isinstance(gap, bool) else EM_DASH
        trust = r.get("trust")
        if isinstance(trust, list) and trust:
            trust_text = " ".join(str(t) for t in trust)
        else:
            # An empty residual trust: a graded result rests on its judge
            # alone; an ungraded one rests on nothing.
            trust_text = "judge only" if raw_grade else EM_DASH
        lines.append(
            f"| {qid} | {describe(r)} | {grade} | {gap_text} | {trust_text} | "
            f"{R.route_text(r)} | {_spent_text(r)} |"
        )
    lines += ["", "## The frontier", ""]
    for qid in s["ids"]:
        if qid in s["settled"]:
            continue
        r = s["best"][qid]
        if r is None:
            lines.append(f"- `{qid}` {EM_DASH} unplayed")
            continue
        if R.value_kind(r) == "partial":
            progress = r["value"].get("progress")
            payload = json.dumps(progress if progress is not None else {}, sort_keys=True)
        else:
            payload = json.dumps(r["value"], sort_keys=True)
        lines.append(f"- `{qid}` via `{R.route_text(r)}` {EM_DASH} {payload}")
    rows = []
    for qid in s["ids"]:
        row = R.ledger_row(s["per"][qid])
        if row is not None:
            rows.append((qid, row))
    if rows:
        lines += [
            "",
            "## Ledger (bits bought; profiling, never a grade)",
            "",
            "| question | S ≥ (bits) | B (bits) | B/spent (bits/s) | via |",
            "|---|---|---|---|---|",
        ]
        for qid, row in rows:
            s_text = EM_DASH if row["S"] is None else "%.1f" % row["S"]
            if row["B"] is None:
                b_text = rate = via = EM_DASH
            else:
                b_text = _int_text(row["B"])
                rate = _rate_text(row["B"], row["spent"])
                via = row["via"]
            lines.append(f"| {qid} | {s_text} | {b_text} | {rate} | {via} |")
    events = R.contradictions(s["questions"], s["per"])
    if events:
        lines += ["", "## Contradictions (chain falsified)", ""]
        for e in events:
            w, c = e["witness"], e["claim"]
            lines.append(
                f"- `{e['question']}`: replayed witness at depth {w['value'].get('depth')} "
                f"vs universal to bound {_bound_text(c['value'].get('bound'))} via "
                f"`{R.route_text(c)}` {EM_DASH} the universal's evidence, checks, and every "
                "transport it crossed are falsified"
            )
    return "\n".join(lines) + "\n"


def _edge_style(count, open_count):
    if count == 0:
        return "dotted"
    return "bold" if open_count == 0 else "solid"


def graph(registry, benchmark, log):
    s = summarize(benchmark, log)
    name = benchmark.get("name")
    questions, best = s["questions"], s["best"]
    per_language = {}
    open_language = {}
    for qid, q in questions.items():
        lang = q.get("language")
        per_language[lang] = per_language.get(lang, 0) + 1
        if qid not in s["settled"]:
            open_language[lang] = open_language.get(lang, 0) + 1
    pair_count, pair_open, search_count, search_open = {}, {}, {}, {}
    for qid, r in best.items():
        if r is None:
            continue
        route = r.get("route")
        hops = list(route) if isinstance(route, list) else [route]
        if not hops:
            continue
        is_open = qid not in s["settled"]
        *pairs, stop = hops
        for p in pairs:
            pair_count[p] = pair_count.get(p, 0) + 1
            pair_open[p] = pair_open.get(p, 0) + int(is_open)
        search_count[stop] = search_count.get(stop, 0) + 1
        search_open[stop] = search_open.get(stop, 0) + int(is_open)
    lines = [
        f'digraph "{name}" {{',
        "  rankdir=LR; labelloc=t;",
        f'  label="{name}: {s["n_settled"]} of {s["total"]} settled; frontier holds {s["n_open"]}";',
        "  node [shape=box];",
    ]
    for lang in sorted(registry["languages"]):
        if lang in per_language:
            lines.append(
                f'  "{lang}" [peripheries=2, label="{lang}\\n{per_language[lang]} questions, '
                f'{open_language.get(lang, 0)} open"];'
            )
        else:
            lines.append(f'  "{lang}";')
    for pid in sorted(registry["pairs"]):
        m = registry["pairs"][pid]["manifest"]
        channels = " ".join(str(c) for c in (m.get("channels") or []))
        count = pair_count.get(pid, 0)
        label = f"{pid}\\n[{channels}]" + (f" ({count})" if count else "")
        style = _edge_style(count, pair_open.get(pid, 0))
        lines.append(f'  "{m.get("src")}" -> "{m.get("tgt")}" [style={style}, label="{label}"];')
    for sid in sorted(registry["searches"]):
        m = registry["searches"][sid]["manifest"]
        count = search_count.get(sid, 0)
        label = sid + (f" ({count})" if count else "")
        style = _edge_style(count, search_open.get(sid, 0))
        lines.append(f'  "search:{sid}" [shape=doubleoctagon, label="{sid}"];')
        lines.append(f'  "{m.get("language")}" -> "search:{sid}" [style={style}, label="{label}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def base(registry):
    """The trusted base: admitted interpreters and their evidence checkers."""
    anchored_by = {}
    for dname in sorted(registry["domains"]):
        d = registry["domains"][dname]
        m = d["manifest"]
        stamp = m.get("admission") if isinstance(m.get("admission"), dict) else {}
        n = stamp.get("anchors")
        if not isinstance(n, int):
            anchors = m.get("anchors")
            n = len(anchors) if isinstance(anchors, list) else 0
        anchored_by.setdefault(m.get("root"), []).append((dname, n))
    lines = [f"# The trusted base {EM_DASH} judges only", ""]
    if not registry["languages"]:
        lines.append(f"(empty: zero admitted judges {EM_DASH} the kernel ships this way)")
    for lname in sorted(registry["languages"]):
        e = registry["languages"][lname]
        m = e["manifest"]
        stamp = m.get("admission") if isinstance(m.get("admission"), dict) else {}
        anchors = anchored_by.get(lname)
        if anchors:
            anchored = "anchored by " + ", ".join(f"{d} ({n} anchors)" for d, n in anchors)
        else:
            anchored = f"anchored by no domain {EM_DASH} corroborated only by its pairs' squares"
        lines.append(
            f"- interpreter `{e['label']}` {EM_DASH} vectors {stamp.get('vectors', 0)}, "
            f"controls {stamp.get('controls', 0)}; lineage {list(m.get('lineage') or [])!r}; {anchored}"
        )
        evidence = stamp.get("evidence") if isinstance(stamp.get("evidence"), dict) else {}
        for schema in sorted(evidence):
            j = evidence[schema] if isinstance(evidence[schema], dict) else {}
            lines.append(
                f"  - judge `{lname}:{schema}` {EM_DASH} vectors {j.get('vectors', 0)}, "
                f"controls {j.get('controls', 0)}"
            )
    lines += [
        "",
        "Everything else in the registry is untrusted syntax: every transport's output "
        "is only ever as good as the judgment it survives.",
    ]
    return "\n".join(lines) + "\n"
