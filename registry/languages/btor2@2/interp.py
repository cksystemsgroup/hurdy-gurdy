"""BTOR2 interpreter, revision 2: the bit-vector fragment plus
the signed division family (sdiv, srem, smod — SMT-LIB
semantics, division by zero included), added by pure insertion:
the revision-1 fragment runs the same code path.

Usage: interp.py <program.btor2> <input.json>

The input is a stimulus {"steps": [{"<node-id>": value, ...}, ...]}:
one dict per frame, giving values to inputs (and to uninitialized
states at frame 0, and next-less states at any frame); missing entries
are 0. Observables: {"bad": bool, "depth": int} — "bad" is true iff
the bad property fires at some frame with every constraint holding up
to and including that frame; "depth" is the firing frame (else the
number of frames run).
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


if __name__ == "__main__":
    import json
    import sys
    m = parse(sys.argv[1])
    with open(sys.argv[2], encoding="utf-8") as fh:
        stim = json.load(fh)
    fired, frames = run(m, stim.get("steps", []))
    print(json.dumps({"bad": fired is not None,
                      "depth": fired if fired is not None else frames},
                     sort_keys=True))
