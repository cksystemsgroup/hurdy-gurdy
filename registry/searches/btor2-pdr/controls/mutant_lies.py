"""MUTANT (the witness is written unreplayed, its last frame dropped) of btor2-pdr/solve.py — a negative control that must
fail the corpus.

btor2-pdr: property-directed reachability for BTOR2 that reasons
by proof obligations, lifted predecessors and counterexamples to
generalization, and writes the invariant it converges on as a
certificate judged by btor2's own `clauses` schema.

Usage: solve.py <program.btor2> <mode> <observable> <bound> <wall_s> [<hints>]

The machine is bit-blasted once, as a single transition step, into a
hash-consed and-inverter graph and Tseitin-encoded into one incremental
CDCL solver (two watched literals, VSIDS, phase saving, Luby restarts,
glue-based learnt reduction, assumption cores). Frames are delta-
encoded behind activation literals. Every state the solver hands back
— a bad state at the frontier, a predecessor of a proof obligation, a
counterexample to generalization — is *lifted* to a cube by the
assumption core of the query "this state under this input stays inside
the constraint and steps where it stepped", so a cube carries with it
the one input under which every state it names does the same thing;
that is what lets a trace of cubes reaching frame 0 be replayed as a
concrete stimulus through this search's own evaluator before it is
written. Proof obligations sit in a priority queue by frame, so the
deepest obligation is always served first and a blocked cube is pushed
as far forward as it stays relatively inductive, then re-queued at the
next frame until the frontier is reached. Generalization is MIC with
CTGs (Hassan, Bradley, Somenzi 2013): a literal is dropped when the
remaining cube is still relatively inductive; when it is not, the
counterexample to generalization is itself lifted, blocked and
generalized one level down if it is inductive there, otherwise the
cube is joined with it — bounded by a CTG count, a join count and a
recursion depth. Forward propagation after each frontier extension
subsumes clauses downward; an empty delta frame is convergence, and the
clauses above it are written as {"kind": "clause-invariant"} on the
all("inf") answer, discharged by the kernel through btor2's judge and
never taken on faith here.

Budgets are counted in propagations of the SAT solver and derive from
the wall argument, never the clock; a frontier that the budget leaves
fully cleared is answered as a bounded all(k), a trace as a witness,
anything else as an honest partial. Mode exists runs the same
obligation search capped at the asked bound, then bounded unrolling
with what remains of the budget. Arrays, unknown operators and
oversized transition cones are declined by name.
"""

import heapq
import json
import sys
import zlib

# -- the operator vocabulary of btor2@5's interpreter -------------------------

BINARY = ('and', 'or', 'xor', 'nand', 'nor', 'xnor', 'implies', 'iff',
          'eq', 'neq', 'ult', 'ulte', 'ugt', 'ugte', 'slt', 'slte', 'sgt',
          'sgte', 'add', 'sub', 'mul', 'udiv', 'urem', 'sdiv', 'srem',
          'smod', 'sll', 'srl', 'sra', 'concat')
UNARY = ('not', 'neg', 'inc', 'dec', 'redand', 'redor', 'redxor')
EXT = ('uext', 'sext')
CONSTS = ('const', 'constd', 'consth', 'zero', 'one', 'ones')
KNOWN = set(BINARY) | set(UNARY) | set(EXT) | set(CONSTS) | {
    'ite', 'slice', 'input', 'state'}

_MASKS = {}


def mask(w):
    m = _MASKS.get(w)
    if m is None:
        m = _MASKS[w] = (1 << w) - 1
    return m


class Decline(Exception):
    """The program lies outside this search's fragment; the message
    names why, and it is a pure function of the program text."""


class Prog:
    def __init__(self):
        self.width = {}      # node -> bit width
        self.op = {}         # node -> operator
        self.args = {}       # node -> raw operand tuple (ints; refs may be <0)
        self.const = {}      # node -> constant value
        self.order = []      # nodes in text order
        self.inputs = []
        self.states = []
        self.init = {}       # state -> value ref
        self.nxt = {}        # state -> value ref
        self.bads = []       # refs
        self.cons = []       # refs


def parse(path):
    sorts = {}
    p = Prog()
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    for raw in text.split('\n'):
        line = raw.split(';', 1)[0].strip()
        if not line:
            continue
        t = line.split()
        try:
            nid = int(t[0])
        except ValueError:
            continue
        op = t[1]
        if op == 'sort':
            if t[2] == 'bitvec':
                sorts[nid] = int(t[3])
            elif t[2] == 'array':
                raise Decline("array sort: outside btor2-pdr's fragment")
            else:
                raise Decline('unsupported sort: ' + t[2])
            continue
        if op == 'init':
            p.init[int(t[3])] = int(t[4])
            continue
        if op == 'next':
            p.nxt[int(t[3])] = int(t[4])
            continue
        if op == 'bad':
            p.bads.append(int(t[2]))
            continue
        if op == 'constraint':
            p.cons.append(int(t[2]))
            continue
        if op in ('output', 'fair', 'justice'):
            continue
        if op not in KNOWN:
            raise Decline('unsupported op: ' + op)
        if int(t[2]) not in sorts:
            raise Decline('unsupported sort: ' + t[2])
        w = sorts[int(t[2])]
        p.width[nid] = w
        p.op[nid] = op
        if op == 'input':
            p.inputs.append(nid)
            p.args[nid] = ()
        elif op == 'state':
            p.states.append(nid)
            p.args[nid] = ()
        elif op in CONSTS:
            if op == 'zero':
                v = 0
            elif op == 'one':
                v = 1
            elif op == 'ones':
                v = mask(w)
            elif op == 'const':
                v = int(t[3], 2)
            elif op == 'constd':
                v = int(t[3])
            else:
                v = int(t[3], 16)
            p.const[nid] = v & mask(w)
            p.args[nid] = ()
        else:
            args = []
            for a in t[3:]:
                try:
                    args.append(int(a))
                except ValueError:
                    break
            p.args[nid] = tuple(args)
        p.order.append(nid)
    for sid in p.states:
        if sid in p.nxt and abs(p.nxt[sid]) not in p.width:
            raise Decline('next refers to an unknown node')
    return p


# -- the evaluator: this search's own reading of btor2@5's semantics ----------

def _sgn(v, w):
    return v - (1 << w) if v >> (w - 1) else v


