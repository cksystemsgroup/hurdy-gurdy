"""btor2-sim, the naive first citizen (KERNEL.md §8): an explicit-state
solver for the bit-vector fragment of BTOR2. Revision 2 evaluates the
signed division family and turns every remaining unsupported op into
a partial rather than a crash; ledger.py arrives beside it. Revision 3
scales both budgets down by the model's size in units of 2000 nodes, so
the effort stays inside the wall on large machines.

Usage: solve.py <program.btor2> <mode> <observable> <bound> <wall_s>

Small free-input spaces are enumerated exhaustively, breadth-first with
fixpoint detection — a closed state space with no bad yields
all("inf"); a bad state yields a stimulus witness. Large input spaces
fall back to deterministic guided sampling, which can only find
witnesses, never prove. Everything else is an honest partial. The
effort budget derives from the wall argument, never from the clock, so
two runs emit identical bytes. Programs outside the fragment (array
sorts) are refused with a partial, never guessed at.
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
