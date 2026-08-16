"""btor2-bmcf, revision 2: the btor2-bmc algorithm plus the
signed division family (sdiv, srem, smod) in both the evaluator
and the blaster (magnitude circuits with sign correction, whose
division-by-zero cases fold to the SMT-LIB values), added by
pure insertion: the revision-1 fragment runs the same code path.

Usage: solve.py <program.btor2> <mode> <observable> <bound> <wall_s>

Word-level bit-blasting onto an AND/inverter graph with structural
hashing and constant folding; per-depth query cones are Tseitin-encoded
into a built-in CDCL SAT solver (two-watched literals, 1UIP learning,
VSIDS, restarts, phase saving). A sat depth yields a stimulus witness,
re-simulated internally before it is emitted; unsat depths accumulate
into all(k) up to the asked bound. The conflict budget derives from the
wall argument, never from the clock, so two runs emit identical bytes.
"""

MASK = {}


def mask(w):
    m = MASK.get(w)
    if m is None:
        m = MASK[w] = (1 << w) - 1
    return m


class Model:
    def __init__(self):
        self.width = {}      # node id -> bit width
        self.node = {}       # node id -> (op, args) args = raw ints
        self.order = []      # node ids, ascending
        self.inputs = []     # input node ids
        self.states = []     # state node ids
        self.init = {}       # state id -> value node ref
        self.next = {}       # state id -> value node ref
        self.bads = []       # node refs
        self.constraints = []  # node refs


def parse(path):
    sorts = {}
    m = Model()
    with open(path) as fh:
        for raw in fh:
            line = raw.split(';', 1)[0].strip()
            if not line:
                continue
            t = line.split()
            nid, op = int(t[0]), t[1]
            if op == 'sort':
                if t[2] != 'bitvec':
                    raise ValueError('unsupported sort: ' + t[2])
                sorts[int(t[0])] = int(t[3])
                continue
            if op == 'init':
                m.init[int(t[3])] = int(t[4])
                continue
            if op == 'next':
                m.next[int(t[3])] = int(t[4])
                continue
            if op in ('bad', 'constraint'):
                (m.bads if op == 'bad' else m.constraints).append(int(t[2]))
                continue
            if op in ('output', 'fair', 'justice'):
                continue
            w = sorts[int(t[2])]
            m.width[nid] = w
            if op == 'input':
                m.inputs.append(nid)
                m.node[nid] = ('input', ())
            elif op == 'state':
                m.states.append(nid)
                m.node[nid] = ('state', ())
            elif op in ('const', 'constd', 'consth', 'zero', 'one', 'ones'):
                if op == 'zero':
                    v = 0
                elif op == 'one':
                    v = 1
                elif op == 'ones':
                    v = mask(w)
                elif op == 'const':
                    v = int(t[3], 2)
                elif op == 'constd':
                    v = int(t[3]) & mask(w)
                else:
                    v = int(t[3], 16)
                m.node[nid] = ('const', (v & mask(w),))
            else:
                args = []
                for a in t[3:]:          # a trailing symbol ends the args
                    try:
                        args.append(int(a))
                    except ValueError:
                        break
                m.node[nid] = (op, tuple(args))
            m.order.append(nid)
    return m


def _signed(v, w):
    return v - (1 << w) if v >> (w - 1) else v


