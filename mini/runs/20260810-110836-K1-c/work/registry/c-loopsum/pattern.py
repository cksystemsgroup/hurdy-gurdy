"""Loop summarization for a restricted but real shape: a single top-level
loop `for (int I = INIT; I < BOUND; I++) BODY` (optionally wrapped in one
guarding `if`, no else) whose BODY is a flat list of statements each of
the form `VAR += LIT;` / `VAR -= LIT;` (or `VAR = VAR +/- LIT;`) — a
per-iteration constant delta, independent of any other loop-carried
variable.

Instead of unrolling, this derives the exact closed form
VAR_exit = VAR_init + delta * k, where k is the number of iterations the
loop actually ran, bounded above by a literal extracted from the guarding
`if` (e.g. "n <= 60000"). It only fires when that closed form is provably
free of 32-bit overflow across the whole reachable range of k — otherwise
it declines rather than risk an unsound shortcut, and whatever unrolling
solver is also registered is the fallback.

This is a genuinely different technique from both cbmc's SAT-based
unwinding and czlib's plain bounded unrolling: it proves loops whose body
is small relative to no bound at all, in O(1), independent of how large
the loop's actual trip count is."""

import czlib


def _flatten(stmts):
    out = []
    for s in stmts:
        if s[0] == 'block':
            out.extend(_flatten(s[1]))
        else:
            out.append(s)
    return out


def _count_loops(stmts):
    n = 0
    for s in stmts:
        if s[0] in ('for', 'while'):
            n += 1
        elif s[0] == 'if':
            n += _count_loops(_flatten([s[2]]))
            if s[3] is not None:
                n += _count_loops(_flatten([s[3]]))
    return n


def find_loop_context(stmts):
    """Locate the program's one loop, optionally under one guarding
    if/then (no else). Returns dict(guard, prefix, loop, suffix) or None
    if there isn't exactly one loop in this shape anywhere in the program."""
    top = _flatten(stmts)
    if _count_loops(top) != 1:
        return None
    guard = None
    block = top
    for s in top:
        if s[0] == 'if' and s[3] is None:
            inner = _flatten([s[2]])
            if any(x[0] in ('for', 'while') for x in inner):
                guard = s[1]
                block = inner
                break
    loop_idxs = [i for i, s in enumerate(block) if s[0] in ('for', 'while')]
    if len(loop_idxs) != 1:
        return None
    idx = loop_idxs[0]
    return {"guard": guard, "prefix": block[:idx], "loop": block[idx],
            "suffix": block[idx + 1:]}


def _literal_upper_bound(cond, varname):
    """Tightest N such that cond implies varname <= N, scanning && conjuncts
    (only; an || can't guarantee a bound, so we don't descend into one)."""
    bounds = []

    def walk(node):
        if node[0] == 'logic' and node[1] == '&&':
            walk(node[2])
            walk(node[3])
            return
        if node[0] == 'bin' and node[2] == ('var', varname) and node[1] in ('<=', '<') \
                and node[3][0] == 'num':
            bounds.append(node[3][1] - (0 if node[1] == '<=' else 1))
        if node[0] == 'bin' and node[3] == ('var', varname) and node[1] in ('>=', '>') \
                and node[2][0] == 'num':
            bounds.append(node[2][1] - (0 if node[1] == '>=' else 1))

    walk(cond)
    return min(bounds) if bounds else None


def _decl_literal(stmts, name):
    for s in stmts:
        if s[0] == 'decl' and s[1] == name and s[2] is not None and s[2][0] == 'num':
            return s[2][1]
    return None


def _body_deltas(body_stmts):
    deltas = {}
    for s in body_stmts:
        e = s[1] if s[0] == 'expr' else None
        if e is not None and e[0] == 'cassign' and e[1] in ('+', '-') and e[3][0] == 'num':
            var, d = e[2], (e[3][1] if e[1] == '+' else -e[3][1])
        elif e is not None and e[0] == 'assign' and e[2][0] == 'bin' \
                and e[2][1] in ('+', '-') and e[2][2] == ('var', e[1]) \
                and e[2][3][0] == 'num':
            var, d = e[1], (e[2][3][1] if e[2][1] == '+' else -e[2][3][1])
        else:
            return None
        if var in deltas:
            return None  # two updates to the same var — outside this shape
        deltas[var] = d
    return deltas


def analyze(stmts):
    """Returns a filled pattern dict on success, or (None, reason) on any
    shape this technique doesn't cover."""
    ctx = find_loop_context(stmts)
    if ctx is None:
        return None, "not exactly one loop in a supported position"
    loop = ctx["loop"]
    if loop[0] != 'for':
        return None, "not a for-loop"
    init, cond, upd, body = loop[1], loop[2], loop[3], loop[4]
    if init is None or init[0] != 'decl' or init[2] is None or init[2][0] != 'num':
        return None, "for-init is not `int I = <literal>`"
    ivar, ival = init[1], init[2][1]
    if cond is None or cond[0] != 'bin' or cond[1] != '<' \
            or cond[2] != ('var', ivar) or cond[3][0] != 'var':
        return None, "for-cond is not exactly `I < BOUND`"
    bound_var = cond[3][1]
    if upd != ('postop', '++', ivar):
        return None, "for-update is not `I++`"
    if ctx["guard"] is None:
        return None, "loop is not under a bound-establishing if"
    bound_lit = _literal_upper_bound(ctx["guard"], bound_var)
    if bound_lit is None:
        return None, f"no literal upper bound found for {bound_var!r}"
    body_list = _flatten([body])
    deltas = _body_deltas(body_list)
    if deltas is None:
        return None, "loop body is not a flat list of `VAR += LIT` updates"
    if not deltas:
        return None, "loop body updates nothing"
    inits = {}
    for var in deltas:
        v0 = _decl_literal(ctx["prefix"], var)
        if v0 is None:
            return None, f"no literal initializer found for accumulator {var!r}"
        inits[var] = v0
    # Either `I < bound_var` or `I <= bound_var`, with bound_var <= bound_lit:
    # the loop can run at most (bound_lit - ival) times before I exceeds it.
    max_k = max(0, bound_lit - ival)
    for var, d in deltas.items():
        v0 = inits[var]
        extreme = max(abs(v0), abs(v0 + d * max_k))
        if extreme >= (1 << 30):
            return None, f"{var!r} could reach {extreme}, too close to overflow to trust"
    if abs(ival) >= (1 << 30) or abs(bound_lit) >= (1 << 30):
        return None, "loop counter's own range is too close to overflow to trust"
    return {"ivar": ivar, "ival": ival, "bound_var": bound_var,
            "bound_lit": bound_lit, "deltas": deltas,
            "inits": inits, "guard": ctx["guard"], "prefix": ctx["prefix"],
            "suffix": ctx["suffix"]}, None


def build_closed_form(pat, env):
    """Given env (with pat['bound_var'] already bound to a BitVec), return
    a new env where the loop's variables hold their exact exit values."""
    bv = czlib.bv
    bound_val = env[pat["bound_var"]]
    init_bv = bv(pat["ival"])
    i_exit = czlib.z3.If(bound_val > init_bv, bound_val, init_bv)
    new_env = dict(env)
    new_env[pat["ivar"]] = i_exit
    k = i_exit - init_bv
    for var, d in pat["deltas"].items():
        new_env[var] = bv(pat["inits"][var]) + bv(d) * k
    return new_env