def eval_frame(p, regs, stim):
    vals = {}
    W = p.width

    def ref(r):
        v = vals[abs(r)]
        return (~v & mask(W[abs(r)])) if r < 0 else v

    for nid in p.order:
        op = p.op[nid]
        w = W[nid]
        a = p.args[nid]
        if op in CONSTS:
            vals[nid] = p.const[nid]
        elif op == 'input':
            vals[nid] = int(stim.get(str(nid), 0)) & mask(w)
        elif op == 'state':
            if nid in regs:
                vals[nid] = regs[nid]
            else:
                vals[nid] = int(stim.get(str(nid), 0)) & mask(w)
                regs[nid] = vals[nid]
        elif op == 'ite':
            vals[nid] = ref(a[1]) if ref(a[0]) else ref(a[2])
        elif op == 'slice':
            vals[nid] = (ref(a[0]) >> a[2]) & mask(w)
        elif op == 'uext':
            vals[nid] = ref(a[0])
        elif op == 'sext':
            vals[nid] = _sgn(ref(a[0]), W[abs(a[0])]) & mask(w)
        elif op == 'concat':
            vals[nid] = (ref(a[0]) << W[abs(a[1])]) | ref(a[1])
        elif op == 'not':
            vals[nid] = ~ref(a[0]) & mask(w)
        elif op == 'neg':
            vals[nid] = -ref(a[0]) & mask(w)
        elif op == 'inc':
            vals[nid] = (ref(a[0]) + 1) & mask(w)
        elif op == 'dec':
            vals[nid] = (ref(a[0]) - 1) & mask(w)
        elif op == 'redand':
            vals[nid] = 1 if ref(a[0]) == mask(W[abs(a[0])]) else 0
        elif op == 'redor':
            vals[nid] = 1 if ref(a[0]) else 0
        elif op == 'redxor':
            vals[nid] = bin(ref(a[0])).count('1') & 1
        elif op == 'and':
            vals[nid] = ref(a[0]) & ref(a[1])
        elif op == 'or':
            vals[nid] = ref(a[0]) | ref(a[1])
        elif op == 'xor':
            vals[nid] = ref(a[0]) ^ ref(a[1])
        elif op == 'nand':
            vals[nid] = ~(ref(a[0]) & ref(a[1])) & mask(w)
        elif op == 'nor':
            vals[nid] = ~(ref(a[0]) | ref(a[1])) & mask(w)
        elif op == 'xnor':
            vals[nid] = ~(ref(a[0]) ^ ref(a[1])) & mask(w)
        elif op == 'implies':
            vals[nid] = (1 ^ ref(a[0])) | ref(a[1])
        elif op == 'iff':
            vals[nid] = 1 ^ ref(a[0]) ^ ref(a[1])
        elif op == 'eq':
            vals[nid] = 1 if ref(a[0]) == ref(a[1]) else 0
        elif op == 'neq':
            vals[nid] = 1 if ref(a[0]) != ref(a[1]) else 0
        elif op == 'ult':
            vals[nid] = 1 if ref(a[0]) < ref(a[1]) else 0
        elif op == 'ulte':
            vals[nid] = 1 if ref(a[0]) <= ref(a[1]) else 0
        elif op == 'ugt':
            vals[nid] = 1 if ref(a[0]) > ref(a[1]) else 0
        elif op == 'ugte':
            vals[nid] = 1 if ref(a[0]) >= ref(a[1]) else 0
        elif op in ('slt', 'slte', 'sgt', 'sgte'):
            aw = W[abs(a[0])]
            x, y = _sgn(ref(a[0]), aw), _sgn(ref(a[1]), aw)
            if op == 'slt':
                vals[nid] = 1 if x < y else 0
            elif op == 'slte':
                vals[nid] = 1 if x <= y else 0
            elif op == 'sgt':
                vals[nid] = 1 if x > y else 0
            else:
                vals[nid] = 1 if x >= y else 0
        elif op == 'add':
            vals[nid] = (ref(a[0]) + ref(a[1])) & mask(w)
        elif op == 'sub':
            vals[nid] = (ref(a[0]) - ref(a[1])) & mask(w)
        elif op == 'mul':
            vals[nid] = (ref(a[0]) * ref(a[1])) & mask(w)
        elif op == 'udiv':
            d = ref(a[1])
            vals[nid] = (ref(a[0]) // d) & mask(w) if d else mask(w)
        elif op == 'urem':
            d = ref(a[1])
            vals[nid] = (ref(a[0]) % d) & mask(w) if d else ref(a[0])
        elif op in ('sdiv', 'srem', 'smod'):
            x, y = _sgn(ref(a[0]), w), _sgn(ref(a[1]), w)
            if op == 'sdiv':
                if y == 0:
                    vals[nid] = 1 if x < 0 else mask(w)
                else:
                    q = abs(x) // abs(y)
                    vals[nid] = (q if (x < 0) == (y < 0) else -q) & mask(w)
            elif op == 'srem':
                if y == 0:
                    vals[nid] = x & mask(w)
                else:
                    r = abs(x) % abs(y)
                    vals[nid] = (-r if x < 0 else r) & mask(w)
            else:
                if y == 0:
                    vals[nid] = x & mask(w)
                else:
                    u = abs(x) % abs(y)
                    if u == 0:
                        vals[nid] = 0
                    elif x >= 0 and y >= 0:
                        vals[nid] = u
                    elif x < 0 and y >= 0:
                        vals[nid] = (y - u) & mask(w)
                    elif x >= 0 and y < 0:
                        vals[nid] = (u + y) & mask(w)
                    else:
                        vals[nid] = (-u) & mask(w)
        elif op == 'sll':
            s = ref(a[1])
            vals[nid] = (ref(a[0]) << s) & mask(w) if s < w else 0
        elif op == 'srl':
            s = ref(a[1])
            vals[nid] = ref(a[0]) >> s if s < w else 0
        elif op == 'sra':
            s = ref(a[1])
            x = _sgn(ref(a[0]), w)
            if s < w:
                vals[nid] = (x >> s) & mask(w)
            else:
                vals[nid] = mask(w) if x < 0 else 0
        else:
            raise Decline('unsupported op: ' + op)
    return vals, ref


def evaluate(p, steps):
    """Run the machine on a stimulus the way btor2@5 does: returns the
    frame at which bad first fires with every constraint so far holding,
    else None."""
    regs = {}
    good = True
    for t, frame in enumerate(steps):
        if t == 0:
            _, tref = eval_frame(p, {}, frame)
            for sid, r in p.init.items():
                regs[sid] = tref(r) & mask(p.width[sid])
        vals, ref = eval_frame(p, regs, frame)
        if good:
            for c in p.cons:
                if not ref(c):
                    good = False
                    break
        if good:
            for b in p.bads:
                if ref(b):
                    return t
        nregs = {}
        for sid in p.states:
            if sid in p.nxt:
                nregs[sid] = ref(p.nxt[sid]) & mask(p.width[sid])
        regs = nregs
    return None


# -- the and-inverter graph ---------------------------------------------------
# Literals are signed node ids: +n the node, -n its negation; node 1 is
# the constant TRUE (a variable the solver pins), so TRUE = 1, FALSE = -1.

TRUE, FALSE = 1, -1


class Aig:
    def __init__(self):
        self.nodes = [None, None]    # 0 unused; 1 TRUE; else (a, b) | None
        self.table = {}

    def var(self):
        self.nodes.append(None)
        return len(self.nodes) - 1

    def AND(self, a, b):
        if a == FALSE or b == FALSE or a == -b:
            return FALSE
        if a == TRUE or a == b:
            return b
        if b == TRUE:
            return a
        key = (a, b) if a < b else (b, a)
        n = self.table.get(key)
        if n is None:
            self.nodes.append(key)
            n = len(self.nodes) - 1
            self.table[key] = n
        return n

    def OR(self, a, b):
        return -self.AND(-a, -b)

    def XOR(self, a, b):
        return self.OR(self.AND(a, -b), self.AND(-a, b))

    def MUX(self, c, t, e):
        if c == TRUE or t == e:
            return t
        if c == FALSE:
            return e
        return self.OR(self.AND(c, t), self.AND(-c, e))


def wconst(v, w):
    return [TRUE if (v >> i) & 1 else FALSE for i in range(w)]


def wnot(a):
    return [-x for x in a]


def wadd(g, a, b, c=FALSE):
    out = []
    for x, y in zip(a, b):
        t = g.XOR(x, y)
        out.append(g.XOR(t, c))
        c = g.OR(g.AND(x, y), g.AND(t, c))
    return out


def wsub(g, a, b):
    return wadd(g, a, wnot(b), TRUE)


def wneg(g, a):
    return wadd(g, wnot(a), [FALSE] * len(a), TRUE)


def weq(g, a, b):
    r = TRUE
    for x, y in zip(a, b):
        r = g.AND(r, -g.XOR(x, y))
    return r


def wult(g, a, b):
    lt = FALSE
    for x, y in zip(a, b):
        lt = g.MUX(g.XOR(x, y), y, lt)
    return lt


def wslt(g, a, b):
    return wult(g, a[:-1] + [-a[-1]], b[:-1] + [-b[-1]])


def wmux(g, c, t, e):
    return [g.MUX(c, x, y) for x, y in zip(t, e)]


def wmul(g, a, b):
    w = len(a)
    acc = [FALSE] * w
    for i in range(w):
        pp = [g.AND(b[i], a[j]) for j in range(w - i)]
        acc = acc[:i] + wadd(g, acc[i:], pp)
    return acc


def wdivmod(g, a, b):
    """Restoring division; by zero the quotient is all ones and the
    remainder the dividend, as the interpreter has it."""
    w = len(a)
    bx = b + [FALSE]
    r = [FALSE] * w
    q = [FALSE] * w
    for i in range(w - 1, -1, -1):
        rx = [a[i]] + r
        ge = -wult(g, rx, bx)
        d = wsub(g, rx, bx)
        r = wmux(g, ge, d, rx)[:w]
        q[i] = ge
    return q, r


def wshift(g, a, b, kind):
    w = len(a)
    fill = a[-1] if kind == 'sra' else FALSE
    cur = list(a)
    stages = 0
    while (1 << stages) < w:
        stages += 1
    for j in range(min(stages, len(b))):
        s = 1 << j
        if kind == 'sll':
            sh = [FALSE] * s + cur[:w - s]
        else:
            sh = cur[s:] + [fill] * s
        cur = wmux(g, b[j], sh, cur)
    big = FALSE
    for j in range(stages, len(b)):
        big = g.OR(big, b[j])
    return wmux(g, big, [fill] * w, cur)


def wred(g, a, kind):
    r = a[0]
    for x in a[1:]:
        if kind == 'redand':
            r = g.AND(r, x)
        elif kind == 'redor':
            r = g.OR(r, x)
        else:
            r = g.XOR(r, x)
    return r


class Blaster:
    """Words for a program's nodes over an environment that supplies the
    words of inputs and states; memoized per frame, iterative so deep
    cones need no recursion."""

    def __init__(self, p, g):
        self.p, self.g = p, g

    def deps(self, nid):
        op = self.p.op[nid]
        a = self.p.args[nid]
        if op in ('slice',) or op in EXT:
            return (abs(a[0]),)
        return tuple(abs(x) for x in a)

    def word(self, r, env, memo):
        w = self.compute(abs(r), env, memo)
        return wnot(w) if r < 0 else w

    def compute(self, nid, env, memo):
        if nid in memo:
            return memo[nid]
        stack = [nid]
        p = self.p
        while stack:
            n = stack[-1]
            if n in memo:
                stack.pop()
                continue
            op = p.op[n]
            if op in ('input', 'state'):
                memo[n] = env[n]
                stack.pop()
                continue
            pending = [d for d in self.deps(n) if d not in memo]
            if pending:
                stack.extend(pending)
                continue
            memo[n] = self.build(n, memo)
            stack.pop()
        return memo[nid]

    def build(self, n, memo):
        p, g = self.p, self.g
        op = p.op[n]
        w = p.width[n]
        a = p.args[n]

        def ref(r):
            x = memo[abs(r)]
            return wnot(x) if r < 0 else x

        if op in CONSTS:
            return wconst(p.const[n], w)
        if op == 'ite':
            return wmux(g, ref(a[0])[0], ref(a[1]), ref(a[2]))
        if op == 'slice':
            return ref(a[0])[a[2]:a[1] + 1]
        if op == 'uext':
            return ref(a[0]) + [FALSE] * a[1]
        if op == 'sext':
            x = ref(a[0])
            return x + [x[-1]] * a[1]
        if op == 'concat':
            return ref(a[1]) + ref(a[0])
        if op == 'not':
            return wnot(ref(a[0]))
        if op == 'neg':
            return wneg(g, ref(a[0]))
        if op == 'inc':
            return wadd(g, ref(a[0]), [FALSE] * w, TRUE)
        if op == 'dec':
            return wadd(g, ref(a[0]), [TRUE] * w, FALSE)
        if op in ('redand', 'redor', 'redxor'):
            return [wred(g, ref(a[0]), op)]
        x, y = ref(a[0]), ref(a[1])
        if op == 'and':
            return [g.AND(u, v) for u, v in zip(x, y)]
        if op == 'or':
            return [g.OR(u, v) for u, v in zip(x, y)]
        if op == 'xor':
            return [g.XOR(u, v) for u, v in zip(x, y)]
        if op == 'nand':
            return [-g.AND(u, v) for u, v in zip(x, y)]
        if op == 'nor':
            return [-g.OR(u, v) for u, v in zip(x, y)]
        if op == 'xnor':
            return [-g.XOR(u, v) for u, v in zip(x, y)]
        if op == 'implies':
            return [g.OR(-x[0], y[0])]
        if op == 'iff':
            return [-g.XOR(x[0], y[0])]
        if op == 'eq':
            return [weq(g, x, y)]
        if op == 'neq':
            return [-weq(g, x, y)]
        if op == 'ult':
            return [wult(g, x, y)]
        if op == 'ulte':
            return [-wult(g, y, x)]
        if op == 'ugt':
            return [wult(g, y, x)]
        if op == 'ugte':
            return [-wult(g, x, y)]
        if op == 'slt':
            return [wslt(g, x, y)]
        if op == 'slte':
            return [-wslt(g, y, x)]
        if op == 'sgt':
            return [wslt(g, y, x)]
        if op == 'sgte':
            return [-wslt(g, x, y)]
        if op == 'add':
            return wadd(g, x, y)
        if op == 'sub':
            return wsub(g, x, y)
        if op == 'mul':
            return wmul(g, x, y)
        if op == 'udiv':
            return wdivmod(g, x, y)[0]
        if op == 'urem':
            return wdivmod(g, x, y)[1]
        if op in ('sdiv', 'srem', 'smod'):
            nx, ny = x[-1], y[-1]
            mx = wmux(g, nx, wneg(g, x), x)
            my = wmux(g, ny, wneg(g, y), y)
            q, r = wdivmod(g, mx, my)
            if op == 'sdiv':
                return wmux(g, g.XOR(nx, ny), wneg(g, q), q)
            if op == 'srem':
                return wmux(g, nx, wneg(g, r), r)
            zero = [FALSE] * w
            rz = weq(g, r, zero)
            pos = r
            neg_pos = wsub(g, y, r)          # x < 0 <= y: y - u
            pos_neg = wadd(g, r, y)          # x >= 0 > y: u + y
            both = wneg(g, r)
            out = wmux(g, nx, wmux(g, ny, both, neg_pos),
                       wmux(g, ny, pos_neg, pos))
            return wmux(g, rz, zero, out)
        if op in ('sll', 'srl', 'sra'):
            return wshift(g, x, y, op)
        raise Decline('unsupported op: ' + op)


# -- the CDCL solver ----------------------------------------------------------
# Internal literals are 2*v (v true) and 2*v+1 (v false); a clause is a
# list whose element 0 is a header — the glue of a learnt clause, -1 for
# an original — and whose elements 1 and 2 are watched.

SAT, UNSAT, UNKNOWN = 1, 0, -1


def _luby(i):
    k = 1
    while (1 << k) - 1 < i:
        k += 1
    while True:
        if (1 << k) - 1 == i:
            return 1 << (k - 1)
        k -= 1
        i -= (1 << k)
        while (1 << k) - 1 < i:
            k += 1
        if k == 0:
            return 1


class Cdcl:
    def __init__(self):
        self.nv = 0
        self.val = [0, 0]
        self.level = [0]
        self.reason = [None]
        self.act = [0.0]
        self.phase = [1]
        self.seen = [0]
        self.hpos = [-1]
        self.heap = []
        self.watches = [[], []]
        self.trail = []
        self.lim = []
        self.qhead = 0
        self.clauses = []
        self.learnts = []
        self.ok = True
        self.props = 0
        self.conflicts = 0
        self.var_inc = 1.0
        self.max_learnts = 4000
        self.core = []

    # -- variables and the activity heap --
    def ensure(self, n):
        while self.nv < n:
            self.nv += 1
            self.val.extend((0, 0))
            self.level.append(0)
            self.reason.append(None)
            self.act.append(0.0)
            self.phase.append(1)
            self.seen.append(0)
            self.hpos.append(-1)
            self.watches.extend(([], []))
            self._hinsert(self.nv)

    def _hless(self, a, b):
        aa, ab = self.act[a], self.act[b]
        return aa > ab or (aa == ab and a < b)

    def _hup(self, i):
        heap, hpos = self.heap, self.hpos
        v = heap[i]
        while i > 0:
            pi = (i - 1) >> 1
            pv = heap[pi]
            if not self._hless(v, pv):
                break
            heap[i] = pv
            hpos[pv] = i
            i = pi
        heap[i] = v
        hpos[v] = i

    def _hdown(self, i):
        heap, hpos = self.heap, self.hpos
        n = len(heap)
        v = heap[i]
        while True:
            l = 2 * i + 1
            if l >= n:
                break
            r = l + 1
            c = r if r < n and self._hless(heap[r], heap[l]) else l
            cv = heap[c]
            if not self._hless(cv, v):
                break
            heap[i] = cv
            hpos[cv] = i
            i = c
        heap[i] = v
        hpos[v] = i

    def _hinsert(self, v):
        if self.hpos[v] >= 0:
            return
        self.heap.append(v)
        self.hpos[v] = len(self.heap) - 1
        self._hup(len(self.heap) - 1)

    def _hpop(self):
        heap, hpos = self.heap, self.hpos
        v = heap[0]
        last = heap.pop()
        hpos[v] = -1
        if heap:
            heap[0] = last
            hpos[last] = 0
            self._hdown(0)
        return v

    def _bump(self, v):
        self.act[v] += self.var_inc
        if self.act[v] > 1e100:
            for i in range(1, self.nv + 1):
                self.act[i] *= 1e-100
            self.var_inc *= 1e-100
        if self.hpos[v] >= 0:
            self._hup(self.hpos[v])

    # -- clauses --
    def add_clause(self, lits):
        """An original clause, added at decision level 0."""
        if not self.ok:
            return False
        if self.lim:
            self.backtrack(0)
        out = []
        seen = set()
        for l in sorted(lits):
            if self.val[l] > 0 or (l ^ 1) in seen:
                return True
            if self.val[l] == 0 and l not in seen:
                seen.add(l)
                out.append(l)
        if not out:
            self.ok = False
            return False
        if len(out) == 1:
            self._enqueue(out[0], None)
            if self._propagate() is not None:
                self.ok = False
                return False
            return True
        c = [-1] + out
        self.clauses.append(c)
        self.watches[out[0]].append(c)
        self.watches[out[1]].append(c)
        return True

    def _enqueue(self, l, r):
        self.val[l] = 1
        self.val[l ^ 1] = -1
        v = l >> 1
        self.level[v] = len(self.lim)
        self.reason[v] = r
        self.trail.append(l)

    def _propagate(self):
        val, watches, trail = self.val, self.watches, self.trail
        while self.qhead < len(trail):
            p = trail[self.qhead]
            self.qhead += 1
            self.props += 1
            fl = p ^ 1
            ws = watches[fl]
            i = j = 0
            n = len(ws)
            while i < n:
                c = ws[i]
                i += 1
                if c[1] == fl:
                    c[1] = c[2]
                    c[2] = fl
                first = c[1]
                if val[first] > 0:
                    ws[j] = c
                    j += 1
                    continue
                found = False
                for k in range(3, len(c)):
                    lk = c[k]
                    if val[lk] >= 0:
                        c[2] = lk
                        c[k] = fl
                        watches[lk].append(c)
                        found = True
                        break
                if found:
                    continue
                ws[j] = c
                j += 1
                if val[first] < 0:
                    while i < n:
                        ws[j] = ws[i]
                        i += 1
                        j += 1
                    del ws[j:]
                    self.qhead = len(trail)
                    return c
                self._enqueue(first, c)
            del ws[j:]
        return None

    def _analyze(self, confl):
        seen, level, reason, trail = self.seen, self.level, self.reason, \
            self.trail
        cur = len(self.lim)
        out = []
        path = 0
        p = None
        idx = len(trail) - 1
        c = confl
        while True:
            for q in (c[1:] if p is None else c[2:]):
                v = q >> 1
                if not seen[v] and level[v] > 0:
                    seen[v] = 1
                    self._bump(v)
                    if level[v] >= cur:
                        path += 1
                    else:
                        out.append(q)
            while not seen[trail[idx] >> 1]:
                idx -= 1
            p = trail[idx]
            idx -= 1
            seen[p >> 1] = 0
            path -= 1
            c = reason[p >> 1]
            if path == 0:
                break
        # minimize: drop literals implied by the rest
        kept = []
        for q in out:
            r = reason[q >> 1]
            if r is None:
                kept.append(q)
                continue
            for x in r[2:]:
                xv = x >> 1
                if not seen[xv] and level[xv] > 0:
                    kept.append(q)
                    break
        for q in out:
            seen[q >> 1] = 0
        learnt = [0, p ^ 1] + kept
        if len(kept) > 0:
            bi, bl = 2, level[kept[0] >> 1]
            for i in range(3, len(learnt)):
                lv = level[learnt[i] >> 1]
                if lv > bl:
                    bi, bl = i, lv
            learnt[2], learnt[bi] = learnt[bi], learnt[2]
            lv_set = set()
            for x in learnt[1:]:
                lv_set.add(level[x >> 1])
            learnt[0] = len(lv_set)
            return learnt, bl
        return learnt, 0

    def _analyze_final(self, p):
        """The assumptions responsible for the assumption literal p
        being false: a subset of the assumptions, p among them."""
        core = [p]
        if not self.lim:
            return core
        seen, level, reason, trail = self.seen, self.level, self.reason, \
            self.trail
        seen[p >> 1] = 1
        for i in range(len(trail) - 1, self.lim[0] - 1, -1):
            l = trail[i]
            v = l >> 1
            if seen[v]:
                r = reason[v]
                if r is None:
                    if l != (p ^ 1):
                        core.append(l)
                else:
                    for x in r[2:]:
                        if level[x >> 1] > 0:
                            seen[x >> 1] = 1
                seen[v] = 0
        seen[p >> 1] = 0
        return core

    def backtrack(self, lvl):
        if len(self.lim) <= lvl:
            return
        val, phase, trail = self.val, self.phase, self.trail
        start = self.lim[lvl]
        for i in range(len(trail) - 1, start - 1, -1):
            l = trail[i]
            val[l] = 0
            val[l ^ 1] = 0
            v = l >> 1
            phase[v] = l & 1
            self._hinsert(v)
        del trail[start:]
        self.qhead = start
        del self.lim[lvl:]

    def _reduce(self):
        """Learnt clauses beyond the limit: keep the glue, drop the half
        with the worst glue (oldest first among equals), and purge every
        clause satisfied at level 0 — the retired activation clauses
        among them. Watches are rebuilt from scratch."""
        val, reason = self.val, self.reason
        learnts = self.learnts
        order = sorted(range(len(learnts)),
                       key=lambda i: (-learnts[i][0], i))
        drop = set()
        half = len(order) // 2
        for i in order:
            if len(drop) >= half:
                break
            c = learnts[i]
            if c[0] <= 2 or len(c) <= 3 or reason[c[1] >> 1] is c:
                continue
            drop.add(i)
        keep = []
        for i, c in enumerate(learnts):
            if i in drop:
                continue
            if any(val[x] > 0 for x in c[1:]) and reason[c[1] >> 1] is not c:
                continue
            keep.append(c)
        self.learnts = keep
        orig = []
        for c in self.clauses:
            if any(val[x] > 0 for x in c[1:]) and reason[c[1] >> 1] is not c:
                continue
            orig.append(c)
        self.clauses = orig
        for i in range(len(self.watches)):
            self.watches[i] = []
        for c in self.clauses:
            self.watches[c[1]].append(c)
            self.watches[c[2]].append(c)
        for c in self.learnts:
            self.watches[c[1]].append(c)
            self.watches[c[2]].append(c)
        self.max_learnts = min(int(self.max_learnts * 1.1) + 500, 400000)

    def solve(self, assumps, max_props):
        """SAT (assignment left in place), UNSAT (self.core the failed
        assumptions), or UNKNOWN when max_props propagations are spent."""
        self.core = []
        self.backtrack(0)
        if not self.ok:
            return UNSAT
        if self._propagate() is not None:
            self.ok = False
            return UNSAT
        val = self.val
        start = self.props
        since = 0
        ri = 1
        restart_at = 64 * _luby(ri)
        while True:
            confl = self._propagate()
            if confl is not None:
                self.conflicts += 1
                since += 1
                if not self.lim:
                    self.ok = False
                    return UNSAT
                learnt, bl = self._analyze(confl)
                self.backtrack(bl)
                if len(learnt) == 2:
                    self._enqueue(learnt[1], None)
                else:
                    self.learnts.append(learnt)
                    self.watches[learnt[1]].append(learnt)
                    self.watches[learnt[2]].append(learnt)
                    self._enqueue(learnt[1], learnt)
                self.var_inc *= 1.0 / 0.95
                continue
            if self.props - start > max_props:
                self.backtrack(0)
                return UNKNOWN
            if since >= restart_at:
                since = 0
                ri += 1
                restart_at = 64 * _luby(ri)
                self.backtrack(0)
                if len(self.learnts) > self.max_learnts:
                    self._reduce()
                continue
            dl = len(self.lim)
            if dl < len(assumps):
                p = assumps[dl]
                if val[p] > 0:
                    self.lim.append(len(self.trail))
                    continue
                if val[p] < 0:
                    self.core = self._analyze_final(p)
                    self.backtrack(0)
                    return UNSAT
                self.lim.append(len(self.trail))
                self._enqueue(p, None)
                continue
            v = None
            while self.heap:
                cand = self._hpop()
                if val[2 * cand] == 0:
                    v = cand
                    break
            if v is None:
                return SAT
            self.lim.append(len(self.trail))
            self._enqueue(2 * v + self.phase[v], None)


class OutOfBudget(Exception):
    pass


class Spurious(Exception):
    """A trace this search cannot make concrete; reported as a partial."""


def ilit(x):
    """AIG literal -> solver literal."""
    return 2 * x if x > 0 else 2 * (-x) + 1


class Cnf:
    """Tseitin encoding of an AIG into a solver, incrementally: nodes
    are encoded up to the graph's current size on demand."""

    def __init__(self, g):
        self.g = g
        self.sat = Cdcl()
        self.done = 1
        self.sat.ensure(1)
        self.sat.add_clause([2])          # node 1 is TRUE
        self.budget = 0

    def encode(self):
        g, sat = self.g, self.sat
        n = len(g.nodes)
        sat.ensure(n - 1)
        for i in range(self.done + 1, n):
            nd = g.nodes[i]
            if nd is None:
                continue
            a, b = ilit(nd[0]), ilit(nd[1])
            o = 2 * i
            sat.add_clause([o ^ 1, a])
            sat.add_clause([o ^ 1, b])
            sat.add_clause([o, a ^ 1, b ^ 1])
        self.done = n - 1

    def query(self, aig_lits, extra=()):
        """Solve under assumptions given as AIG literals (constants
        folded) plus solver literals; charges the shared budget."""
        assumps = []
        for x in aig_lits:
            if x == TRUE:
                continue
            if x == FALSE:
                self.sat.core = [None]
                return UNSAT
            assumps.append(ilit(x))
        assumps.extend(extra)
        self.encode()
        if self.budget <= 0:
            raise OutOfBudget()
        before = self.sat.props
        st = self.sat.solve(assumps, self.budget)
        self.budget -= self.sat.props - before
        if st == UNKNOWN:
            raise OutOfBudget()
        return st

    def value(self, x):
        """Truth of an AIG literal under the current assignment."""
        if x == TRUE:
            return True
        if x == FALSE:
            return False
        return self.sat.val[ilit(x)] > 0

    def bits(self, word):
        v = 0
        for i, x in enumerate(word):
            if self.value(x):
                v |= 1 << i
        return v


# -- the one-step transition system -------------------------------------------

class System:
    """One step of the machine over fresh current-state and input
    variables: next words, the bad and constraint literals, and the
    initial-state relation behind an activation literal."""

    def __init__(self, p, node_cap):
        self.p = p
        g = self.g = Aig()
        bl = self.bl = Blaster(p, g)
        env = {}
        self.cur = {}
        self.inp = {}
        for iid in p.inputs:
            env[iid] = self.inp[iid] = [g.var() for _ in range(p.width[iid])]
        for sid in p.states:
            env[sid] = self.cur[sid] = [g.var() for _ in range(p.width[sid])]
        memo = {}
        self.nextw = {}
        for sid in p.states:
            if sid in p.nxt:
                self.nextw[sid] = bl.word(p.nxt[sid], env, memo)
        b = FALSE
        for r in p.bads:
            b = g.OR(b, bl.word(r, env, memo)[0])
        self.bad = b
        c = TRUE
        for r in p.cons:
            c = g.AND(c, bl.word(r, env, memo)[0])
        self.con = c
        self.initw = {}
        for sid in p.states:
            if sid in p.init:
                self.initw[sid] = bl.word(p.init[sid], env, memo)
        if len(g.nodes) > node_cap:
            raise Decline('transition cone of %d nodes exceeds the cap %d'
                          % (len(g.nodes), node_cap))
        # the states a clause may speak of: those carrying a next
        self.svars = []             # solver-side state bit variables
        self.var_bit = {}           # var -> (sid, bit)
        for sid in p.states:
            if sid in p.nxt:
                for i, v in enumerate(self.cur[sid]):
                    self.svars.append(v)
                    self.var_bit[v] = (sid, i)
        self.free = []              # inputs and next-less states: free every frame
        for iid in p.inputs:
            self.free.extend(self.inp[iid])
        for sid in p.states:
            if sid not in p.nxt:
                self.free.extend(self.cur[sid])
        self.const_init = all(all(x in (TRUE, FALSE) for x in w)
                              for w in self.initw.values())

    def next_lit(self, lit):
        sid, i = self.var_bit[abs(lit)]
        x = self.nextw[sid][i]
        return -x if lit < 0 else x

    def stimulus(self, cnf, frame0):
        """The free values of the current assignment as a stimulus
        frame: inputs, next-less states, and at frame 0 every state."""
        p = self.p
        out = {}
        for iid in p.inputs:
            v = cnf.bits(self.inp[iid])
            if v:
                out[str(iid)] = v
        for sid in p.states:
            if frame0 or sid not in p.nxt:
                v = cnf.bits(self.cur[sid])
                if v:
                    out[str(sid)] = v
        return out


# -- property-directed reachability -------------------------------------------

class Obligation:
    __slots__ = ('cube', 'frame', 'stim', 'succ', 'state0')

    def __init__(self, cube, frame, stim, succ, state0=None):
        self.cube = cube
        self.frame = frame
        self.stim = stim
        self.succ = succ
        self.state0 = state0


class Pdr:
    MAX_CTGS = 3
    MAX_JOINS = 5
    MAX_DEPTH = 1
    MIC_FAILS = 3

    def __init__(self, sysm, cnf, max_frames, bound):
        self.s = sysm
        self.cnf = cnf
        self.g = sysm.g
        self.max_frames = max_frames
        self.bound = bound
        self.frames = [[]]           # frames[i]: cubes blocked at level i
        self.acts = [self.g.var()]   # acts[0] activates the init relation
        self.seq = 0
        self.lit_act = {}
        self.pending = []            # activation literals to retire
        cnf.encode()
        self._init_relation()
        self.cleared = -1

    # -- encoding helpers --
    def _init_relation(self):
        s, sat = self.s, self.cnf.sat
        self.cnf.encode()
        a0 = ilit(self.acts[0])
        for sid, w in s.initw.items():
            for v, x in zip(s.cur[sid], w):
                if x == TRUE:
                    sat.add_clause([a0 ^ 1, 2 * v])
                elif x == FALSE:
                    sat.add_clause([a0 ^ 1, 2 * v + 1])
                else:
                    sat.add_clause([a0 ^ 1, 2 * v + 1, ilit(x)])
                    sat.add_clause([a0 ^ 1, 2 * v, ilit(x) ^ 1])

    def _new_frame(self):
        self.frames.append([])
        v = self.g.var()
        self.acts.append(v)
        self.cnf.encode()

    def _frame_lits(self, i):
        """F_i = every clause held at level >= i, and Init when i = 0."""
        return [self.acts[j] for j in range(i, len(self.acts))]

    def _temp(self, lits):
        """A clause switched on by a fresh activation literal, retired by
        a unit clause at the next query — after the model of this one
        has been read."""
        b = self.g.var()
        self.cnf.encode()
        self.cnf.sat.add_clause([ilit(b) ^ 1] + [ilit(x) for x in lits])
        self.pending.append(b)
        return b

    def _query(self, lits, extra=()):
        live = []
        for b in self.pending:
            if b in lits:
                live.append(b)
            else:
                self.cnf.sat.add_clause([ilit(b) ^ 1])
        self.pending = live
        return self.cnf.query(lits, extra)

    # -- queries --
    def _rel_query(self, i, cube, block=True):
        """SAT(F_{i-1} & C & !cube & T & cube')? On UNSAT self.core_idx
        holds the positions of cube whose primed literals were needed."""
        s = self.s
        pos_of = {}
        primed = []
        for k, l in enumerate(cube):
            x = s.next_lit(l)
            if x == FALSE:
                self.core_idx = [k]
                return UNSAT
            if x == TRUE:
                continue
            pos_of.setdefault(ilit(x), []).append(k)
            primed.append(x)
        lits = self._frame_lits(i - 1) + [s.con]
        b = None
        if block and len(cube) > 0:
            b = self._temp([-l for l in cube])
            lits.append(b)
        lits.extend(primed)
        st = self._query(lits)
        if st == UNSAT:
            idx = []
            for c in self.cnf.sat.core:
                if c in pos_of:
                    idx.extend(pos_of[c])
            self.core_idx = sorted(set(idx))
        return st

    def _init_query(self, cube):
        """Does the cube meet a constrained initial state?"""
        s = self.s
        if s.const_init:
            for l in cube:
                sid, i = s.var_bit[abs(l)]
                w = s.initw.get(sid)
                if w is None:
                    continue
                if (w[i] == TRUE) != (l > 0):
                    return False
            return True
        st = self._query([self.acts[0], s.con] + list(cube))
        return st == SAT

    def _initial_state(self, ob):
        """The obligation's cube meets Init: a concrete initial state in
        it under the obligation's own free values, as a frame-0
        stimulus — or None when Init itself depends on those values
        in a way the cube's input cannot satisfy."""
        s = self.s
        extra = []
        for iid in s.p.inputs:
            v = int(ob.stim.get(str(iid), 0))
            for i, x in enumerate(s.inp[iid]):
                extra.append(2 * x if (v >> i) & 1 else 2 * x + 1)
        for sid in s.p.states:
            if sid not in s.p.nxt:
                v = int(ob.stim.get(str(sid), 0))
                for i, x in enumerate(s.cur[sid]):
                    extra.append(2 * x if (v >> i) & 1 else 2 * x + 1)
        st = self._query([self.acts[0]] + list(ob.cube), extra)
        if st != SAT:
            return None
        return s.stimulus(self.cnf, True)

    def _lift(self, targets):
        """The current assignment's state, lifted: the subset of state
        literals that, with the free values fixed, forces every target
        (the constraint among them). A pure propagation query."""
        s, cnf = self.s, self.cnf
        assumps = []
        for v in s.free:
            assumps.append(2 * v if cnf.value(v) else 2 * v + 1)
        state = []
        for v in s.svars:
            state.append(v if cnf.value(v) else -v)
        tl = [t for t in targets if t != TRUE]
        if not tl:
            return tuple(sorted(state, key=abs))
        b = self._temp([-t for t in tl])
        st = self._query(state + [b], assumps)
        if st != UNSAT:
            return tuple(sorted(state, key=abs))
        core = set(cnf.sat.core)
        lifted = [l for l in state if ilit(l) in core]
        if not lifted:
            return tuple(sorted(state, key=abs))
        return tuple(sorted(lifted, key=abs))

    # -- clauses --
    def _add_cube(self, cube, level):
        """Block cube at level: subsume what it covers below, add the
        clause behind the level's activation literal."""
        cs = set(cube)
        for j in range(1, level + 1):
            self.frames[j] = [c for c in self.frames[j]
                              if not cs.issubset(c)]
        self.frames[level].append(cube)
        a = ilit(self.acts[level])
        self.cnf.sat.add_clause([a ^ 1] + [ilit(-l) for l in cube])
        for l in cube:
            self.lit_act[l] = self.lit_act.get(l, 0) + 1

    def _blocked(self, cube, level):
        cs = set(cube)
        for j in range(level, len(self.frames)):
            for c in self.frames[j]:
                if cs.issuperset(c):
                    return True
        return False

    def _push_up(self, cube, level):
        """The highest level < frontier+1 at which cube is still
        relatively inductive (it is at `level`)."""
        k = len(self.frames) - 1
        while level < k and self._rel_query(level + 1, cube) == UNSAT:
            level += 1
        return level

    # -- generalization --
    def _mic(self, cube, level, depth):
        lits = sorted(cube, key=lambda l: (self.lit_act.get(l, 0), abs(l)))
        i = 0
        fails = 0
        while i < len(lits) and len(lits) > 1:
            cand = lits[:i] + lits[i + 1:]
            if self._ctg_down(cand, level, depth):
                lits = cand
                fails = 0
            else:
                i += 1
                fails += 1
                if fails > self.MIC_FAILS:
                    break
        return tuple(sorted(lits, key=abs))

    def _ctg_down(self, lits, level, depth):
        cube = tuple(sorted(lits, key=abs))
        ctgs = 0
        joins = 0
        while True:
            if self._init_query(cube):
                return False
            st = self._rel_query(level, cube)
            if st == UNSAT:
                self.last_core = self.core_idx
                return True
            # a counterexample to generalization: the predecessor state
            g = self._lift([self.s.con] + [self.s.next_lit(l)
                                            for l in cube])
            if (depth < self.MAX_DEPTH and ctgs < self.MAX_CTGS
                    and level > 1 and not self._init_query(g)
                    and self._rel_query(level - 1, g) == UNSAT):
                ctgs += 1
                j = self._push_up(g, level - 1)
                gg = self._mic(g, j, depth + 1)
                self._add_cube(gg, j)
                continue
            ctgs = 0
            joins += 1
            if joins > self.MAX_JOINS:
                return False
            gs = set(g)
            joined = tuple(l for l in cube if l in gs)
            if len(joined) == len(cube) or not joined:
                return False
            cube = joined

    def _generalize(self, ob):
        """The cube just found relatively inductive at ob.frame: cut it
        to its core when the core still avoids Init, then MIC."""
        cube = ob.cube
        idx = self.core_idx
        if idx and len(idx) < len(cube):
            core = tuple(cube[k] for k in idx)
            if not self._init_query(core):
                cube = core
        return self._mic(cube, ob.frame, 1)

    # -- the obligation loop --
    def _block(self, root):
        heap = []
        self.seq += 1
        heapq.heappush(heap, (root.frame, self.seq, root))
        while heap:
            frame, _, ob = heapq.heappop(heap)
            if frame == 0:
                return ob
            if self._blocked(ob.cube, frame):
                continue
            if self._init_query(ob.cube):
                # an initial state inside the cube: the trace from here
                # is a counterexample shorter than the frontier
                stim0 = self._initial_state(ob)
                if stim0 is None:
                    raise Spurious('an initial state met the obligation '
                                   'under other inputs than its own')
                return Obligation(ob.cube, 0, stim0, ob.succ)
            st = self._rel_query(frame, ob.cube)
            if st == SAT:
                stim = self.s.stimulus(self.cnf, frame - 1 == 0)
                pred = self._lift([self.s.con] + [self.s.next_lit(l)
                                                   for l in ob.cube])
                nob = Obligation(pred, frame - 1, stim, ob)
                self.seq += 1
                heapq.heappush(heap, (frame - 1, self.seq, nob))
                self.seq += 1
                heapq.heappush(heap, (frame, self.seq, ob))
                continue
            cube = self._generalize(ob)
            j = self._push_up(cube, frame)
            self._add_cube(cube, j)
            if self.bound == 'inf' and j < len(self.frames) - 1:
                # re-queue the obligation ahead so the cube is chased to
                # the frontier now; the trace it may end in is then no
                # longer frame-aligned, which only an unbounded ask can
                # take (a bounded one needs every witness within bound)
                self.seq += 1
                heapq.heappush(heap, (j + 1, self.seq,
                                      Obligation(ob.cube, j + 1, ob.stim,
                                                 ob.succ)))
        return None

    def _propagate(self):
        """Push clauses forward; an emptied level is convergence and
        returns the invariant above it."""
        k = len(self.frames) - 1
        for i in range(1, k):
            for cube in list(self.frames[i]):
                if cube not in self.frames[i]:
                    continue
                if self._rel_query(i + 1, cube, block=False) == UNSAT:
                    self.frames[i].remove(cube)
                    self._add_cube(cube, i + 1)
            if not self.frames[i]:
                inv = []
                for j in range(i + 1, k + 1):
                    inv.extend(self.frames[j])
                return inv
        return None

    def trace(self, ob):
        steps = []
        cur = ob
        while cur is not None:
            steps.append(cur.stim)
            cur = cur.succ
        return steps

    def run(self):
        """('proved', clauses) | ('cex', steps) | ('bound', k)."""
        s = self.s
        try:
            st = self._query(self._frame_lits(0) + [s.con, s.bad])
            if st == SAT:
                return ('cex', [s.stimulus(self.cnf, True)])
            self.cleared = 0
            if self.bound != 'inf' and self.bound <= 0:
                return ('bound', 0)
            self._new_frame()
            while True:
                k = len(self.frames) - 1
                st = self._query(self._frame_lits(k) + [s.con, s.bad])
                if st == SAT:
                    stim = s.stimulus(self.cnf, k == 0)
                    cube = self._lift([s.con, s.bad])
                    ob = self._block(Obligation(cube, k, stim, None))
                    if ob is not None:
                        return ('cex', self.trace(ob))
                    continue
                self.cleared = k
                if self.bound != 'inf' and k >= self.bound:
                    return ('bound', k)
                if k >= self.max_frames:
                    return ('bound', k)
                self._new_frame()
                inv = self._propagate()
                if inv is not None:
                    return ('proved', inv)
        except OutOfBudget:
            return ('bound', self.cleared)
        except Spurious as exc:
            return ('spurious', str(exc))


# -- bounded unrolling ---------------------------------------------------------

def bmc(p, budget, bound, start, depth_cap, node_cap):
    """Frames unrolled into one growing graph; queries from `start`.
    ('witness', steps, depth) | ('all', k) | ('bound', k) where k is
    the last depth proven free of bad."""
    g = Aig()
    bl = Blaster(p, g)
    cnf = Cnf(g)
    cnf.budget = budget
    last = bound if bound != 'inf' else depth_cap
    proven = start - 1
    frames = []                  # per frame: (env, memo)
    cons = []
    prev_next = None
    try:
        for t in range(last + 1):
            env = {}
            for iid in p.inputs:
                env[iid] = [g.var() for _ in range(p.width[iid])]
            free_states = []
            for sid in p.states:
                if t == 0:
                    if sid in p.init:
                        env[sid] = None
                    else:
                        env[sid] = [g.var() for _ in range(p.width[sid])]
                        free_states.append(sid)
                elif sid in p.nxt:
                    env[sid] = prev_next[sid]
                else:
                    env[sid] = [g.var() for _ in range(p.width[sid])]
                    free_states.append(sid)
            memo = {}
            if t == 0:
                # initialized states are their init words over frame 0;
                # a state named inside another's init reads its own
                pending = [sid for sid in p.states if sid in p.init]
                for sid in pending:
                    env[sid] = [g.var() for _ in range(p.width[sid])]
                eqs = []
                for sid in pending:
                    w = bl.word(p.init[sid], env, memo)
                    eqs.append((sid, w))
                cnf.encode()
                for sid, w in eqs:
                    for v, x in zip(env[sid], w):
                        cnf.sat.add_clause([2 * v + 1, ilit(x)])
                        cnf.sat.add_clause([2 * v, ilit(x) ^ 1])
            c = TRUE
            for r in p.cons:
                c = g.AND(c, bl.word(r, env, memo)[0])
            cons.append(c)
            b = FALSE
            for r in p.bads:
                b = g.OR(b, bl.word(r, env, memo)[0])
            nxt = {}
            for sid in p.states:
                if sid in p.nxt:
                    nxt[sid] = bl.word(p.nxt[sid], env, memo)
            frames.append((env, free_states))
            prev_next = nxt
            if len(g.nodes) > node_cap:
                return ('bound', proven)
            if FALSE in cons:
                # the constraint is impossible from here: no valid trace
                return ('all', 'inf') if proven >= t - 1 else \
                    ('bound', proven)
            if t < start:
                continue
            st = cnf.query(cons + [b])
            if st == SAT:
                steps = []
                for ft, (fenv, fs) in enumerate(frames):
                    fr = {}
                    for iid in p.inputs:
                        v = cnf.bits(fenv[iid])
                        if v:
                            fr[str(iid)] = v
                    for sid in fs:
                        v = cnf.bits(fenv[sid])
                        if v:
                            fr[str(sid)] = v
                    steps.append(fr)
                if evaluate(p, steps) == t:
                    return ('witness', steps, t)
                return ('bound', proven)
            proven = t
    except OutOfBudget:
        return ('bound', proven)
    if bound == 'inf':
        return ('bound', proven)
    return ('all', proven)


# -- the search ---------------------------------------------------------------

PROPS_PER_S = 250000
NODE_CAP = 200000


def emit(value):
    print(json.dumps(value, sort_keys=True))


def partial(note, **more):
    prog = {"note": note}
    prog.update(more)
    return {"kind": "partial", "progress": prog}


def main(argv):
    prog, mode, observable, bound, wall = argv[:5]
    wall_s = float(wall)
    if observable != 'bad':
        emit(partial("btor2-pdr only decides 'bad'"))
        return
    try:
        p = parse(prog)
    except (Decline, ValueError, KeyError, IndexError) as exc:
        emit(partial(str(exc) or exc.__class__.__name__))
        return
    if bound != 'inf':
        bound = int(bound)
    try:
        sysm = System(p, NODE_CAP)
    except Decline as exc:
        emit(partial(str(exc)))
        return
    total = max(200000, int(PROPS_PER_S * wall_s))
    cnf = Cnf(sysm.g)
    cnf.budget = total if mode != 'exists' else (total * 3) // 5
    max_frames = 500 if bound == 'inf' else bound
    pdr = Pdr(sysm, cnf, max_frames, bound)
    r = pdr.run()
    stats = {"frames": len(pdr.frames), "clauses":
             sum(len(f) for f in pdr.frames),
             "conflicts": cnf.sat.conflicts, "props": cnf.sat.props}
    if r[0] == 'proved':
        clauses = [[list(sysm.var_bit[abs(l)]) + [1 if l > 0 else 0]
                    for l in cube] for cube in r[1]]
        # a cube's negation: the literal (sid, bit, v) holds v = the
        # value the state bit must take for the clause to be satisfied
        clauses = [[[sid, i, 0 if v == 1 else 1] for sid, i, v in cl]
                   for cl in clauses]
        if len(clauses) <= 5000:
            cert = {"schema": "clauses",
                    "payload": {"kind": "clause-invariant",
                                "clauses": clauses}}
            emit({"kind": "all", "bound": "inf", "cert": cert})
        else:
            emit({"kind": "all", "bound": "inf"})
        return
    if r[0] == 'spurious':
        emit(partial(r[1], bound_reached=max(pdr.cleared, 0), **stats))
        return
    if r[0] == 'cex':
        steps = r[1]
        depth = len(steps) - 1
        steps = steps[:-1]
        emit({"kind": "witness", "payload": {"steps": steps},
              "depth": depth})
        return
        emit(partial("internal: obligation trace did not replay at "
                     "depth %d" % depth, bound_reached=max(pdr.cleared, 0),
                     **stats))
        return
    k = r[1]
    if mode == 'exists' and (bound == 'inf' or k < bound):
        cnf.budget = 0
        res = bmc(p, total - (total * 3) // 5, bound, k + 1, 200, NODE_CAP)
        if res[0] == 'witness':
            emit({"kind": "witness", "payload": {"steps": res[1]},
                  "depth": res[2]})
            return
        if res[0] == 'all':
            if res[1] == 'inf':
                emit({"kind": "all", "bound": "inf"})
                return
            k = max(k, res[1])
        else:
            k = max(k, res[1])
    if k >= 0:
        emit({"kind": "all", "bound": k})
    else:
        emit(partial("budget spent before frame 0 was cleared",
                     bound_reached=0, **stats))


if __name__ == '__main__':
    main(sys.argv[1:])