def eval_frame(m, regs, frame_inputs, cache):
    """Evaluate every node for one frame. regs: state id -> value (may
    be lazily filled at frame 0 from init). Returns node id -> value."""
    vals = cache

    def ref(r):
        v = vals[abs(r)]
        return (~v & mask(m.width[abs(r)])) if r < 0 else v

    for nid in m.order:
        op, a = m.node[nid]
        w = m.width[nid]
        if op == 'const':
            vals[nid] = a[0]
        elif op == 'input':
            vals[nid] = int(frame_inputs.get(str(nid), 0)) & mask(w)
        elif op == 'state':
            if nid in regs:
                vals[nid] = regs[nid]
            else:
                # uninitialized (frame 0) or next-less: read the stimulus
                vals[nid] = int(frame_inputs.get(str(nid), 0)) & mask(w)
                regs[nid] = vals[nid]
        elif op == 'ite':
            vals[nid] = ref(a[1]) if ref(a[0]) else ref(a[2])
        elif op == 'slice':
            vals[nid] = (ref(a[0]) >> a[2]) & mask(w)
        elif op == 'uext':
            vals[nid] = ref(a[0])
        elif op == 'sext':
            sw = m.width[abs(a[0])]
            vals[nid] = _signed(ref(a[0]), sw) & mask(w)
        elif op == 'concat':
            vals[nid] = (ref(a[0]) << m.width[abs(a[1])]) | ref(a[1])
        elif op == 'not':
            vals[nid] = ~ref(a[0]) & mask(w)
        elif op == 'neg':
            vals[nid] = -ref(a[0]) & mask(w)
        elif op == 'inc':
            vals[nid] = (ref(a[0]) + 1) & mask(w)
        elif op == 'dec':
            vals[nid] = (ref(a[0]) - 1) & mask(w)
        elif op == 'redand':
            aw = m.width[abs(a[0])]
            vals[nid] = 1 if ref(a[0]) == mask(aw) else 0
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
            aw = m.width[abs(a[0])]
            x, y = _signed(ref(a[0]), aw), _signed(ref(a[1]), aw)
            vals[nid] = 1 if ((op == 'slt' and x < y)
                              or (op == 'slte' and x <= y)
                              or (op == 'sgt' and x > y)
                              or (op == 'sgte' and x >= y)) else 0
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
            sa = _signed(ref(a[0]), w)
            sb = _signed(ref(a[1]), w)
            if op == 'sdiv':
                if sb == 0:
                    vals[nid] = 1 if sa < 0 else mask(w)
                else:
                    q = abs(sa) // abs(sb)
                    vals[nid] = (q if (sa < 0) == (sb < 0) else -q) \
                        & mask(w)
            elif op == 'srem':                 # sign follows dividend
                if sb == 0:
                    vals[nid] = sa & mask(w)
                else:
                    r = abs(sa) % abs(sb)
                    vals[nid] = (-r if sa < 0 else r) & mask(w)
            else:                              # smod: sign follows divisor
                if sb == 0:
                    vals[nid] = sa & mask(w)
                else:
                    u = abs(sa) % abs(sb)
                    if u == 0:
                        vals[nid] = 0
                    elif sa >= 0 and sb >= 0:
                        vals[nid] = u
                    elif sa < 0 and sb >= 0:
                        vals[nid] = (-u + sb) & mask(w)
                    elif sa >= 0 and sb < 0:
                        vals[nid] = (u + sb) & mask(w)
                    else:
                        vals[nid] = (-u) & mask(w)
        elif op == 'sll':
            sh = ref(a[1])
            vals[nid] = (ref(a[0]) << sh) & mask(w) if sh < w else 0
        elif op == 'srl':
            sh = ref(a[1])
            vals[nid] = ref(a[0]) >> sh if sh < w else 0
        elif op == 'sra':
            sh = ref(a[1])
            sv = _signed(ref(a[0]), w)
            vals[nid] = (sv >> sh) & mask(w) if sh < w else \
                (mask(w) if sv < 0 else 0)
        else:
            raise ValueError('unsupported op: ' + op)
    return vals, ref


def run(m, steps):
    """Run the model under a stimulus; return (bad_fired_depth | None,
    frames run). Constraints must hold at every frame up to the bad."""
    regs = {}
    for sid in m.states:
        if sid in m.init:
            pass                         # evaluated lazily at frame 0
    constrained = True
    for t, frame in enumerate(steps):
        vals = {}
        # frame 0: pre-fill initialized states (init refs evaluate in a
        # first pass restricted to nodes the init value depends on —
        # ids ascend, so a plain full pass with states-read-from-regs
        # works when we seed initialized states first)
        if t == 0:
            pending = {sid: r for sid, r in m.init.items()}
            # init values are constants or combinational over inputs;
            # evaluate them with a mini pass that treats *other*
            # uninitialized states as stimulus
            tmp_vals, tmp_ref = eval_frame(m, dict(), frame, {})
            for sid, r in pending.items():
                regs[sid] = tmp_ref(r) & mask(m.width[sid])
        vals, ref = eval_frame(m, regs, frame, {})
        if constrained:
            for c in m.constraints:
                if not ref(c):
                    constrained = False
                    break
        if constrained:
            for b in m.bads:
                if ref(b):
                    return t, t + 1
        nxt = {}
        for sid in m.states:
            if sid in m.next:
                nxt[sid] = ref(m.next[sid]) & mask(m.width[sid])
        regs = nxt
    return None, len(steps)

