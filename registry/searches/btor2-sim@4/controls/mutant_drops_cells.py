"""Negative control: the revision-4 search that drops every array's cells from the witness it writes — the candidate replays inside the solver with its cells, then only each array's default is emitted. The judge's replay must refuse what this writes."""

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


# -- explicit-state search ----------------------------------------------------

def free_at(m, t):
    out = list(m.inputs)
    for sid in m.states:
        if (t == 0 and sid not in m.init) or (t > 0 and sid not in m.next):
            out.append(sid)
    return sorted(out)


def free_bits(m, t):
    return sum(m.width[n] for n in free_at(m, t))


def valuation(m, nodes, idx):
    frame = {}
    for n in nodes:
        w = m.width[n]
        v = idx & ((1 << w) - 1)
        idx >>= w
        if v:
            frame[str(n)] = v
    return frame


def one_frame(m, regs, frame, first):
    """Evaluate one frame. Returns (constraints_ok, bad, next_regs)."""
    regs = dict(regs)
    if first:
        tmp_vals, tmp_ref = eval_frame(m, dict(), frame, {})
        for sid, r in m.init.items():
            regs[sid] = tmp_ref(r) & mask(m.width[sid])
    vals, ref = eval_frame(m, regs, frame, {})
    for c in m.constraints:
        if not ref(c):
            return False, False, None
    bad = any(ref(b) for b in m.bads)
    nxt = tuple(ref(m.next[sid]) & mask(m.width[sid])
                for sid in m.states if sid in m.next)
    return True, bad, nxt


def with_regs(m, key):
    order = [sid for sid in m.states if sid in m.next]
    return dict(zip(order, key))


def exhaustive(m, bound, evals, state_cap=200000):
    """Breadth-first over all constrained traces. Returns
    ('witness', steps, depth) | ('all', k|'inf') | ('partial', spent)
    or None when the free-bit widths make enumeration infeasible."""
    if free_bits(m, 0) > 16 or free_bits(m, 1) > 12:
        return None
    f0, f1 = free_at(m, 0), free_at(m, 1)
    seen = {}
    frontier = {}
    spent = 0
    for idx in range(1 << free_bits(m, 0)):
        frame = valuation(m, f0, idx)
        ok, bad, nxt = one_frame(m, {}, frame, True)
        spent += 1
        if not ok:
            continue
        if bad:
            return ('witness', [frame], 0)
        if nxt not in seen:
            seen[nxt] = (None, frame)
            frontier[nxt] = True
        if spent > evals:
            return ('partial', spent)
    t = 0
    while frontier:
        if bound != 'inf' and t >= int(bound):
            return ('all', int(bound))
        t += 1
        nxt_frontier = {}
        for key in frontier:
            regs = with_regs(m, key)
            for idx in range(1 << free_bits(m, 1)):
                frame = valuation(m, f1, idx)
                ok, bad, nkey = one_frame(m, regs, frame, False)
                spent += 1
                if spent > evals or len(seen) > state_cap:
                    return ('partial', spent)
                if not ok:
                    continue
                if bad:
                    steps = [frame]
                    back = key
                    while back is not None:
                        parent, pframe = seen[back]
                        steps.insert(0, pframe)
                        back = parent
                    return ('witness', steps, t)
                if nkey not in seen:
                    seen[nkey] = (key, frame)
                    nxt_frontier[nkey] = True
        frontier = nxt_frontier
    return ('all', 'inf')          # state space closed without a bad


def sampled(m, bound, tries):
    """Deterministic guided sampling: constant patterns, then a seeded
    PRNG. Finds witnesses only; proves nothing."""
    import random
    rng = random.Random(12345)
    depth = 40 if bound == 'inf' else int(bound)
    free0, free1 = free_at(m, 0), free_at(m, 1)

    def attempt(mk):
        steps = []
        regs = {}
        first = True
        for t in range(depth + 1):
            frame = mk(t, free0 if t == 0 else free1)
            ok, bad, nxt = one_frame(m, regs, frame, first)
            steps.append(frame)
            if not ok:
                return None
            if bad:
                return steps[:t + 1], t
            regs = with_regs(m, nxt)
            first = False
        return None

    n = 0
    for c in (0, 1, 2, 3, (1 << 64) - 1):
        if n >= tries:
            break
        n += 1
        hit = attempt(lambda t, ns: {str(x): c & mask(m.width[x])
                                     for x in ns if c & mask(m.width[x])})
        if hit:
            return hit
    while n < tries:
        n += 1
        pick = rng.randrange(3)

        def mk(t, ns):
            frame = {}
            for x in ns:
                wd = m.width[x]
                if pick == 0:
                    v = rng.randrange(min(16, 1 << wd))
                elif pick == 1:
                    v = rng.getrandbits(wd)
                else:
                    v = rng.choice([0, 1, mask(wd)])
                if v:
                    frame[str(x)] = v
            return frame
        hit = attempt(mk)
        if hit:
            return hit
    return None


