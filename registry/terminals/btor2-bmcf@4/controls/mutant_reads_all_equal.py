"""MUTANT (congruence forgets its index guard)

btor2-bmcf, revision 4: the caps learn the accelerator's pace —
the conflict budget and the structural ceilings (AIG nodes, CNF
clauses) are wall-derived at rates the C mirror sustains, with
absolute ceilings that bound peak memory; nothing else changes and
the revision-3 fragment runs the same code path. Revision 3 was: the
bounded model checker plus arrays —
read, write, array ite, extensional array eq/neq, constant-broadcast
init, symbolic array inputs and states — added by pure insertion: the
revision-2 fragment runs the same code path. Nested arrays (array
elements that are arrays) are outside this solver's fragment and are
refused with a partial, never guessed at.

Usage: solve.py <program.btor2> <mode> <observable> <bound> <wall_s>

Arrays are solved by the eager reduction: array-typed nodes blast to
hash-consed array terms (base / constant / write / ite); every read
resolves through the term to element words — a write compares indices,
an ite muxes, and a symbolic base mints fresh element variables under
Ackermann congruence (equal indices force equal values, added as
global axioms). Extensional eq introduces one literal e per term pair
with a skolem witness index — not-e forces the reads at the witness to
differ — and pointwise instantiation of e at the write indices of both
sides and at every base select, past and future. Every axiom is a
valid array lemma, so an unsat verdict is never manufactured; and a
sat model is replayed through the interpreter semantics before it is
emitted, so a too-sparse instantiation can only cost a witness (a
partial), never invent one. The conflict budget derives from the wall
argument, never from the clock, so two runs emit identical bytes.
"""

MASK = {}


def mask(w):
    m = MASK.get(w)
    if m is None:
        m = MASK[w] = (1 << w) - 1
    return m


def vkey(v):
    if isinstance(v, tuple):
        return (1, vkey(v[1]), tuple((i, vkey(x)) for i, x in v[2]))
    return (0, v)


def acanon(default, items, iw):
    """The canonical sparse array (see btor2@3): default-valued entries
    drop, the default covers the largest domain share, ties to the
    least value — so extensional equality is tuple equality."""
    items = {i: v for i, v in items.items() if v != default}
    dom = 1 << iw
    n = len(items)
    counts = {}
    for v in items.values():
        counts[v] = counts.get(v, 0) + 1
    best, cands = dom - n, [default]
    for v in sorted(counts, key=vkey):
        c = counts[v]
        if c > best:
            best, cands = c, [v]
        elif c == best:
            cands.append(v)
    nd = min(cands, key=vkey)
    if nd != default:
        full = {i: items.get(i, default) for i in range(dom)}
        items = {i: v for i, v in full.items() if v != nd}
        default = nd
    return ('a', default, tuple(sorted(items.items())))


def aget(arr, i):
    for k, v in arr[2]:
        if k == i:
            return v
    return arr[1]


def coerce(sort, raw):
    if isinstance(sort, tuple):
        _, isort, esort = sort
        if isinstance(isort, tuple):
            raise ValueError('array index sort must be bitvec')
        if isinstance(raw, dict):
            d = coerce(esort, raw.get('default', 0))
            items = {int(k) & mask(isort): coerce(esort, v)
                     for k, v in (raw.get('set') or {}).items()}
            return acanon(d, items, isort)
        return acanon(coerce(esort, raw), {}, isort)
    return int(raw) & mask(sort)


class Model:
    def __init__(self):
        self.width = {}      # node id -> bit width | ('a', idx, elem)
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
                if t[2] == 'bitvec':
                    sorts[int(t[0])] = int(t[3])
                elif t[2] == 'array':
                    if isinstance(sorts[int(t[4])], tuple):
                        raise ValueError('nested arrays: outside this '
                                         "solver's fragment")
                    sorts[int(t[0])] = ('a', sorts[int(t[3])],
                                        sorts[int(t[4])])
                else:
                    raise ValueError('unsupported sort: ' + t[2])
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
            vals[nid] = coerce(w, frame_inputs.get(str(nid), 0))
        elif op == 'state':
            if nid in regs:
                vals[nid] = regs[nid]
            else:
                vals[nid] = coerce(w, frame_inputs.get(str(nid), 0))
                regs[nid] = vals[nid]
        elif op == 'read':
            vals[nid] = aget(ref(a[0]), ref(a[1]))
        elif op == 'write':
            arr = ref(a[0])
            items = dict(arr[2])
            items[ref(a[1])] = ref(a[2])
            vals[nid] = acanon(arr[1], items, w[1])
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


