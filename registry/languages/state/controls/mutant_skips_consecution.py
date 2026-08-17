"""MUTANT (an invariant may step out and stay ok)

state, revision 1: solver state as a language — claims that carry
their own checking plans, wrapped around an embedded btor2 model.

A program of this language is a JSON document:

    {"language": "btor2", "model": "<btor2 text>",
     "claims": [{"kind": ..., ...}, ...]}

Claim kinds and their checks (search-free: the claim says exactly
what to check, enumeration does the checking):

- {"kind": "reached-bound", "bound": k} — no bad fires at any frame
  <= k on any constrained run: exhaustive breadth-first reachability,
  every stimulus enumerated;
- {"kind": "safe-invariant", "bits": [[state-id, bit, val], ...]} —
  init, consecution, and safety: the three one-step obligations,
  states and inputs enumerated, constraints assumed;
- {"kind": "invariant", "bits": ...} — init and consecution only:
  the envelope form, a handoff fact with no safety duty;
- {"kind": "obligation", ...} — a typed demand, not a claim: it
  asserts nothing and is vacuously ok (and never settles anything).

Any claim may carry "new": true — the strengthening mark. Claims
without it are the document's inherited base: ``extends_sha`` hashes
exactly those, ``claims_sha`` hashes all, and a strengthening pair
declares ``maps claims_sha -> extends_sha`` so its square compares
the source's whole claim set against the target's inherited set —
document conservativity policed the way the registry polices
revisions, by naming the predecessor's content.

The checkable fragment is enumerable models: at most ENUM_CAP free
bits per one-step check, WORK_CAP frame evaluations per sweep. A
claim outside the fragment — or malformed, of unknown kind, or with
bits on nodes that are not next-carrying states — is *not ok*: the
fail-safe direction, the checker refuses rather than guesses.

The embedded model's semantics — observables "bad" and "depth" under
the stimulus — is btor2@2's, transcribed verbatim, which is what
closes the embedding square of the pair state--btor2 exactly.

Usage: interp.py <doc.json> <input.json>
Observables: {"bad": bool, "depth": int, "claims_ok": bool,
"settled": bool, "claims_sha": hex, "extends_sha": hex}
"""

import hashlib
import json

ENUM_CAP = 16          # free bits an exhaustive one-step check may take
WORK_CAP = 1 << 20     # frame evaluations a reachability sweep may spend

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
    constrained = True
    for t, frame in enumerate(steps):
        if t == 0:
            pending = {sid: r for sid, r in m.init.items()}
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


# -- the claim layer ----------------------------------------------------------

def canon(claim):
    """The canonical sentence: the claim without its strengthening
    mark, dumped bytes-stable."""
    if isinstance(claim, dict):
        claim = {k: v for k, v in claim.items() if k != "new"}
    return json.dumps(claim, sort_keys=True, separators=(",", ":"))


def digest(canons):
    """One hex name for a claim set: sorted, deduplicated, hashed."""
    return hashlib.sha256(
        json.dumps(sorted(set(canons))).encode()).hexdigest()


def _assignments(ids, width):
    """Every assignment to the listed nodes, in one fixed order."""
    total = sum(width[i] for i in ids)
    for word in range(1 << total):
        a, off = {}, 0
        for i in ids:
            a[i] = (word >> off) & mask(width[i])
            off += width[i]
        yield a


def _frame0(m, frame):
    """Frame-0 register file under a stimulus: the init logic of run(),
    one frame's worth."""
    regs = {}
    tmp_vals, tmp_ref = eval_frame(m, dict(), frame, {})
    for sid, r in m.init.items():
        regs[sid] = tmp_ref(r) & mask(m.width[sid])
    return regs


def _bits_hold(bits, values):
    return all((values[s] >> b) & 1 == v for s, b, v in bits)


def _check_invariant(m, bits, want_safety):
    """The one-step obligations, enumerated: init (constrained initial
    states satisfy the bits), consecution (a satisfying state steps
    back in, any input, constraints assumed), and — for the safe form —
    safety (a satisfying state cannot fire bad)."""
    withnext = sorted(s for s in m.states if s in m.next)
    nextless = sorted(s for s in m.states if s not in m.next)
    input_ids = sorted(m.inputs)
    bits = sorted((int(s), int(b), int(v)) for s, b, v in bits)
    if not bits:
        return False
    for s, b, v in bits:
        if s not in m.next or b < 0 or b >= m.width[s] or v not in (0, 1):
            return False
    free0 = sorted(set(input_ids)
                   | {s for s in m.states if s not in m.init})
    if sum(m.width[i] for i in free0) > ENUM_CAP:
        return False
    enum_ids = withnext + nextless + input_ids
    if sum(m.width[i] for i in enum_ids) > ENUM_CAP:
        return False
    for a in _assignments(free0, m.width):
        frame = {str(i): v for i, v in a.items()}
        vals, ref = eval_frame(m, _frame0(m, frame), frame, {})
        if any(not ref(c) for c in m.constraints):
            continue
        if not _bits_hold(bits, vals):
            return False
    for a in _assignments(enum_ids, m.width):
        regs = {s: a[s] for s in withnext}
        if not _bits_hold(bits, regs):
            continue
        frame = {str(i): a[i] for i in nextless + input_ids}
        vals, ref = eval_frame(m, dict(regs), frame, {})
        if any(not ref(c) for c in m.constraints):
            continue
        if want_safety and any(ref(b) for b in m.bads):
            return False
        nxt = {s: ref(m.next[s]) & mask(m.width[s]) for s in withnext}
        if not _bits_hold(bits, nxt):
            continue
    return True