# -- revision 4: arrays -------------------------------------------------------
#
# Everything above is revision 3's text, untouched: an array-free
# program never reaches this section, so its bytes are the
# predecessor's. A program the parser above refuses for an array sort
# is handed to array_main below, which carries arrays as sparse maps
# and samples — witnesses only, never a claim.
#
# The semantics matched are btor2@5's, whose front end is embedded
# below (vkey, acanon, aget, coerce, aparse, aeval_frame, _seed, arun —
# the interpreter's text with its names prefixed): a stimulus gives an
# array-sorted input, an uninitialized array state at frame 0, or a
# next-less array state at any frame either as an integer (the constant
# array) or as {"default": v, "set": {"<index>": value}}; a cell never
# written before it is read holds the default; a bit-vector init or
# next broadcasts into every cell; array eq/neq is extensional. The
# sampler draws a free array's cells lazily — a fresh value the first
# time a cell is read, remembered thereafter — so a run is consistent
# with the stimulus it emits, and every candidate witness is replayed
# through the embedded interpreter before it is written, so a witness
# this search emits is one the judge accepts.
#
# Guided sampling reads the transition relation off the model: at
# every frame one case of every constraint, of the next function of
# every one-bit state that bad depends on monotonically, and of bad
# itself is chosen at random — cases whose state-only guards already
# fail are pruned — and the equalities `free = expr` and one-bit
# literals in that case fix the free nodes they name; the rest are
# drawn as before. Programs whose transition relation is written as
# equalities over next-value inputs (the sosylab encodings) are the
# ones this reaches. Effort derives from the wall argument, never the
# clock.

import random
import sys


def vkey(v):
    """A total order over values (ints below arrays, recursively) for
    deterministic canonicalization tie-breaks."""
    if isinstance(v, tuple):
        return (1, vkey(v[1]), tuple((i, vkey(x)) for i, x in v[2]))
    return (0, v)


def acanon(default, items, iw):
    """The canonical sparse array over a 2^iw index domain: entries
    equal to the default are dropped, and the default is the value
    covering the largest share of the domain (ties to the least by
    vkey) — canonical, so extensional equality is tuple equality.
    Switching the default is only possible when the map covers at
    least half the domain, which keeps the complement enumeration
    linear in the map."""
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
    """A stimulus value shaped to its sort: ints mask, arrays build
    canonically (an int broadcasts; a dict gives default and entries)."""
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


def aparse(path):
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


def aeval_frame(m, regs, frame_inputs, cache):
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
                # uninitialized (frame 0) or next-less: read the stimulus
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
    """A state's register value shaped to its sort: bitvecs mask,
    arrays pass through canonically (a bitvec init broadcasts)."""
    w = m.width[sid]
    if isinstance(w, tuple):
        if isinstance(v, tuple):
            return v
        if isinstance(w[2], tuple):
            raise ValueError('broadcast init into a nested array')
        return acanon(v & mask(w[2]), {}, w[1])
    return v & mask(w)


def arun(m, steps):
    """Run the model under a stimulus; return (bad_fired_depth | None,
    frames run). Constraints must hold at every frame up to the bad."""
    regs = {}
    constrained = True
    for t, frame in enumerate(steps):
        # frame 0: pre-fill initialized states (init refs evaluate in a
        # first pass restricted to nodes the init value depends on —
        # ids ascend, so a plain full pass with states-read-from-regs
        # works when we seed initialized states first)
        if t == 0:
            pending = {sid: r for sid, r in m.init.items()}
            # init values are constants or combinational over inputs;
            # evaluate them with a mini pass that treats *other*
            # uninitialized states as stimulus
            tmp_vals, tmp_ref = aeval_frame(m, dict(), frame, {})
            for sid, r in pending.items():
                regs[sid] = _seed(m, sid, tmp_ref(r))
        vals, ref = aeval_frame(m, regs, frame, {})
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


# -- arrays as sparse maps, cells drawn as they are read ---------------------

class Base:
    """One free array's contents: a default and the cells drawn so far.
    A cell read before it is written is drawn on that first read and
    remembered; a frozen base draws no more (its unread cells are the
    default, as in the stimulus that will be emitted). draw is None for
    a constant array."""
    __slots__ = ('iw', 'ew', 'default', 'cells', 'frozen', 'draw')

    def __init__(self, iw, ew, default, draw):
        self.iw, self.ew, self.default = iw, ew, default
        self.cells = {}
        self.frozen = draw is None
        self.draw = draw


def lconst(w, v):
    return ('L', Base(w[1], w[2], v & mask(w[2]), None), {})


def lget(b, i):
    c = b.cells
    if i in c:
        return c[i]
    if b.frozen:
        return b.default
    v = c[i] = b.draw()
    return v