# -- AIG ----------------------------------------------------------------------
# Literal encoding: node n -> literals 2n (positive) and 2n+1 (negated).
# Node 0 is the constant FALSE, so literal 0 = false, 1 = true.


class AIG:
    def __init__(self):
        self.nodes = [None]          # node 0: constant; None marks a leaf
        self.hash = {}

    def var(self):
        self.nodes.append(None)
        return 2 * (len(self.nodes) - 1)

    def AND(self, a, b):
        if a > b:
            a, b = b, a
        if a == 0:
            return 0
        if a == 1:
            return b
        if a == b:
            return a
        if a ^ b == 1:
            return 0
        key = (a, b)
        lit = self.hash.get(key)
        if lit is None:
            self.nodes.append(key)
            lit = self.hash[key] = 2 * (len(self.nodes) - 1)
        return lit

    def OR(self, a, b):
        return self.AND(a ^ 1, b ^ 1) ^ 1

    def XOR(self, a, b):
        return self.OR(self.AND(a, b ^ 1), self.AND(a ^ 1, b))

    def MUX(self, c, t, e):
        return self.OR(self.AND(c, t), self.AND(c ^ 1, e))


# -- words (LSB-first literal vectors) ----------------------------------------

def wconst(v, w):
    return [(v >> i) & 1 for i in range(w)]


def wnot(g, a):
    return [x ^ 1 for x in a]


def wadd(g, a, b, cin=0):
    out, c = [], cin
    for x, y in zip(a, b):
        s = g.XOR(g.XOR(x, y), c)
        c = g.OR(g.AND(x, y), g.AND(c, g.XOR(x, y)))
        out.append(s)
    return out, c


def wsub(g, a, b):
    out, _ = wadd(g, a, wnot(g, b), 1)
    return out


def wneg(g, a):
    out, _ = wadd(g, wnot(g, a), wconst(0, len(a)), 1)
    return out


def weq(g, a, b):
    ne = 0
    for x, y in zip(a, b):
        ne = g.OR(ne, g.XOR(x, y))
    return ne ^ 1


def wult(g, a, b):
    lt = 0
    for x, y in zip(a, b):                 # LSB to MSB
        same = g.XOR(x, y) ^ 1
        lt = g.OR(g.AND(x ^ 1, y), g.AND(same, lt))
    return lt


def wslt(g, a, b):
    fa = a[:-1] + [a[-1] ^ 1]
    fb = b[:-1] + [b[-1] ^ 1]
    return wult(g, fa, fb)


def wmux(g, c, t, e):
    return [g.MUX(c, x, y) for x, y in zip(t, e)]


def wmul(g, a, b):
    w = len(a)
    acc = wconst(0, w)
    for i, bi in enumerate(b):
        if bi == 0:
            continue
        part = [0] * i + a[:w - i]
        if bi != 1:
            part = [g.AND(bi, x) for x in part]
        acc, _ = wadd(g, acc, part)
    return acc


def wudiv(g, a, b):
    """Restoring division; by construction b=0 yields q=ones, r=a."""
    w = len(a)
    bx = b + [0]                                     # width w+1
    rem = wconst(0, w + 1)
    q = [0] * w
    for i in range(w - 1, -1, -1):
        rem = [a[i]] + rem[:w]
        ge = wult(g, rem, bx) ^ 1
        rem = wmux(g, ge, wsub(g, rem, bx), rem)
        q[i] = ge
    return q, rem[:w]