def _seed(m, sid, v):
    w = m.width[sid]
    if isinstance(w, tuple):
        if isinstance(v, tuple):
            return v
        if isinstance(w[2], tuple):
            raise ValueError('broadcast init into a nested array')
        return acanon(v & mask(w[2]), {}, w[1])
    return v & mask(w)


def run(m, steps):
    """Run the model under a stimulus; return (bad_fired_depth | None,
    frames run). Constraints must hold at every frame up to the bad."""
    regs = {}
    constrained = True
    for t, frame in enumerate(steps):
        if t == 0:
            pending = {sid: r for sid, r in m.init.items()}
            tmp_vals, tmp_ref = eval_frame(m, dict(), frame, {})
            for sid, r in pending.items():
                regs[sid] = _seed(m, sid, tmp_ref(r))
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
                nxt[sid] = _seed(m, sid, ref(m.next[sid]))
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
    when uninitialized) and to the previous frame's next elsewhere.
    Array-typed nodes build hash-consed array terms instead of words;
    reads resolve through them, and the array axioms (base congruence,
    extensionality) accumulate in self.axioms — global truths assumed
    on every query."""

    def __init__(self, model):
        self.m = model
        self.g = AIG()
        self.words = {}              # (node id, frame) -> literal vector
        self.anodes = [None]         # array term id -> structure
        self.amap = {}               # structure -> array term id
        self.aew = {0: 0}            # array term id -> element width
        self.sel_cache = {}          # (term id, index word) -> element word
        self.base_sels = {}          # base id -> [(index word, element word)]
        self.base_eqs = {}           # base id -> [(e, A, B)]
        self.eq_cache = {}           # (A, B) -> literal e
        self.eq_done = set()         # (e, index word) already instantiated
        self.axioms = []             # AIG literals: valid array lemmas
        self._wix = {}               # term id -> write index words below it
        self._bas = {}               # term id -> base ids below it

    def _aintern(self, struct, ew):
        aid = self.amap.get(struct)
        if aid is None:
            self.anodes.append(struct)
            aid = self.amap[struct] = len(self.anodes) - 1
            self.aew[aid] = ew
            if struct[0] == 'base':
                self.base_sels[aid] = []
                self.base_eqs[aid] = []
        return aid

    def _bases_of(self, aid):
        out = self._bas.get(aid)
        if out is None:
            s = self.anodes[aid]
            if s[0] == 'base':
                out = frozenset([aid])
            elif s[0] == 'constarr':
                out = frozenset()
            elif s[0] == 'write':
                out = self._bases_of(s[1])
            else:                                    # aite
                out = self._bases_of(s[2]) | self._bases_of(s[3])
            self._bas[aid] = out
        return out

    def _write_indices(self, aid):
        out = self._wix.get(aid)
        if out is None:
            s = self.anodes[aid]
            if s[0] == 'write':
                out = self._write_indices(s[1]) | {s[2]}
            elif s[0] == 'aite':
                out = self._write_indices(s[2]) | self._write_indices(s[3])
            else:
                out = frozenset()
            self._wix[aid] = out
        return out

    def _select(self, aid, idx):
        """The element word of an array term at an index word."""
        key = (aid, tuple(idx))
        w = self.sel_cache.get(key)
        if w is not None:
            return w
        g = self.g
        s = self.anodes[aid]
        if s[0] == 'constarr':
            w = list(s[1])
        elif s[0] == 'write':
            hit = weq(g, list(idx), list(s[2]))
            w = wmux(g, hit, list(s[3]), self._select(s[1], idx))
        elif s[0] == 'aite':
            w = wmux(g, s[1], self._select(s[2], idx),
                     self._select(s[3], idx))
        else:                                        # a symbolic base
            w = [g.var() for _ in range(self.aew[aid])]
            self.sel_cache[key] = w      # before axioms: reentry-safe
            for pidx, pw in list(self.base_sels[aid]):
                same = weq(g, list(idx), list(pidx))
                agree = weq(g, w, list(pw))
                self.axioms.append(agree)
            self.base_sels[aid].append((tuple(idx), tuple(w)))
            for rec in list(self.base_eqs[aid]):
                self._inst_eq(rec, tuple(idx))
        self.sel_cache[key] = w
        return w

    def _inst_eq(self, rec, idx):
        """Pointwise instantiation of extensionality: e -> the two
        sides read equal at this index. A valid lemma either way."""
        e, aA, aB = rec
        k = (e, idx)
        if k in self.eq_done:
            return
        self.eq_done.add(k)
        ra = self._select(aA, list(idx))
        rb = self._select(aB, list(idx))
        self.axioms.append(self.g.OR(e ^ 1, weq(self.g, ra, rb)))

    def _aeq(self, aA, aB, iw):
        """One literal for extensional equality of two array terms:
        not-e forces a skolem witness index where the reads differ;
        e forces pointwise equality at both sides' write indices and
        at every base select, past and future."""
        if aA == aB:
            return 1
        key = (min(aA, aB), max(aA, aB))
        e = self.eq_cache.get(key)
        if e is not None:
            return e
        g = self.g
        e = g.var()
        self.eq_cache[key] = e
        rec = (e, aA, aB)
        for b in sorted(self._bases_of(aA) | self._bases_of(aB)):
            self.base_eqs[b].append(rec)
            for pidx, _ in list(self.base_sels[b]):
                self._inst_eq(rec, pidx)
        for idx in sorted(self._write_indices(aA)
                          | self._write_indices(aB)):
            self._inst_eq(rec, idx)
        wit = [g.var() for _ in range(iw)]
        ra = self._select(aA, wit)
        rb = self._select(aB, wit)
        self.axioms.append(g.OR(e, weq(g, ra, rb) ^ 1))
        return e

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
        if isinstance(w, tuple):
            if r < 0:
                raise ValueError('negated array reference')
            return w
        return wnot(self.g, w) if r < 0 else w

    def _compute(self, key):
        m, g = self.m, self.g
        nid, t = key
        op, a = m.node[nid]
        w = m.width[nid]

        def ref(r, at=None):
            return self._lookup(r, t if at is None else at)

        def aid_of(v):
            return v[1]

        arr_sorted = isinstance(w, tuple)
        if op == 'const':
            return wconst(a[0], w)
        if op == 'input':
            if arr_sorted:
                return ('ARR', self._aintern(('base', nid, t), w[2]))
            return [g.var() for _ in range(w)]
        if op == 'state':
            r = m.init.get(nid) if t == 0 else m.next.get(nid)
            if arr_sorted:
                if r is None:
                    return ('ARR', self._aintern(('base', nid, t), w[2]))
                v = ref(r, t if t == 0 else t - 1)
                if isinstance(v, tuple):
                    return v
                # a bitvec init broadcasts into the constant array
                return ('ARR', self._aintern(('constarr', tuple(v)), w[2]))
            if r is None:
                return [g.var() for _ in range(w)]
            return ref(r, t if t == 0 else t - 1)
        if op == 'read':
            return self._select(aid_of(ref(a[0])), ref(a[1]))
        if op == 'write':
            return ('ARR', self._aintern(
                ('write', aid_of(ref(a[0])), tuple(ref(a[1])),
                 tuple(ref(a[2]))), w[2]))
        if op == 'ite':
            if arr_sorted:
                c = ref(a[0])[0]
                x, y = aid_of(ref(a[1])), aid_of(ref(a[2]))
                if c == 1 or x == y:
                    return ('ARR', x)
                if c == 0:
                    return ('ARR', y)
                return ('ARR', self._aintern(('aite', c, x, y), w[2]))
            return wmux(g, ref(a[0])[0], ref(a[1]), ref(a[2]))
        if op in ('eq', 'neq') and isinstance(m.width[abs(a[0])], tuple):
            iw = m.width[abs(a[0])][1]
            e = self._aeq(aid_of(ref(a[0])), aid_of(ref(a[1])), iw)
            return [e if op == 'eq' else e ^ 1]
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
            # the array axioms are global truths: every query assumes
            # every axiom minted so far (bad/constraint cones minted
            # them; instantiation only ever adds valid lemmas)
            for ax in bl.axioms:
                if ax == 0:
                    raise ValueError('internal: contradictory array axiom')
                if ax != 1:
                    asm.append(cnf.lit(ax))
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
                        wd = m.width[nid]
                        if isinstance(wd, tuple):
                            aval = bl.words.get((nid, t))
                            if aval is None:
                                continue         # never observed: default
                            entries = {}
                            for pidx, pw in bl.base_sels.get(aval[1], []):
                                iv = model_bits(cnf, model, list(pidx))
                                vv = model_bits(cnf, model, list(pw))
                                entries.setdefault(iv, vv)
                            if entries:
                                frame[str(nid)] = {
                                    "default": 0,
                                    "set": {str(i): entries[i]
                                            for i in sorted(entries)}}
                        else:
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
    if bound != "inf":
        bound = int(bound)
    budget = max(2000, int(400 * wall_s))
    try:
        m = parse(prog)
        res = bmc(m, mode, bound, budget,
                  node_cap=max(4_000_000,
                               min(12_000_000, int(20_000 * wall_s))),
                  clause_cap=max(20000,
                                 min(18_000_000, int(30_000 * wall_s))))
    except ValueError as exc:
        print(json.dumps({"kind": "partial",
                          "progress": {"note": str(exc)}}, sort_keys=True))
        sys.exit(0)
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