def lread(arr, i):
    ov = arr[2]
    if i in ov:
        return ov[i]
    return lget(arr[1], i)


def lwrite(arr, i, v):
    ov = dict(arr[2])
    ov[i] = v
    return ('L', arr[1], ov)


def leq(x, y):
    """Extensional equality of two lazy arrays. Over one base only the
    written cells can differ. Over two bases a small domain is compared
    cell by cell (every cell becomes known, so nothing can change), and
    a large one is compared on every known cell plus the defaults —
    equality then freezes both bases, so no later draw can contradict
    the verdict; inequality rests on a cell that stays."""
    if x is y:
        return True
    bx, by = x[1], y[1]
    keys = list(x[2])
    keys += [k for k in y[2] if k not in x[2]]
    if bx is by:
        for k in keys:
            if lread(x, k) != lread(y, k):
                return False
        return True
    if bx.iw <= 8:
        for k in range(1 << bx.iw):
            if lread(x, k) != lread(y, k):
                return False
        return True
    keys += [k for k in bx.cells if k not in x[2] and k not in y[2]]
    keys += [k for k in by.cells if k not in x[2] and k not in y[2]
             and k not in bx.cells]
    for k in keys:
        if lread(x, k) != lread(y, k):
            return False
    if bx.default != by.default:
        return False
    bx.frozen = by.frozen = True
    return True


def lseed(m, sid, v):
    w = m.width[sid]
    if isinstance(w, tuple):
        if isinstance(v, tuple):
            return v
        return lconst(w, v)
    return v & mask(w)


def lzero(w):
    return lconst(w, 0) if isinstance(w, tuple) else 0


def lstim(arr):
    """The stimulus value the interpreter reads for this array: the
    default and every cell known to differ from it — drawn or written —
    or None for the constant-zero array the interpreter assumes when
    an entry is missing."""
    b = arr[1]
    d = b.default
    items = {}
    for i, v in b.cells.items():
        if v != d:
            items[str(i)] = v
    for i, v in arr[2].items():
        if v != d:
            items[str(i)] = v
        else:
            items.pop(str(i), None)
    if items:
        return {"default": d, "set": items}
    return d if d else None


def node_args(op, a):
    if op in ('slice', 'uext', 'sext'):
        return a[:1]
    return a


class Attempt:
    """One sampled trace's randomness: the pattern every free value is
    drawn by, and the bases of its free arrays, keyed by node and
    frame so the two passes of frame 0 see one array."""

    def __init__(self, rng, pick, const):
        self.rng, self.pick, self.const = rng, pick, const
        self.bases = {}
        self.spent = 0

    def bits(self, w):
        if self.const is not None:
            return self.const & mask(w)
        if self.pick == 0:
            return self.rng.randrange(min(16, 1 << w))
        if self.pick == 1:
            return self.rng.getrandbits(w)
        return self.rng.choice((0, 1, mask(w)))

    def base(self, nid, t, w):
        key = (nid, t)
        b = self.bases.get(key)
        if b is None:
            iw, ew = w[1], w[2]
            if self.const is not None:
                b = Base(iw, ew, self.const & mask(ew), None)
            else:
                b = Base(iw, ew, self.bits(ew), lambda: self.bits(ew))
            self.bases[key] = b
        return ('L', b, {})