def wshift(g, a, b, kind):
    """Barrel shifter; amounts >= width give 0 (or sign for sra)."""
    w = len(a)
    fill = a[-1] if kind == 'sra' else 0
    out = list(a)
    for s in range(w.bit_length()):
        if s >= len(b):
            break
        sh = 1 << s
        if kind == 'sll':
            shifted = [0] * min(sh, w) + out[:max(w - sh, 0)]
        else:
            shifted = out[min(sh, w):] + [fill] * min(sh, w)
        out = wmux(g, b[s], shifted, out)
    big = 0                                          # amount >= w?
    for j in range(len(b)):
        if (1 << j) >= w:
            big = g.OR(big, b[j])
    return [g.MUX(big, fill, x) for x in out]


# -- blasting a model over frames ---------------------------------------------

class Blaster:
    """Demand-driven blasting: a word is built for (node, frame) when a
    cone needs it, via an explicit work stack (no recursion limits).
    States resolve to their init expression at frame 0 (fresh variables
    when uninitialized) and to the previous frame's next elsewhere."""

    def __init__(self, model):
        self.m = model
        self.g = AIG()
        self.words = {}              # (node id, frame) -> literal vector

    def _deps(self, key):
        nid, t = key
        op, a = self.m.node[nid]
        if op in ('const', 'input'):
            return []
        if op == 'state':
            if t == 0:
                r = self.m.init.get(nid)
            else:
                r = self.m.next.get(nid)
            return [] if r is None else [(abs(r), t if t == 0 else t - 1)]
        if op == 'slice':
            return [(abs(a[0]), t)]
        if op in ('uext', 'sext'):
            return [(abs(a[0]), t)]
        return [(abs(r), t) for r in a]

    def _lookup(self, r, t):
        w = self.words[(abs(r), t)]
        return wnot(self.g, w) if r < 0 else w

    def _compute(self, key):
        m, g = self.m, self.g
        nid, t = key
        op, a = m.node[nid]
        w = m.width[nid]

        def ref(r, at=None):
            return self._lookup(r, t if at is None else at)

        if op == 'const':
            return wconst(a[0], w)
        if op == 'input':
            return [g.var() for _ in range(w)]
        if op == 'state':
            r = m.init.get(nid) if t == 0 else m.next.get(nid)
            if r is None:
                return [g.var() for _ in range(w)]
            return ref(r, t if t == 0 else t - 1)
        if op == 'ite':
            return wmux(g, ref(a[0])[0], ref(a[1]), ref(a[2]))
        if op == 'slice':
            return ref(a[0])[a[2]:a[1] + 1]
        if op == 'uext':
            return ref(a[0]) + [0] * a[1]
        if op == 'sext':
            x = ref(a[0])
            return x + [x[-1]] * a[1]
        if op == 'concat':
            return ref(a[1]) + ref(a[0])
        if op == 'not':
            return wnot(g, ref(a[0]))
        if op == 'neg':
            return wneg(g, ref(a[0]))
        if op == 'inc':
            out, _ = wadd(g, ref(a[0]), wconst(1, w))
            return out
        if op == 'dec':
            return wsub(g, ref(a[0]), wconst(1, w))
        if op in ('redand', 'redor', 'redxor'):
            x = ref(a[0])
            acc = x[0]
            for bit in x[1:]:
                acc = (g.AND(acc, bit) if op == 'redand'
                       else g.OR(acc, bit) if op == 'redor'
                       else g.XOR(acc, bit))
            return [acc]
        if op in ('and', 'or', 'xor', 'nand', 'nor', 'xnor'):
            x, y = ref(a[0]), ref(a[1])
            f = {'and': g.AND, 'or': g.OR, 'xor': g.XOR,
                 'nand': lambda p, q: g.AND(p, q) ^ 1,
                 'nor': lambda p, q: g.OR(p, q) ^ 1,
                 'xnor': lambda p, q: g.XOR(p, q) ^ 1}[op]
            return [f(p, q) for p, q in zip(x, y)]
        if op == 'implies':
            return [g.OR(ref(a[0])[0] ^ 1, ref(a[1])[0])]
        if op == 'iff':
            return [g.XOR(ref(a[0])[0], ref(a[1])[0]) ^ 1]
        if op == 'eq':
            return [weq(g, ref(a[0]), ref(a[1]))]
        if op == 'neq':
            return [weq(g, ref(a[0]), ref(a[1])) ^ 1]
        if op in ('ult', 'ulte', 'ugt', 'ugte'):
            x, y = ref(a[0]), ref(a[1])
            lit = (wult(g, x, y) if op == 'ult'
                   else wult(g, y, x) ^ 1 if op == 'ulte'
                   else wult(g, y, x) if op == 'ugt'
                   else wult(g, x, y) ^ 1)
            return [lit]
        if op in ('slt', 'slte', 'sgt', 'sgte'):
            x, y = ref(a[0]), ref(a[1])
            lit = (wslt(g, x, y) if op == 'slt'
                   else wslt(g, y, x) ^ 1 if op == 'slte'
                   else wslt(g, y, x) if op == 'sgt'
                   else wslt(g, x, y) ^ 1)
            return [lit]
        if op == 'add':
            out, _ = wadd(g, ref(a[0]), ref(a[1]))
            return out
        if op == 'sub':
            return wsub(g, ref(a[0]), ref(a[1]))
        if op == 'mul':
            return wmul(g, ref(a[0]), ref(a[1]))
        if op == 'udiv':
            q, _ = wudiv(g, ref(a[0]), ref(a[1]))
            return q
        if op == 'urem':
            b_ = ref(a[1])
            _, r = wudiv(g, ref(a[0]), b_)
            z = 0
            for bit in b_:
                z = g.OR(z, bit)
            return wmux(g, z, r, ref(a[0]))
        if op in ('sll', 'srl', 'sra'):
            return wshift(g, ref(a[0]), ref(a[1]), op)
        if op in ('sdiv', 'srem', 'smod'):
            x, y = ref(a[0]), ref(a[1])
            ax = wmux(g, x[-1], wneg(g, x), x)
            ay = wmux(g, y[-1], wneg(g, y), y)
            q, r = wudiv(g, ax, ay)
            if op == 'sdiv':
                diff = g.XOR(x[-1], y[-1])
                return wmux(g, diff, wneg(g, q), q)
            if op == 'srem':
                return wmux(g, x[-1], wneg(g, r), r)
            nz = 0
            for bit in r:
                nz = g.OR(nz, bit)
            nu = wneg(g, r)
            r10, _ = wadd(g, nu, y)
            r01, _ = wadd(g, r, y)
            pos = wmux(g, x[-1], r10, r)
            negb = wmux(g, x[-1], nu, r01)
            res = wmux(g, y[-1], negb, pos)
            return wmux(g, nz, res, r)
        raise ValueError('unsupported op: ' + op)

    def word(self, nid, t):
        key = (nid, t)
        if key in self.words:
            return self.words[key]
        stack = [key]
        fuel = 400 * (len(self.m.order) + 1) * (t + 2)
        while stack:
            fuel -= 1
            if fuel < 0:
                raise ValueError('circular definition while blasting')
            k = stack[-1]
            if k in self.words:
                stack.pop()
                continue
            missing = [d for d in self._deps(k) if d not in self.words]
            if missing:
                stack.extend(missing)
                continue
            self.words[k] = self._compute(k)
            stack.pop()
        return self.words[key]

    def bad(self, t):
        lit = 0
        for b in self.m.bads:
            x = self.word(abs(b), t)[0] ^ (1 if b < 0 else 0)
            lit = self.g.OR(lit, x)
        return lit

    def constraint(self, t):
        lit = 1
        for c in self.m.constraints:
            x = self.word(abs(c), t)[0] ^ (1 if c < 0 else 0)
            lit = self.g.AND(lit, x)
        return lit