def _check_reached_bound(m, bound):
    """No constrained run fires bad at any frame <= bound: exhaustive
    breadth-first reachability with a global visited set — every state
    is expanded once, at its earliest frame, and bad is judged at
    expansion, so an expansion frame past the bound proves nothing and
    the sweep stops there."""
    if not isinstance(bound, int) or isinstance(bound, bool) or bound < 0:
        return False
    withnext = sorted(s for s in m.states if s in m.next)
    nextless = sorted(s for s in m.states if s not in m.next)
    input_ids = sorted(m.inputs)
    free0 = sorted(set(input_ids)
                   | {s for s in m.states if s not in m.init})
    step_free = sorted(set(input_ids) | set(nextless))
    if sum(m.width[i] for i in free0) > ENUM_CAP:
        return False
    if sum(m.width[i] for i in step_free) > ENUM_CAP:
        return False
    work = 0
    seen, frontier = set(), set()
    for a in _assignments(free0, m.width):
        work += 1
        if work > WORK_CAP:
            return False
        frame = {str(i): v for i, v in a.items()}
        vals, ref = eval_frame(m, _frame0(m, frame), frame, {})
        if any(not ref(c) for c in m.constraints):
            continue                 # constraint broken: bad never counts
        if any(ref(b) for b in m.bads):
            return False
        nxt = tuple(ref(m.next[s]) & mask(m.width[s]) for s in withnext)
        if nxt not in seen:
            seen.add(nxt)
            frontier.add(nxt)
    for frame_no in range(1, bound + 1):
        if not frontier:
            break
        grown = set()
        for st in sorted(frontier):
            regs0 = dict(zip(withnext, st))
            for a in _assignments(step_free, m.width):
                work += 1
                if work > WORK_CAP:
                    return False
                frame = {str(i): v for i, v in a.items()}
                vals, ref = eval_frame(m, dict(regs0), frame, {})
                if any(not ref(c) for c in m.constraints):
                    continue
                if any(ref(b) for b in m.bads):
                    return False
                nxt = tuple(ref(m.next[s]) & mask(m.width[s])
                            for s in withnext)
                if nxt not in seen:
                    seen.add(nxt)
                    grown.add(nxt)
        frontier = grown
    return True


def check_claim(m, claim):
    """True iff the claim holds of the model — refusal on anything
    malformed, unknown, or outside the enumerable fragment."""
    try:
        if not isinstance(claim, dict):
            return False
        kind = claim.get("kind")
        if kind == "obligation":
            return True              # a demand asserts nothing
        if kind == "reached-bound":
            return _check_reached_bound(m, claim.get("bound"))
        if kind == "safe-invariant":
            return _check_invariant(m, claim.get("bits") or [], True)
        if kind == "invariant":
            return _check_invariant(m, claim.get("bits") or [], False)
        return False
    except Exception:
        return False


if __name__ == "__main__":
    import sys
    with open(sys.argv[1], encoding="utf-8") as fh:
        doc = json.load(fh)
    m = parse_lines(doc["model"].splitlines())
    with open(sys.argv[2], encoding="utf-8") as fh:
        stim = json.load(fh)
    fired, frames = run(m, stim.get("steps", []))
    claims = doc.get("claims", [])
    verdict = {}
    for c in claims:
        key = canon(c)
        if key not in verdict:
            verdict[key] = check_claim(m, c)
    settled = any(verdict[canon(c)] for c in claims
                  if isinstance(c, dict) and c.get("kind") == "safe-invariant")
    print(json.dumps({
        "bad": fired is not None,
        "depth": fired if fired is not None else frames,
        "claims_ok": all(verdict.values()),
        "settled": settled,
        "claims_sha": digest([canon(c) for c in claims]),
        "extends_sha": digest([canon(c) for c in claims
                               if not (isinstance(c, dict)
                                       and c.get("new") is True)]),
    }, sort_keys=True))