class LazyFrame:
    """One frame evaluated on demand, exactly as the interpreter would
    given the stimulus this frame ends up choosing: main values (mode 0)
    read initialized states from their init at frame 0 and from the
    registers later; tmp values (mode 1, frame 0 only) are the
    interpreter's first pass, every state read as stimulus. A free node
    takes its value the first time either pass touches it — from an
    assignment the guide made, else drawn — and keeps it."""
    __slots__ = ('m', 'att', 't', 'tk', 'regs', 'assign', 'frame',
                 'vals', 'inprog')

    def __init__(self, m, att, t, regs):
        self.m, self.att, self.t = m, att, t
        self.tk = 0 if t == 0 else 1
        self.regs = regs
        self.assign = {}
        self.frame = {}
        self.vals = ({}, {})
        self.inprog = set()

    def free(self, n):
        op = self.m.node[n][0]
        if op == 'input':
            return True
        if op != 'state':
            return False
        return n not in (self.m.init if self.tk == 0 else self.m.next)

    def ref(self, r, md=0):
        v = self.get(abs(r), md)
        if r < 0:
            if isinstance(v, tuple):
                raise ValueError('negated array reference')
            return ~v & mask(self.m.width[abs(r)])
        return v

    def _rref(self, vs, r):
        v = vs[abs(r)]
        if r < 0:
            if isinstance(v, tuple):
                raise ValueError('negated array reference')
            return ~v & mask(self.m.width[abs(r)])
        return v

    def _stim_deps(self, n):
        if n in self.frame:
            return ()
        asg = self.assign.get(n)
        if asg is None or asg[0] != 'ref':
            return ()
        r = abs(asg[1])
        if r in self.vals[0]:
            return ()
        if (r, 0) in self.inprog:
            del self.assign[n]           # a cycle through assignments
            return ()
        return ((r, 0),)

    def _deps(self, n, md):
        m = self.m
        op, a = m.node[n]
        if op == 'const':
            return ()
        if op == 'input':
            return self._stim_deps(n)
        if op == 'state':
            if md == 1:
                return () if n in m.init else self._stim_deps(n)
            if n in self.regs:
                return ()
            if self.t == 0 and n in m.init:
                r = abs(m.init[n])
                return () if r in self.vals[1] else ((r, 1),)
            return self._stim_deps(n)
        vs = self.vals[md]
        return tuple((abs(x), md) for x in node_args(op, a)
                     if abs(x) not in vs)

    def get(self, nid, md=0):
        vals = self.vals[md]
        if nid in vals:
            return vals[nid]
        stack = [(nid, md)]
        inprog = self.inprog
        while stack:
            n, k = stack[-1]
            vs = self.vals[k]
            if n in vs:
                stack.pop()
                continue
            deps = self._deps(n, k)
            if deps:
                inprog.add((n, k))
                stack.extend(deps)
                continue
            vs[n] = self._compute(n, k)
            inprog.discard((n, k))
            stack.pop()
        return vals[nid]

    def stim(self, n):
        fr = self.frame
        if n in fr:
            return fr[n]
        m = self.m
        w = m.width[n]
        asg = self.assign.get(n)
        v = None
        if asg is not None:
            if asg[0] == 'const':
                v = lconst(w, asg[1]) if isinstance(w, tuple) \
                    else asg[1] & mask(w)
            elif abs(asg[1]) in self.vals[0]:
                r = asg[1]
                if isinstance(w, tuple):
                    if r > 0 and isinstance(self.vals[0][r], tuple):
                        v = self.vals[0][r]
                else:
                    x = self._rref(self.vals[0], r)
                    if not isinstance(x, tuple):
                        v = x & mask(w)
        if v is None:
            if isinstance(w, tuple):
                v = self.att.base(n, self.t, w)
            else:
                v = self.att.bits(w)
        fr[n] = v
        return v

    def _compute(self, nid, md):
        m = self.m
        op, a = m.node[nid]
        w = m.width[nid]
        vs = self.vals[md]
        if op == 'const':
            return a[0]
        if op == 'input':
            return self.stim(nid)
        if op == 'state':
            if md == 1:
                return lzero(w) if nid in m.init else self.stim(nid)
            if nid in self.regs:
                return self.regs[nid]
            if self.t == 0 and nid in m.init:
                return lseed(m, nid, self._rref(self.vals[1], m.init[nid]))
            return self.stim(nid)

        def ref(r):
            v = vs[abs(r)]
            if r < 0:
                if isinstance(v, tuple):
                    raise ValueError('negated array reference')
                return ~v & mask(m.width[abs(r)])
            return v

        if op == 'read':
            return lread(ref(a[0]), ref(a[1]))
        if op == 'write':
            return lwrite(ref(a[0]), ref(a[1]), ref(a[2]))
        if op == 'ite':
            return ref(a[1]) if ref(a[0]) else ref(a[2])
        if op == 'eq':
            x, y = ref(a[0]), ref(a[1])
            if isinstance(x, tuple):
                return 1 if leq(x, y) else 0
            return 1 if x == y else 0
        if op == 'neq':
            x, y = ref(a[0]), ref(a[1])
            if isinstance(x, tuple):
                return 0 if leq(x, y) else 1
            return 1 if x != y else 0
        if op == 'and':
            return ref(a[0]) & ref(a[1])
        if op == 'or':
            return ref(a[0]) | ref(a[1])
        if op == 'not':
            return ~ref(a[0]) & mask(w)
        if op == 'slice':
            return (ref(a[0]) >> a[2]) & mask(w)
        if op == 'uext':
            return ref(a[0])
        if op == 'sext':
            sw = m.width[abs(a[0])]
            return _signed(ref(a[0]), sw) & mask(w)
        if op == 'concat':
            return (ref(a[0]) << m.width[abs(a[1])]) | ref(a[1])
        if op == 'neg':
            return -ref(a[0]) & mask(w)
        if op == 'inc':
            return (ref(a[0]) + 1) & mask(w)
        if op == 'dec':
            return (ref(a[0]) - 1) & mask(w)
        if op == 'redand':
            aw = m.width[abs(a[0])]
            return 1 if ref(a[0]) == mask(aw) else 0
        if op == 'redor':
            return 1 if ref(a[0]) else 0
        if op == 'redxor':
            return bin(ref(a[0])).count('1') & 1
        if op == 'xor':
            return ref(a[0]) ^ ref(a[1])
        if op == 'nand':
            return ~(ref(a[0]) & ref(a[1])) & mask(w)
        if op == 'nor':
            return ~(ref(a[0]) | ref(a[1])) & mask(w)
        if op == 'xnor':
            return ~(ref(a[0]) ^ ref(a[1])) & mask(w)
        if op == 'implies':
            return (1 ^ ref(a[0])) | ref(a[1])
        if op == 'iff':
            return 1 ^ ref(a[0]) ^ ref(a[1])
        if op == 'ult':
            return 1 if ref(a[0]) < ref(a[1]) else 0
        if op == 'ulte':
            return 1 if ref(a[0]) <= ref(a[1]) else 0
        if op == 'ugt':
            return 1 if ref(a[0]) > ref(a[1]) else 0
        if op == 'ugte':
            return 1 if ref(a[0]) >= ref(a[1]) else 0
        if op in ('slt', 'slte', 'sgt', 'sgte'):
            aw = m.width[abs(a[0])]
            x, y = _signed(ref(a[0]), aw), _signed(ref(a[1]), aw)
            return 1 if ((op == 'slt' and x < y)
                         or (op == 'slte' and x <= y)
                         or (op == 'sgt' and x > y)
                         or (op == 'sgte' and x >= y)) else 0
        if op == 'add':
            return (ref(a[0]) + ref(a[1])) & mask(w)
        if op == 'sub':
            return (ref(a[0]) - ref(a[1])) & mask(w)
        if op == 'mul':
            return (ref(a[0]) * ref(a[1])) & mask(w)
        if op == 'udiv':
            d = ref(a[1])
            return (ref(a[0]) // d) & mask(w) if d else mask(w)
        if op == 'urem':
            d = ref(a[1])
            return (ref(a[0]) % d) & mask(w) if d else ref(a[0])
        if op in ('sdiv', 'srem', 'smod'):
            sa = _signed(ref(a[0]), w)
            sb = _signed(ref(a[1]), w)
            if op == 'sdiv':
                if sb == 0:
                    return 1 if sa < 0 else mask(w)
                q = abs(sa) // abs(sb)
                return (q if (sa < 0) == (sb < 0) else -q) & mask(w)
            if op == 'srem':                   # sign follows dividend
                if sb == 0:
                    return sa & mask(w)
                r = abs(sa) % abs(sb)
                return (-r if sa < 0 else r) & mask(w)
            if sb == 0:                        # smod: sign follows divisor
                return sa & mask(w)
            u = abs(sa) % abs(sb)
            if u == 0:
                return 0
            if sa >= 0 and sb >= 0:
                return u
            if sa < 0 and sb >= 0:
                return (-u + sb) & mask(w)
            if sa >= 0 and sb < 0:
                return (u + sb) & mask(w)
            return (-u) & mask(w)
        if op == 'sll':
            sh = ref(a[1])
            return (ref(a[0]) << sh) & mask(w) if sh < w else 0
        if op == 'srl':
            sh = ref(a[1])
            return ref(a[0]) >> sh if sh < w else 0
        if op == 'sra':
            sh = ref(a[1])
            sv = _signed(ref(a[0]), w)
            return (sv >> sh) & mask(w) if sh < w else \
                (mask(w) if sv < 0 else 0)
        raise ValueError('unsupported op: ' + op)

    def finish(self):
        """(constraints_ok, bad, next_regs), the interpreter's reading of
        this frame; counts the nodes evaluated toward the budget."""
        m = self.m
        ok = True
        for c in m.constraints:
            if not self.ref(c):
                ok = False
                break
        bad = False
        nxt = None
        if ok:
            bad = any(self.ref(b) for b in m.bads)
            nxt = {}
            for sid in m.states:
                if sid in m.next:
                    nxt[sid] = lseed(m, sid, self.ref(m.next[sid]))
        self.att.spent += len(self.vals[0]) + len(self.vals[1]) + 16
        return ok, bad, nxt


# -- reading the transition relation off the model ---------------------------

class Guide:
    """The static side of guided sampling: which nodes are free at
    frame 0 and later, which cones hold no free node (guards decidable
    from the state alone), the roots to satisfy — every constraint, the
    next function of every one-bit state bad depends on monotonically
    (wanted at its polarity in bad, when that function can be read
    off), and bad itself — and the case counts that make the walk
    choose uniformly among a root's cases."""

    def __init__(self, m):
        self.m = m
        self.hf = (self._has_free(0), self._has_free(1))
        self.counts = {}
        self.roots = self._roots()
        self.assignable = any(k == 'n' for _, _, k in self.roots) or \
            any(self._assignable(abs(r), 1) for r, _, k in self.roots
                if k != 'n')

    def _has_free(self, tk):
        m = self.m
        tmp = {}
        if tk == 0:
            for nid in m.order:
                op, a = m.node[nid]
                if op == 'input':
                    tmp[nid] = True
                elif op == 'state':
                    tmp[nid] = nid not in m.init
                elif op == 'const':
                    tmp[nid] = False
                else:
                    tmp[nid] = any(tmp[abs(x)] for x in node_args(op, a))
        hf = {}
        for nid in m.order:
            op, a = m.node[nid]
            if op == 'input':
                hf[nid] = True
            elif op == 'state':
                if tk == 0:
                    hf[nid] = nid not in m.init or tmp[abs(m.init[nid])]
                else:
                    hf[nid] = nid not in m.next
            elif op == 'const':
                hf[nid] = False
            else:
                hf[nid] = any(hf[abs(x)] for x in node_args(op, a))
        return hf

    def _free(self, n, tk):
        m = self.m
        op = m.node[n][0]
        if op == 'input':
            return True
        if op != 'state':
            return False
        return n not in (m.init if tk == 0 else m.next)

    def _assignable(self, root, tk):
        """Does the cone of root hold a literal the walk could fix — a
        free one-bit node, or an equality with a free side?"""
        m = self.m
        seen = {}
        stack = [root]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen[n] = True
            op, a = m.node[n]
            if op == 'const':
                continue
            if op in ('input', 'state'):
                if m.width[n] == 1 and self._free(n, tk):
                    return True
                continue
            if op in ('eq', 'neq'):
                if any(self._free(abs(x), tk) for x in a):
                    return True
            stack.extend(abs(x) for x in node_args(op, a))
        return False

    def _polarity(self):
        """Each state's polarity in the bad cone through the monotone
        connectives: 1 positive, 2 negative, 3 mixed."""
        m = self.m
        pol = {}
        seen = {}
        stack = [(b, 1) for b in m.bads]
        while stack:
            r, p = stack.pop()
            n = abs(r)
            if r < 0:
                p = 3 - p if p != 3 else 3
            key = (n, p)
            if key in seen:
                continue
            seen[key] = True
            op, a = m.node[n]
            if op == 'state':
                pol[n] = pol.get(n, 0) | p
            elif op in ('and', 'or'):
                stack.append((a[0], p))
                stack.append((a[1], p))
            elif op == 'not':
                stack.append((a[0], 3 - p if p != 3 else 3))
            elif op == 'implies':
                stack.append((a[0], 3 - p if p != 3 else 3))
                stack.append((a[1], p))
            elif op == 'ite' and m.width[n] == 1:
                stack.append((a[0], 3))
                stack.append((a[1], p))
                stack.append((a[2], p))
            elif op != 'const':
                stack.extend((x, 3) for x in node_args(op, a))
        return pol

    def _roots(self):
        m = self.m
        roots = [(c, 1, 'c') for c in m.constraints]
        pol = self._polarity()
        picked = 0
        for sid in m.states:
            if m.width[sid] != 1 or sid not in m.next or picked >= 8:
                continue
            p = pol.get(sid, 0)
            if p not in (1, 2):
                continue
            r = m.next[sid]
            op = m.node[abs(r)][0]
            if op in ('input', 'state', 'const'):
                continue
            if not self._assignable(abs(r), 1):
                continue
            roots.append((r, 1 if p == 1 else 0, 'n'))
            picked += 1
        roots += [(b, 1, 'b') for b in m.bads]
        return roots

    def count(self, r, want):
        n = abs(r)
        if r < 0:
            want ^= 1
        key = (n, want)
        c = self.counts.get(key)
        if c is not None:
            return c
        m = self.m
        op, a = m.node[n]
        if m.width[n] != 1:
            c = 1
        elif op == 'and':
            c = (self.count(a[0], 1) * self.count(a[1], 1) if want
                 else self.count(a[0], 0) + self.count(a[1], 0))
        elif op == 'or':
            c = (self.count(a[0], 1) + self.count(a[1], 1) if want
                 else self.count(a[0], 0) * self.count(a[1], 0))
        elif op == 'not':
            c = self.count(a[0], 1 - want)
        elif op == 'implies':
            c = (self.count(a[0], 0) + self.count(a[1], 1) if want
                 else self.count(a[0], 1) * self.count(a[1], 0))
        elif op == 'ite':
            c = (self.count(a[0], 1) * self.count(a[1], want)
                 + self.count(a[0], 0) * self.count(a[2], want))
        else:
            c = 1
        c = min(c, 1 << 40)
        self.counts[key] = c
        return c

    def _order(self, lf, x, y):
        """Walk state-only conjuncts first: a dead case is found before
        its literals are drawn."""
        hf = self.hf[lf.tk]
        if hf[abs(x)] and not hf[abs(y)]:
            return y, x
        return x, y

    def _one(self, lf, rng, options, out):
        """Walk one of the options — each a list of literals to hold
        jointly — chosen at random in proportion to its cases, falling
        through to the next when it is dead."""
        weights = []
        for opt in options:
            w = 1
            for r, want in opt:
                w *= self.count(r, want)
            weights.append(min(w, 1 << 40))
        order = list(range(len(options)))
        while order:
            total = sum(weights[i] for i in order)
            pick = rng.randrange(total)
            chosen = order[-1]
            for i in order:
                if pick < weights[i]:
                    chosen = i
                    break
                pick -= weights[i]
            order.remove(chosen)
            save = dict(out)
            good = True
            for r, want in options[chosen]:
                if not self.walk(lf, rng, r, want, out):
                    good = False
                    break
            if good:
                return True
            out.clear()
            out.update(save)
        return False

    def walk(self, lf, rng, r, want, out):
        """One case of ref r taking value want at lf's frame: guards
        without a free node are decided now on the frame; literals on
        free nodes land in out (first assignment wins). False when the
        case is dead."""
        m = self.m
        n = abs(r)
        if r < 0:
            want ^= 1
        if not self.hf[lf.tk][n]:
            return (lf.get(n) & 1) == want
        op, a = m.node[n]
        if m.width[n] == 1:
            if op == 'and':
                if want:
                    x, y = self._order(lf, a[0], a[1])
                    return (self.walk(lf, rng, x, 1, out)
                            and self.walk(lf, rng, y, 1, out))
                return self._one(lf, rng, [[(a[0], 0)], [(a[1], 0)]], out)
            if op == 'or':
                if want:
                    return self._one(lf, rng, [[(a[0], 1)], [(a[1], 1)]],
                                     out)
                x, y = self._order(lf, a[0], a[1])
                return (self.walk(lf, rng, x, 0, out)
                        and self.walk(lf, rng, y, 0, out))
            if op == 'not':
                return self.walk(lf, rng, a[0], 1 - want, out)
            if op == 'implies':
                if want:
                    return self._one(lf, rng, [[(a[0], 0)], [(a[1], 1)]],
                                     out)
                return (self.walk(lf, rng, a[0], 1, out)
                        and self.walk(lf, rng, a[1], 0, out))
            if op == 'ite':
                return self._one(lf, rng, [[(a[0], 1), (a[1], want)],
                                           [(a[0], 0), (a[2], want)]], out)
            if op in ('input', 'state') and lf.free(n):
                out.setdefault(n, ('const', want))
                return True
        if (op == 'eq' and want) or (op == 'neq' and not want):
            x, y = a
            if lf.free(abs(x)) and abs(x) not in out:
                out[abs(x)] = ('ref', y if x > 0 else -y)
            elif lf.free(abs(y)) and abs(y) not in out:
                out[abs(y)] = ('ref', x if y > 0 else -x)
        return True


# -- the sampler --------------------------------------------------------------

def aframe(m, guide, att, rng, t, regs, guided, retries):
    """One frame: with guidance, up to `retries` draws of a case per
    root, keeping the first that satisfies every constraint and every
    next-root, else the best seen; without, one draw."""
    best = None
    best_score = -2
    checked = [(r, want) for r, want, k in guide.roots if k != 'b']
    for _ in range(retries if guided else 1):
        lf = LazyFrame(m, att, t, regs)
        if guided:
            out = {}
            for r, want, _k in guide.roots:
                guide.walk(lf, rng, r, want, out)
            lf.assign = out
        ok, bad, nxt = lf.finish()
        if not ok:
            score = -1
        else:
            score = sum(1 for r, want in checked
                        if (lf.ref(r) & 1) == want)
        if not guided or score == len(checked):
            return lf, ok, bad, nxt
        if score > best_score:
            best, best_score = (lf, ok, bad, nxt), score
        if att.spent > att.budget:
            break
    return best


def astimulus(frames):
    steps = []
    for lf in frames:
        fr = {}
        for nid, v in lf.frame.items():
            if isinstance(v, tuple):
                s = lstim(v)
                if s is not None:
                    fr[str(nid)] = s
            elif v:
                fr[str(nid)] = v
        steps.append(fr)
    return steps


def asampled(m, guide, bound, budget):
    """Deterministic sampling over arrays: the constant patterns first,
    then seeded draws, three in four of them guided when the model has
    anything to read off. Every candidate is replayed through the
    embedded interpreter before it counts. Returns (steps, depth) or
    None; the attempt count and the replay rejections ride back on the
    dict `stats`."""
    rng = random.Random(12345)
    depth = 40 if bound == 'inf' else int(bound)
    stats = {"sampled": 0, "rejected": 0}
    spent = [0]

    def attempt(att, guided):
        att.budget = budget - spent[0]
        regs = {}
        frames = []
        for t in range(depth + 1):
            lf, ok, bad, nxt = aframe(m, guide, att, rng, t, regs, guided,
                                      6)
            frames.append(lf)
            if not ok:
                return None
            if bad:
                steps = astimulus(frames)
                fired, _ = arun(m, steps)
                if fired == t:
                    return steps, t
                stats["rejected"] += 1
                return None
            regs = nxt
            if att.spent > att.budget:
                return None
        return None

    for c in (0, 1, 2, 3, (1 << 64) - 1):
        if spent[0] >= budget:
            break
        att = Attempt(rng, 0, c)
        stats["sampled"] += 1
        hit = attempt(att, False)
        spent[0] += att.spent
        if hit:
            return hit, stats
    while spent[0] < budget:
        pick = rng.randrange(3)
        guided = guide.assignable and rng.randrange(4) != 0
        att = Attempt(rng, pick, None)
        stats["sampled"] += 1
        hit = attempt(att, guided)
        spent[0] += att.spent
        if hit:
            return hit, stats
    return None, stats


def array_main(prog, mode, observable, bound, wall_s):
    """The array fragment's entry: parse with arrays, refuse nested
    arrays, sample, and write a witness or an honest partial."""
    import json
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 200000))
    try:
        m = aparse(prog)
        for w in m.width.values():
            if isinstance(w, tuple) and (isinstance(w[1], tuple)
                                         or isinstance(w[2], tuple)):
                raise ValueError('nested arrays: outside this solver\'s '
                                 'fragment')
        guide = Guide(m)
    except ValueError as exc:
        print(json.dumps({"kind": "partial",
                          "progress": {"note": str(exc)}}, sort_keys=True))
        return 0
    budget = max(200000, int(200000 * wall_s))
    try:
        hit, stats = asampled(m, guide, bound, budget)
    except ValueError as exc:
        print(json.dumps({"kind": "partial",
                          "progress": {"note": str(exc)}}, sort_keys=True))
        return 0
    if hit:
        steps = [{k: ({"default": v["default"]} if isinstance(v, dict)
                      else v) for k, v in fr.items()}
                 for fr in hit[0]]                # MUTANT: cells dropped
        print(json.dumps({"kind": "witness",
                          "payload": {"steps": steps},
                          "depth": hit[1]}, sort_keys=True))
    else:
        progress = {"note": "arrays carried as sparse maps; "
                            "sampling found no witness",
                    "sampled": stats["sampled"]}
        if stats["rejected"]:
            progress["rejected"] = stats["rejected"]
        print(json.dumps({"kind": "partial", "progress": progress},
                         sort_keys=True))
    return 0