# -- CDCL ---------------------------------------------------------------------

import heapq

UNSAT, SAT, UNKNOWN = 0, 1, 2


class Solver:
    """MiniSat-style CDCL: two-watched literals, 1UIP learning, VSIDS
    with a lazy heap, geometric restarts, phase saving. Deterministic:
    ties break on variable index, budgets count conflicts, not time."""

    def __init__(self):
        self.clauses = []
        self.watches = []            # watches[l]: clauses to visit when l asserts
        self.assign = []             # -1 unset / 0 false / 1 true
        self.level = []
        self.reason = []
        self.phase = []
        self.act = []
        self.heap = []               # lazy (-activity, var)
        self.trail = []
        self.lim = []                # decision level -> trail mark
        self.qhead = 0
        self.inc = 1.0
        self.conflicts = 0
        self.ok = True

    def new_var(self):
        v = len(self.assign)
        self.assign.append(-1)
        self.level.append(0)
        self.reason.append(-1)
        self.phase.append(0)
        self.act.append(0.0)
        self.watches.append([])
        self.watches.append([])
        heapq.heappush(self.heap, (0.0, v))
        return v

    def value(self, lit):
        a = self.assign[lit >> 1]
        return a if a < 0 else a ^ (lit & 1)

    def add_clause(self, lits):
        if not self.ok:
            return False
        out = sorted(set(lits))
        for lit in out:
            if lit ^ 1 in set(out):
                return True                       # tautology
        out = [l for l in out if self.value(l) != 0 or self.level[l >> 1] > 0]
        if any(self.value(l) == 1 and self.level[l >> 1] == 0 for l in out):
            return True                           # satisfied at root
        if not out:
            self.ok = False
            return False
        if len(out) == 1:
            if not self._enqueue(out[0], -1):
                self.ok = False
            return self.ok
        ci = len(self.clauses)
        self.clauses.append(out)
        self.watches[out[0] ^ 1].append(ci)
        self.watches[out[1] ^ 1].append(ci)
        return True

    def _enqueue(self, lit, reason):
        v = lit >> 1
        want = (lit & 1) ^ 1
        if self.assign[v] != -1:
            return self.assign[v] == want
        self.assign[v] = want
        self.level[v] = len(self.lim)
        self.reason[v] = reason
        self.trail.append(lit)
        return True

    def _propagate(self):
        while self.qhead < len(self.trail):
            p = self.trail[self.qhead]
            self.qhead += 1
            fl = p ^ 1
            ws = self.watches[p]
            i = j = 0
            n = len(ws)
            while i < n:
                ci = ws[i]
                i += 1
                cl = self.clauses[ci]
                if cl[0] == fl:
                    cl[0], cl[1] = cl[1], cl[0]
                first = cl[0]
                if self.value(first) == 1:
                    ws[j] = ci
                    j += 1
                    continue
                for k in range(2, len(cl)):
                    if self.value(cl[k]) != 0:
                        cl[1] = cl[k]
                        cl[k] = fl
                        self.watches[cl[1] ^ 1].append(ci)
                        break
                else:
                    ws[j] = ci
                    j += 1
                    if self.value(first) == 0:
                        while i < n:              # keep the rest watched
                            ws[j] = ws[i]
                            j += 1
                            i += 1
                        del ws[j:]
                        return ci
                    self._enqueue(first, ci)
            del ws[j:]
        return -1

    def _bump(self, v):
        self.act[v] += self.inc
        if self.act[v] > 1e100:
            for u in range(len(self.act)):
                self.act[u] *= 1e-100
            self.inc *= 1e-100
        heapq.heappush(self.heap, (-self.act[v], v))

    def _analyze(self, ci):
        learnt = [0]
        seen = set()
        counter = 0
        p = -1
        idx = len(self.trail)
        cur = len(self.lim)
        while True:
            for q in self.clauses[ci]:
                if q == p:
                    continue
                v = q >> 1
                if v not in seen and self.level[v] > 0:
                    seen.add(v)
                    self._bump(v)
                    if self.level[v] >= cur:
                        counter += 1
                    else:
                        learnt.append(q)
            while True:
                idx -= 1
                p = self.trail[idx]
                if (p >> 1) in seen:
                    break
            counter -= 1
            if counter == 0:
                break
            ci = self.reason[p >> 1]
        learnt[0] = p ^ 1
        if len(learnt) == 1:
            return learnt, 0
        mi = max(range(1, len(learnt)),
                 key=lambda i: self.level[learnt[i] >> 1])
        learnt[1], learnt[mi] = learnt[mi], learnt[1]
        return learnt, self.level[learnt[1] >> 1]

    def _backtrack(self, lvl):
        if len(self.lim) <= lvl:
            return
        mark = self.lim[lvl]
        for lit in self.trail[mark:]:
            v = lit >> 1
            self.phase[v] = self.assign[v]
            self.assign[v] = -1
            self.reason[v] = -1
            heapq.heappush(self.heap, (-self.act[v], v))
        del self.trail[mark:]
        del self.lim[lvl:]
        self.qhead = len(self.trail)

    def _decide(self):
        while self.heap:
            negact, v = heapq.heappop(self.heap)
            if self.assign[v] == -1 and -negact == self.act[v]:
                self.lim.append(len(self.trail))
                self._enqueue(2 * v + (self.phase[v] ^ 1), -1)
                return True
        for v in range(len(self.assign)):         # heap starved: sweep
            if self.assign[v] == -1:
                self.lim.append(len(self.trail))
                self._enqueue(2 * v + (self.phase[v] ^ 1), -1)
                return True
        return False

    def solve(self, assumptions, budget):
        """(status, model | None); UNKNOWN when the conflict budget is
        spent. Sound: UNSAT/SAT are never emitted on a guess."""
        if not self.ok:
            return UNSAT, None
        self._backtrack(0)
        base = self.conflicts
        restart_at, step = 512, 512
        while True:
            ci = self._propagate()
            if ci != -1:
                self.conflicts += 1
                if self.conflicts - base > budget:
                    self._backtrack(0)
                    return UNKNOWN, None
                if len(self.lim) <= len(assumptions):
                    self._backtrack(0)
                    return UNSAT, None
                learnt, bt = self._analyze(ci)
                self._backtrack(max(bt, len(assumptions)))
                if len(learnt) >= 2:
                    nci = len(self.clauses)
                    self.clauses.append(learnt)
                    self.watches[learnt[0] ^ 1].append(nci)
                    self.watches[learnt[1] ^ 1].append(nci)
                    self._enqueue(learnt[0], nci)
                else:
                    self._enqueue(learnt[0], -1)
                self.inc /= 0.95
                if self.conflicts - base > restart_at:
                    step = min(step * 2, 16384)
                    restart_at = self.conflicts - base + step
                    self._backtrack(len(assumptions))
            else:
                if len(self.lim) < len(assumptions):
                    a = assumptions[len(self.lim)]
                    if self.value(a) == 0:
                        self._backtrack(0)
                        return UNSAT, None
                    self.lim.append(len(self.trail))
                    self._enqueue(a, -1)
                    continue
                if not self._decide():
                    model = list(self.assign)
                    self._backtrack(0)
                    return SAT, model


