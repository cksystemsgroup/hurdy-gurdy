"""From-scratch DPLL search plus a from-scratch RUP proof checker.
Both are pure Python, sharing no code with cadical/z3: an independent
decision procedure and an independently-verifiable certificate format.

Proof format: an ordered list of clauses (each a list of ints), the
last of which is the empty clause. Each clause must be RUP (derivable
by unit propagation after assuming its negation) against the original
CNF plus every clause listed before it — the same discipline DRAT/RUP
proofs use, just without the hint numbers LRAT adds for speed.
"""


def parse_cnf(path):
    nvars = nclauses = 0
    clauses = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line[0] == "c":
                continue
            if line[0] == "p":
                _, _, nv, nc = line.split()
                nvars, nclauses = int(nv), int(nc)
                continue
            lits = [int(x) for x in line.split()]
            if lits[-1] != 0:
                raise ValueError(f"clause not zero-terminated: {line!r}")
            clauses.append(tuple(lits[:-1]))
    return nvars, nclauses, clauses


# ------------------------------------------------------------- search

class Budget(Exception):
    pass


def _propagate(clauses, assign):
    while True:
        conflict = None
        unit = None
        for clause in clauses:
            sat = False
            unresolved = []
            for lit in clause:
                v = abs(lit)
                val = assign.get(v)
                if val is None:
                    unresolved.append(lit)
                elif (lit > 0) == val:
                    sat = True
                    break
            if sat:
                continue
            if not unresolved:
                conflict = clause
                break
            if len(unresolved) == 1:
                unit = unresolved[0]
                break
        if conflict is not None:
            return "conflict"
        if unit is not None:
            assign[abs(unit)] = unit > 0
            continue
        return "fixpoint"


def _pick_var(clauses, nvars, assign):
    counts = {}
    for clause in clauses:
        sat = False
        unassigned = []
        for lit in clause:
            v = abs(lit)
            val = assign.get(v)
            if val is None:
                unassigned.append(v)
            elif (lit > 0) == val:
                sat = True
                break
        if sat:
            continue
        for v in unassigned:
            counts[v] = counts.get(v, 0) + 1
    if counts:
        return max(counts, key=counts.get)
    for v in range(1, nvars + 1):
        if v not in assign:
            return v
    return None


def solve(nvars, clauses, deadline, now):
    """Chronological DPLL. Returns (model | None, proof, nodes).
    Raises Budget(nodes) if `now()` passes `deadline` mid-search — the
    caller turns that into an honest partial, never a false answer."""
    proof = []
    nodes = [0]

    def dpll(assign, decisions):
        nodes[0] += 1
        if now() > deadline:
            raise Budget(nodes[0])
        status = _propagate(clauses, assign)
        if status == "conflict":
            proof.append(sorted({-d for d in decisions}, key=abs))
            return None
        if len(assign) == nvars:
            return dict(assign)
        var = _pick_var(clauses, nvars, assign)
        a1 = dict(assign)
        a1[var] = True
        r = dpll(a1, decisions + [var])
        if r is not None:
            return r
        a2 = dict(assign)
        a2[var] = False
        r = dpll(a2, decisions + [-var])
        if r is not None:
            return r
        proof.append(sorted({-d for d in decisions}, key=abs))
        return None

    model = dpll({}, [])
    return model, proof, nodes[0]


# ------------------------------------------------------------ checking

def _unit_propagate_conflict(clauses, assign):
    while True:
        progressed = False
        for clause in clauses:
            sat = False
            unresolved = []
            for lit in clause:
                v = abs(lit)
                val = assign.get(v)
                if val is None:
                    unresolved.append(lit)
                elif (lit > 0) == val:
                    sat = True
                    break
            if sat:
                continue
            if not unresolved:
                return True
            if len(unresolved) == 1:
                lit = unresolved[0]
                assign[abs(lit)] = lit > 0
                progressed = True
        if not progressed:
            return False


def _is_rup(clauses_so_far, candidate):
    assign = {}
    for lit in candidate:
        v = abs(lit)
        if v in assign and assign[v] != (lit > 0):
            return True  # candidate is a tautology
        assign[v] = not (lit > 0)
    return _unit_propagate_conflict(clauses_so_far, assign)


def verify(original_clauses, proof):
    """Checks every proof clause is RUP against original + prior proof
    clauses, and the proof ends in the empty clause. Independent of
    the search above: a wrong proof cannot pass just because a real
    solver produced it."""
    if not proof:
        return False, "empty proof"
    if list(proof[-1]) != []:
        return False, "proof does not end in the empty clause"
    clauses_so_far = list(original_clauses)
    for i, clause in enumerate(proof):
        if not all(isinstance(x, int) for x in clause):
            return False, f"line {i}: not a list of ints"
        if not _is_rup(clauses_so_far, clause):
            return False, f"line {i}: not RUP: {clause}"
        clauses_so_far.append(tuple(clause))
    return True, "ok"