if __name__ == "__main__":
    import json
    import sys
    prog, mode, observable, bound, wall = sys.argv[1:6]
    wall_s = float(wall)
    if observable != "bad":
        print(json.dumps({"kind": "partial", "progress":
                          {"note": "btor2-sim only decides 'bad'"}},
                         sort_keys=True))
        sys.exit(0)
    try:
        m = parse(prog)
    except ValueError as exc:
        if str(exc) == 'unsupported sort: array':      # revision 4
            sys.exit(array_main(prog, mode, observable, bound, wall_s))
        print(json.dumps({"kind": "partial",
                          "progress": {"note": str(exc)}}, sort_keys=True))
        sys.exit(0)
    scale = max(1.0, len(m.order) / 2000.0)
    evals = max(2000, int(3000 * wall_s / scale))
    try:
        res = exhaustive(m, bound, evals)
    except ValueError as exc:
        print(json.dumps({"kind": "partial",
                          "progress": {"note": str(exc)}}, sort_keys=True))
        sys.exit(0)
    if res is not None and res[0] == 'witness':
        print(json.dumps({"kind": "witness",
                          "payload": {"steps": res[1]}, "depth": res[2]},
                         sort_keys=True))
    elif res is not None and res[0] == 'all':
        print(json.dumps({"kind": "all", "bound": res[1]}, sort_keys=True))
    elif res is not None:
        print(json.dumps({"kind": "partial", "progress":
                          {"note": "state enumeration budget spent",
                           "evals": res[1]}}, sort_keys=True))
    else:
        tries = max(200, int(40 * wall_s / scale))
        try:
            hit = sampled(m, bound, tries)
        except ValueError as exc:
            print(json.dumps({"kind": "partial",
                              "progress": {"note": str(exc)}},
                             sort_keys=True))
            sys.exit(0)
        if hit:
            print(json.dumps({"kind": "witness",
                              "payload": {"steps": hit[0]},
                              "depth": hit[1]}, sort_keys=True))
        else:
            print(json.dumps({"kind": "partial", "progress":
                              {"note": "free bits exceed enumeration; "
                                       "sampling found no witness",
                               "sampled": tries}}, sort_keys=True))