# -- Tseitin ------------------------------------------------------------------

class CNF:
    """Incremental Tseitin encoding of AIG cones into one Solver."""

    def __init__(self, aig):
        self.g = aig
        self.sat = Solver()
        self.varof = {}

    def lit(self, aig_lit):
        if aig_lit < 2:
            raise ValueError('constant literal reached the CNF')
        stack = [aig_lit >> 1]
        while stack:
            n = stack[-1]
            if n in self.varof:
                stack.pop()
                continue
            gate = self.g.nodes[n]
            if gate is None:
                self.varof[n] = self.sat.new_var()
                stack.pop()
                continue
            a, b = gate
            need = [x >> 1 for x in (a, b)
                    if x > 1 and (x >> 1) not in self.varof]
            if need:
                stack.extend(need)
                continue
            stack.pop()
            x = self.varof[n] = self.sat.new_var()
            la = self._enc(a)
            lb = self._enc(b)
            self.sat.add_clause([2 * x + 1, la])
            self.sat.add_clause([2 * x + 1, lb])
            self.sat.add_clause([2 * x, la ^ 1, lb ^ 1])
        return self._enc(aig_lit)

    def _enc(self, aig_lit):
        return 2 * self.varof[aig_lit >> 1] | (aig_lit & 1)


def model_bits(cnf, model, word):
    """Integer value of an AIG word under a SAT model (missing bits: 0)."""
    v = 0
    for i, lit in enumerate(word):
        if lit == 1:
            v |= 1 << i
        elif lit > 1:
            var = cnf.varof.get(lit >> 1)
            if var is not None and model[var] == ((lit & 1) ^ 1):
                v |= 1 << i
    return v


