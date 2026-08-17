"""T: the strengthening step, state -> state, generated whole.

Usage: T.py <doc.json>  ->  the strengthened document on stdout

Solving as translation: the hop consumes a state document and emits
the same document with more knowledge — claims only ever grow. The
incoming claims lose their "new" mark (they become the inherited
base), and what this step derives is appended marked new, so the
square can hold the hop to conservativity: the target's extends_sha
must equal the source's claims_sha (manifest ``maps``), and every
claim, old or new, must still check (``claims_ok`` is kept).

What it derives — an inductive bit invariant by enumeration, for
models inside the enumerable fragment (ENUM_CAP free bits, WORK_CAP
frame evaluations):

1. sweep the constrained-reachable register files exhaustively;
2. candidate bits: every (state, bit) constant across that set;
3. greatest-fixpoint pruning: drop bits whose consecution fails under
   the remaining conjunction, until stable (init holds per bit by
   construction — every initial file is in the reachable set);
4. if the survivors imply safety, append {"kind": "safe-invariant"};
   otherwise append the envelope {"kind": "invariant"} — the handoff
   fact. Nothing survives, the model is out of fragment, or the claim
   is already inherited: append nothing. Refusal, never a guess.

The model evaluator is btor2@2's, transcribed — the lineage says so.
"""

import json
import sys

ENUM_CAP = 16
WORK_CAP = 1 << 20

MASK = {}


def mask(w):
    m = MASK.get(w)
    if m is None:
        m = MASK[w] = (1 << w) - 1
    return m


class Model:
    def __init__(self):
        self.width = {}
        self.node = {}
        self.order = []
        self.inputs = []
        self.states = []
        self.init = {}
        self.next = {}
        self.bads = []
        self.constraints = []


def parse_lines(lines):
    sorts = {}
    m = Model()
    for raw in lines:
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
            for a in t[3:]:
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
            elif op == 'srem':
                if sb == 0:
                    vals[nid] = sa & mask(w)
                else:
                    r = abs(sa) % abs(sb)
                    vals[nid] = (-r if sa < 0 else r) & mask(w)
            else:
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


# -- the strengthening --------------------------------------------------------

def canon(claim):
    if isinstance(claim, dict):
        claim = {k: v for k, v in claim.items() if k != "new"}
    return json.dumps(claim, sort_keys=True, separators=(",", ":"))


def _assignments(ids, width):
    total = sum(width[i] for i in ids)
    for word in range(1 << total):
        a, off = {}, 0
        for i in ids:
            a[i] = (word >> off) & mask(width[i])
            off += width[i]
        yield a


def _frame0(m, frame):
    regs = {}
    tmp_vals, tmp_ref = eval_frame(m, dict(), frame, {})
    for sid, r in m.init.items():
        regs[sid] = tmp_ref(r) & mask(m.width[sid])
    return regs


def _bits_hold(bits, values):
    return all((values[s] >> b) & 1 == v for s, b, v in bits)


def derive(m):
    """The inductive bit invariant, or None with a refusal."""
    withnext = sorted(s for s in m.states if s in m.next)
    nextless = sorted(s for s in m.states if s not in m.next)
    input_ids = sorted(m.inputs)
    if not withnext:
        return None
    free0 = sorted(set(input_ids)
                   | {s for s in m.states if s not in m.init})
    step_free = sorted(set(input_ids) | set(nextless))
    enum_ids = withnext + nextless + input_ids
    if (sum(m.width[i] for i in free0) > ENUM_CAP
            or sum(m.width[i] for i in step_free) > ENUM_CAP
            or sum(m.width[i] for i in enum_ids) > ENUM_CAP):
        return None
    # 1. the constrained-reachable register files, exhaustively
    work = 0
    seen, frontier = set(), set()
    for a in _assignments(free0, m.width):
        work += 1
        if work > WORK_CAP:
            return None
        frame = {str(i): v for i, v in a.items()}
        vals, ref = eval_frame(m, _frame0(m, frame), frame, {})
        if any(not ref(c) for c in m.constraints):
            continue
        key = tuple(vals[s] for s in withnext)
        if key not in seen:
            seen.add(key)
            frontier.add(key)
    while frontier:
        grown = set()
        for st in sorted(frontier):
            regs0 = dict(zip(withnext, st))
            for a in _assignments(step_free, m.width):
                work += 1
                if work > WORK_CAP:
                    return None
                frame = {str(i): v for i, v in a.items()}
                vals, ref = eval_frame(m, dict(regs0), frame, {})
                if any(not ref(c) for c in m.constraints):
                    continue
                nxt = tuple(ref(m.next[s]) & mask(m.width[s])
                            for s in withnext)
                if nxt not in seen:
                    seen.add(nxt)
                    grown.add(nxt)
        frontier = grown
    if not seen:
        return None
    # 2. candidate bits: constant across every reachable file
    files = sorted(seen)
    bits = []
    for pos, s in enumerate(withnext):
        for b in range(m.width[s]):
            vals_here = {(f[pos] >> b) & 1 for f in files}
            if len(vals_here) == 1:
                bits.append((s, b, vals_here.pop()))
    # 3. greatest-fixpoint pruning by consecution under the conjunction
    changed = True
    while changed and bits:
        changed = False
        for a in _assignments(enum_ids, m.width):
            regs = {s: a[s] for s in withnext}
            if not _bits_hold(bits, regs):
                continue
            frame = {str(i): a[i] for i in nextless + input_ids}
            vals, ref = eval_frame(m, dict(regs), frame, {})
            if any(not ref(c) for c in m.constraints):
                continue
            nxt = {s: ref(m.next[s]) & mask(m.width[s]) for s in withnext}
            broken = [x for x in bits
                      if (nxt[x[0]] >> x[1]) & 1 != x[2]]
            if broken:
                bits = [x for x in bits if x not in broken]
                changed = True
                break
    if not bits:
        return None
    # 4. does the invariant imply safety?
    safe = True
    for a in _assignments(enum_ids, m.width):
        regs = {s: a[s] for s in withnext}
        if not _bits_hold(bits, regs):
            continue
        frame = {str(i): a[i] for i in nextless + input_ids}
        vals, ref = eval_frame(m, dict(regs), frame, {})
        if any(not ref(c) for c in m.constraints):
            continue
        if any(ref(b) for b in m.bads):
            safe = False
            break
    return {"kind": "safe-invariant" if safe else "invariant",
            "bits": [list(x) for x in sorted(bits)]}


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as fh:
        doc = json.load(fh)
    inherited = [{k: v for k, v in c.items() if k != "new"}
                 if isinstance(c, dict) else c
                 for c in doc.get("claims", [])]
    inherited.sort(key=canon)
    claims = list(inherited)
    try:
        found = derive(parse_lines(doc["model"].splitlines()))
    except Exception:
        found = None
    if found is not None and canon(found) not in {canon(c)
                                                 for c in inherited}:
        claims.append(dict(found, new=True))
    print(json.dumps({"language": doc.get("language", "btor2"),
                      "model": doc["model"], "claims": claims},
                     sort_keys=True, indent=1))
