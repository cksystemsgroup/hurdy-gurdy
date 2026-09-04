"""The result order, best-per-question, the frontier, the ledger rows,
contradiction events and the corroborated flag (KERNEL.md §4, §5).

Everything here is a pure function of (benchmark, log).  The order is the
four-part key stated in §5 -- ``(level, bound, grade, gap)``, compared
lexicographically, strictly greater is better -- with "latest wins among
equal keys".
"""

INF = float("inf")

GRADE_RANK = {"": 0, "claimed": 1, "checked": 2, "certified": 3}


def _num(x):
    """A bound as a number: ``"inf"`` -> +inf; ints/floats as they are."""
    if x == "inf" or x is INF:
        return INF
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return x


def asked_bound(question):
    b = _num(question.get("bound"))
    return INF if b is None else b


def covers(claim_bound, bound):
    """Does a universal claim at ``claim_bound`` cover ``bound``?"""
    return claim_bound == INF or claim_bound >= bound


def is_result(record, questions):
    """A log record is a result iff it carries a value and names a
    question of the benchmark (event records are not results)."""
    if not isinstance(record, dict) or "event" in record:
        return False
    value = record.get("value")
    if not isinstance(value, dict):
        return False
    return record.get("question") in questions


def value_kind(record):
    kind = record["value"].get("kind")
    return kind if kind in ("witness", "all", "partial") else "partial"


def claim_bound(record):
    """Numeric bound of a universal claim (None if malformed)."""
    return _num(record["value"].get("bound"))


def partial_bound(record):
    """The bound a partial reached, read from its typed core
    ``progress.bound_reached`` (KERNEL.md §5); None if it records none."""
    progress = record["value"].get("progress")
    if not isinstance(progress, dict):
        return None
    return _num(progress.get("bound_reached"))


def level(record, question):
    """0 a partial; 1 a universal claim below the asked bound; 2 settled."""
    kind = value_kind(record)
    if kind == "witness":
        return 2
    if kind == "all":
        b = claim_bound(record)
        if b is None:
            return 0
        return 2 if covers(b, asked_bound(question)) else 1
    return 0


def order_key(record, question):
    kind = value_kind(record)
    lvl = level(record, question)
    if kind == "witness":
        bound = (2, 0)  # above every number, and above inf
    elif kind == "all":
        b = claim_bound(record)
        if b is None:
            bound = (-1, 0)
        elif b == INF:
            bound = (1, 0)
        else:
            bound = (0, b)
    else:
        b = partial_bound(record)
        bound = (-1, 0) if b is None else (0, b)
    grade = record.get("grade")
    grade_rank = GRADE_RANK.get(grade if isinstance(grade, str) else "", 0)
    gap = record.get("gap")
    gap_key = -gap if isinstance(gap, (int, float)) and not isinstance(gap, bool) else -INF
    return (lvl, bound, grade_rank, gap_key)


def settled(record, question):
    return level(record, question) == 2


def results_by_question(benchmark, log):
    """Per question id, its results in log order."""
    questions = {q["id"]: q for q in benchmark["questions"]}
    per = {qid: [] for qid in questions}
    for record in log:
        if is_result(record, questions):
            per[record["question"]].append(record)
    return questions, per


def best_per_question(questions, per):
    """The incumbent per question: strictly better replaces; among equal
    keys the latest wins.  Unplayed questions map to None."""
    best = {}
    for qid, records in per.items():
        q = questions[qid]
        incumbent, incumbent_key = None, None
        for r in records:
            k = order_key(r, q)
            if incumbent is None or k >= incumbent_key:
                incumbent, incumbent_key = r, k
        best[qid] = incumbent
    return best


def contradictions(questions, per):
    """Contradiction events: a replayed witness at depth d beside a
    universal claim whose bound covers d, on the same question."""
    events = []
    for qid, records in per.items():
        witnesses = [r for r in records if value_kind(r) == "witness"]
        claims = [r for r in records if value_kind(r) == "all"]
        for w in witnesses:
            d = _num(w["value"].get("depth"))
            if d is None:
                continue
            for c in claims:
                b = claim_bound(c)
                if b is not None and covers(b, d):
                    events.append({"question": qid, "witness": w, "claim": c})
    return events


def corroborated(question, records, best):
    """Two settled results of the best's kind on the question whose
    recorded lineage sets are disjoint.  A record with no recorded lineage
    (missing or empty) never counts: it corroborates nothing."""
    if best is None or not settled(best, question):
        return False
    kind = value_kind(best)
    lineages = []
    for r in records:
        if value_kind(r) != kind or not settled(r, question):
            continue
        lineage = r.get("lineage")
        if isinstance(lineage, list) and lineage:
            lineages.append(frozenset(lineage))
    for i in range(len(lineages)):
        for j in range(i + 1, len(lineages)):
            if not (lineages[i] & lineages[j]):
                return True
    return False


def route_text(record):
    route = record.get("route")
    if isinstance(route, str):
        return route
    if isinstance(route, list):
        return ">".join(str(hop) for hop in route)
    return ""


def ledger_row(records):
    """The ledger row of a question, or None when no result recorded a
    surprisal bound or cleared bits.

    S: the tightest (largest) recorded ``S_bits_min``.  B: the largest
    recorded ``B_bits`` (``"inf"`` above every number); among equal B the
    record that spent least, so the rate shown is the best clearance rate
    at that clearance; ``via`` is that record's route.
    """
    s_values = []
    b_candidates = []
    for r in records:
        ledger = r.get("ledger")
        if not isinstance(ledger, dict):
            continue
        s = _num(ledger.get("S_bits_min"))
        if s is not None:
            s_values.append(s)
        b = _num(ledger.get("B_bits"))
        if b is not None:
            budget = r.get("budget") if isinstance(r.get("budget"), dict) else {}
            spent = _num(budget.get("spent_s"))
            b_candidates.append((b, spent, r))
    if not s_values and not b_candidates:
        return None
    row = {"S": max(s_values) if s_values else None, "B": None, "spent": None, "via": None}
    if b_candidates:
        best = None
        for b, spent, r in b_candidates:
            spent_key = -spent if spent is not None else -INF
            k = (b, spent_key)
            if best is None or k > best[0]:
                best = (k, b, spent, r)
        _, b, spent, r = best
        row["B"] = b
        row["spent"] = spent
        row["via"] = route_text(r)
        row["record"] = r
    return row