# -- the BMC loop -------------------------------------------------------------

def free_at(m, t):
    """Node ids whose value at frame t is chosen freely (inputs, plus
    uninitialized states at frame 0 and next-less states elsewhere)."""
    out = list(m.inputs)
    for sid in m.states:
        if (t == 0 and sid not in m.init) or (t > 0 and sid not in m.next):
            out.append(sid)
    return sorted(out)


def bmc(m, mode, bound, budget, inf_cap=300, node_cap=4_000_000,
        clause_cap=None):
    """Run BMC to `bound` ('inf' allowed). Returns one of
      ('witness', steps, depth) — inputs extracted and self-replayed
      ('all', K)                — no bad at any depth <= K (proven)
      ('partial', K, note)      — budget/size out after proving K."""
    bl = Blaster(m)
    cnf = CNF(bl.g)
    proven = -1
    k = 0
    vacuous_from = None          # constraints constant-false at some frame
    while bound == 'inf' or k <= int(bound):
        if bound == 'inf' and k > inf_cap:
            return ('partial', proven, 'inf depth cap')
        if vacuous_from is not None:
            return ('all', 'inf')
        if len(bl.g.nodes) > node_cap:
            return ('partial', proven, 'AIG node cap')
        if clause_cap is not None and len(cnf.sat.clauses) > clause_cap:
            return ('partial', proven, 'CNF size cap')
        asm = []
        dead = False
        for t in range(k + 1):
            c = bl.constraint(t)
            if c == 0:
                vacuous_from = t
                dead = True
                break
            if c != 1:
                asm.append(cnf.lit(c))
        if not dead:
            b = bl.bad(k)
            if b == 0:
                proven = k
                k += 1
                continue
            if b != 1:
                asm.append(cnf.lit(b))
            status, model = cnf.sat.solve(asm, budget - cnf.sat.conflicts)
            if status == UNKNOWN:
                return ('partial', proven, 'conflict budget spent')
            if status == SAT:
                steps = []
                for t in range(k + 1):
                    frame = {}
                    for nid in free_at(m, t):
                        val = model_bits(cnf, model, bl.word(nid, t))
                        if val:
                            frame[str(nid)] = val
                    steps.append(frame)
                fired, _ = run(m, steps)
                if fired != k:
                    return ('partial', proven,
                            'internal: model did not replay at depth %d' % k)
                return ('witness', steps, k)
            proven = k
            if cnf.sat.conflicts >= budget:
                return ('partial', proven, 'conflict budget spent')
        else:
            # constraints impossible at frame `vacuous_from`: no valid
            # trace reaches it, so every deeper depth is vacuously safe
            if proven >= vacuous_from - 1:
                return ('all', 'inf')
            return ('partial', proven, 'constraints impossible yet unproven')
        k += 1
    return ('all', int(bound))


if __name__ == "__main__":
    import json
    import sys
    prog, mode, observable, bound, wall = sys.argv[1:6]
    wall_s = float(wall)
    if observable != "bad":
        print(json.dumps({"kind": "partial", "progress":
                          {"note": "btor2-bmcf only decides 'bad'"}},
                         sort_keys=True))
        sys.exit(0)
    m = parse(prog)
    if bound != "inf":
        bound = int(bound)
    budget = max(2000, int(150 * wall_s))
    res = bmc(m, mode, bound, budget,
              clause_cap=max(20000, int(4000 * wall_s)))
    if res[0] == 'witness':
        print(json.dumps({"kind": "witness",
                          "payload": {"steps": res[1]}, "depth": res[2]},
                         sort_keys=True))
    elif res[0] == 'all':
        print(json.dumps({"kind": "all", "bound": res[1]}, sort_keys=True))
    else:
        _, proven, note = res
        if proven >= 0:
            # every depth up to `proven` is a genuine unsat: a bounded
            # universal claim, below the ask
            print(json.dumps({"kind": "all", "bound": proven},
                             sort_keys=True))
        else:
            print(json.dumps({"kind": "partial",
                              "progress": {"note": note}}, sort_keys=True))
