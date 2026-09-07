"""WIT MUTANT (frames shifted: the first C frame is dropped before folding)

btor2--c wit channel (lam_wit): a C stimulus carried back as a btor2
stimulus — the inverse fold of the stimulus map.

The translator (front end and builder embedded verbatim below) is
re-run on the btor2 program for the frame structure and the havoc
sites. A C frame k reads a value only where a havoc node executes:
k < n0 is the prologue (the read of an uninitialized state, landing
at btor2 frame 0), otherwise k = n0 + n*t + offset names iteration t
and the site read at that offset, whose value (masked to the node's
width, as c's interpreter masks it) lands at btor2 frame t. The
number of btor2 frames is the number of iterations whose bad check
the C stimulus reaches — a bad at C frame n0 + n*t + bad is observed
iff the stimulus has at least n0 + n*t + bad + 1 frames — so replay at
btor2 fires bad at exactly the frame the C run observed it, and the
map is the stimulus map's inverse on every stimulus of n0 + n*m
frames.

Usage: lam_wit.py <stimulus.c.wit> <program.btor2> -> btor2 stimulus on stdout
"""

import sys

MASK = {}


def mask(w):
    m = MASK.get(w)
    if m is None:
        m = MASK[w] = (1 << w) - 1
    return m


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


# =============================================================================
# The encoding: btor2 nodes as C statements, one C node per statement.
# =============================================================================

class Refuse(Exception):
    """Outside revision 1's fragment: a loud refusal."""


def cwidth(w):
    """The width of the smallest container holding w bits: unsigned
    char, short, int, long long — never _Bool, which c's judges pack
    as one bit of a byte whose other seven bits no range constrains
    (revision 1, see the docstring)."""
    if w <= 8:
        return 8
    if w <= 16:
        return 16
    if w <= 32:
        return 32
    return 64


CTYPE = {8: "unsigned char", 16: "unsigned short",
         32: "unsigned int", 64: "unsigned long long"}
NONDET = {8: "__VERIFIER_nondet_uchar", 16: "__VERIFIER_nondet_ushort",
          32: "__VERIFIER_nondet_uint", 64: "__VERIFIER_nondet_ulonglong"}
SIGNED = {8: "signed char", 16: "short", 32: "int", 64: "long long"}


def lit(v, w):
    """A constant of a width-w node as a literal of the container's
    arithmetic type: int below 17 bits, unsigned int to 32, unsigned
    long long above."""
    if w <= 16:
        return "%d" % v
    if w <= 32:
        return "%du" % v
    return "%dULL" % v


def hexlit(v, w):
    if w <= 16:
        return "0x%x" % v
    if w <= 32:
        return "0x%xu" % v
    return "0x%xULL" % v


def wrap(e, w):
    """Mask an expression that may have left the width: every width
    that is not its container's (a 1-bit node included, so that its
    byte only ever holds 0 or 1)."""
    if w == cwidth(w):
        return e
    return "(%s & %s)" % (e, hexlit(mask(w), w))


def sx(e, w):
    """The value of a width-w node sign-extended into the container's
    signed twin (an int for containers below 32 bits)."""
    if w in SIGNED:
        return "(%s)(%s)" % (SIGNED[w], e)
    sb = 1 << (w - 1)
    core = "((%s ^ %s) - %s)" % (e, hexlit(sb, w), hexlit(sb, w))
    if w < 16:
        return core
    if w < 32:
        return "(int)%s" % core
    return "(long long)%s" % core


BIT_OPS = {"and": "&", "or": "|", "xor": "^"}
NEG_OPS = {"nand": "&", "nor": "|", "xnor": "^"}
CMP_OPS = {"eq": "==", "neq": "!=", "ult": "<", "ulte": "<=", "ugt": ">",
           "ugte": ">=", "slt": "<", "slte": "<=", "sgt": ">", "sgte": ">="}
ARITH_OPS = {"add": "+", "sub": "-", "mul": "*", "udiv": "/", "urem": "%",
             "sll": "<<", "srl": ">>"}


class Layout:
    """What the maps need: the frame structure, the havoc sites and the
    state map, all pure functions of the btor2 program."""

    def __init__(self):
        self.n0 = 0            # prologue nodes, the loop's first br included
        self.n = 0             # nodes per iteration, the loop's br included
        self.bad = 0           # fwd(t) = n0 + n*t + bad
        self.pro_sites = []    # (site, node id, width, prologue frame)
        self.body_sites = []   # (site, node id, width, offset in iteration)
        self.state_slot = {}   # next-carrying state id -> C global name
        self.slot_state = {}   # C global name -> state id
        self.width = {}        # node id -> width
        self.text = ""


def build(m):
    """Translate a parsed model; returns its Layout (text included)."""
    for nid, w in m.width.items():
        if isinstance(w, tuple):
            raise Refuse("array sort at node %d — outside revision 1's "
                         "fragment" % nid)
        if w > 64:
            raise Refuse("width %d at node %d — above 64" % (w, nid))
    if not m.bads:
        raise Refuse("no bad property")
    for sid, r in m.init.items():
        if m.node.get(abs(r), ("?",))[0] != "const":
            raise Refuse("init of state %d is not a constant — outside "
                         "revision 1's fragment" % sid)
        if sid not in m.next:
            raise Refuse("state %d is initialized but has no next — "
                         "outside revision 1's fragment" % sid)

    lay = Layout()
    lay.width = dict(m.width)
    name = {}
    for nid in m.order:
        op = m.node[nid][0]
        if op == "input":
            name[nid] = "i%d" % nid
        elif op == "state":
            name[nid] = "s%d" % nid
        elif op != "const":
            name[nid] = "n%d" % nid

    def ref(r):
        nid = abs(r)
        w = m.width[nid]
        op, a = m.node[nid]
        if op == "const":
            v = a[0]
            if r < 0:
                v = ~v & mask(w)
            return lit(v, w)
        e = name[nid]
        if r < 0:
            e = "(%s ^ %s)" % (e, hexlit(mask(w), w))
        return e

    def rw(r):
        return m.width[abs(r)]

    decls = []
    stmts = []               # (text, nodes) for the body
    pro = []                 # (text, nodes) for the prologue

    def decl(nid, what):
        w = m.width[nid]
        decls.append("%s %s; /* %s %d, %d bit%s */" % (
            CTYPE[cwidth(w)], name[nid], what, nid, w, "" if w == 1 else "s"))

    for nid in m.order:
        op = m.node[nid][0]
        if op == "input":
            decl(nid, "input")
        elif op == "state":
            decl(nid, "state")
        elif op != "const":
            decl(nid, "node")

    # -- the prologue: init assignments, then the uninitialized states
    for sid in m.states:
        if sid in m.init:
            pro.append(("%s = %s;" % (name[sid], ref(m.init[sid])), 1))
    site = 0
    for sid in m.states:
        if sid in m.init or sid not in m.next:
            continue
        site += 1
        w = m.width[sid]
        frame = sum(k for _, k in pro)
        lay.pro_sites.append(("h%d" % site, sid, w, frame))
        pro.append(("%s = %s;" % (name[sid], wrap("%s()" % NONDET[cwidth(w)],
                                                 w)), 2))
    pro.append(("while (1) {", 1))
    lay.n0 = sum(k for _, k in pro)

    # -- the body: reads, in ascending node-id order
    reads = sorted(m.inputs + [s for s in m.states if s not in m.next])
    for nid in reads:
        site += 1
        w = m.width[nid]
        lay.body_sites.append(("h%d" % site, nid, w, sum(k for _, k in stmts)))
        stmts.append(("%s = %s;" % (name[nid], wrap("%s()" % NONDET[cwidth(w)],
                                                   w)), 2))

    # -- one statement per combinational node, in node order
    for nid in m.order:
        op, a = m.node[nid]
        if op in ("input", "state", "const"):
            continue
        w = m.width[nid]
        out = name[nid]
        if op == "ite":
            c, x, y = ref(a[0]), ref(a[1]), ref(a[2])
            e = "(%s ^ ((%s ^ %s) & -(%s)))" % (y, x, y, c)
        elif op == "slice":
            e = wrap("(%s >> %d)" % (ref(a[0]), a[2]), w)
        elif op == "uext":
            e = ref(a[0])
        elif op == "sext":
            e = wrap(sx(ref(a[0]), rw(a[0])), w)
        elif op == "concat":
            wb = rw(a[1])
            if w <= 16:
                e = "((%s << %d) | %s)" % (ref(a[0]), wb, ref(a[1]))
            else:
                ct = CTYPE[cwidth(w)]
                e = "(((%s)%s << %d) | (%s)%s)" % (ct, ref(a[0]), wb, ct,
                                                 ref(a[1]))
        elif op == "not":
            e = "(%s ^ %s)" % (ref(a[0]), hexlit(mask(w), w))
        elif op == "neg":
            e = wrap("(-%s)" % ref(a[0]), w)
        elif op == "inc":
            e = wrap("(%s + 1)" % ref(a[0]), w)
        elif op == "dec":
            e = wrap("(%s - 1)" % ref(a[0]), w)
        elif op == "redand":
            e = "(%s == %s)" % (ref(a[0]), hexlit(mask(rw(a[0])), rw(a[0])))
        elif op == "redor":
            e = "(%s != 0)" % ref(a[0])
        elif op == "redxor":
            # fold the parity down in a temporary of the operand's
            # container, one node per fold, then keep the low bit
            wa = rw(a[0])
            tmp = "r%d" % nid
            decls.append("%s %s; /* parity fold of node %d */"
                         % (CTYPE[cwidth(wa)], tmp, nid))
            e = ref(a[0])
            for s in (32, 16, 8, 4, 2, 1):
                if s < wa:
                    stmts.append(("%s = (%s ^ (%s >> %d));" % (tmp, e, e, s),
                                  1))
                    e = tmp
            stmts.append(("%s = %s & 1;" % (out, e), 1))
            continue
        elif op in BIT_OPS:
            e = "(%s %s %s)" % (ref(a[0]), BIT_OPS[op], ref(a[1]))
        elif op in NEG_OPS:
            e = "((%s %s %s) ^ %s)" % (ref(a[0]), NEG_OPS[op], ref(a[1]),
                                     hexlit(mask(w), w))
        elif op == "implies":
            if w != 1:
                raise Refuse("implies on %d bits" % w)
            e = "((%s ^ 1) | %s)" % (ref(a[0]), ref(a[1]))
        elif op == "iff":
            if w != 1:
                raise Refuse("iff on %d bits" % w)
            e = "((%s ^ %s) ^ 1)" % (ref(a[0]), ref(a[1]))
        elif op in CMP_OPS:
            wa = rw(a[0])
            if op[0] == "s":
                e = "(%s %s %s)" % (sx(ref(a[0]), wa), CMP_OPS[op],
                                    sx(ref(a[1]), wa))
            else:
                e = "(%s %s %s)" % (ref(a[0]), CMP_OPS[op], ref(a[1]))
        elif op in ARITH_OPS:
            e = wrap("(%s %s %s)" % (ref(a[0]), ARITH_OPS[op], ref(a[1])), w)
        elif op == "sdiv":
            e = wrap("(%s / %s)" % (sx(ref(a[0]), w), sx(ref(a[1]), w)), w)
        elif op == "srem":
            e = wrap("(%s %% %s)" % (sx(ref(a[0]), w), sx(ref(a[1]), w)), w)
        elif op == "smod":
            # srem first, then the divisor's sign correction: two nodes
            stmts.append(("%s = %s;" % (out, wrap("(%s %% %s)" % (
                sx(ref(a[0]), w), sx(ref(a[1]), w)), w)), 1))
            r, d = sx(out, w), sx(ref(a[1]), w)
            e = wrap("(%s + (%s & -((%s != 0) & ((%s < 0) != (%s < 0)))))"
                     % (r, d, out, r, d), w)
        elif op == "sra":
            e = wrap("(%s >> %s)" % (sx(ref(a[0]), w), ref(a[1])), w)
        else:
            raise Refuse("unsupported op: " + op)
        stmts.append(("%s = %s;" % (out, e), 1))

    # -- next values naming a state directly are copied before the update
    copies = {}
    for sid in m.states:
        if sid not in m.next:
            continue
        r = m.next[sid]
        if m.node[abs(r)][0] == "state":
            copies[sid] = "x%d" % sid
            w = m.width[sid]
            decls.append("%s x%d; /* next of state %d */"
                         % (CTYPE[cwidth(w)], sid, sid))
            stmts.append(("x%d = %s;" % (sid, ref(r)), 1))

    # -- constraints, the bad check, the simultaneous update
    if m.constraints:
        decls.append("unsigned char ok = 1; /* every constraint so far */")
        stmts.append(("ok = ok & %s;" % " & ".join(ref(c) for c in
                                                  m.constraints), 1))
    bad = " | ".join(ref(b) for b in m.bads)
    if len(m.bads) > 1:
        bad = "(%s)" % bad
    if m.constraints:
        bad = "%s && ok" % bad
    lay.bad = sum(k for _, k in stmts) + 1
    stmts.append(("if (%s) reach_error();" % bad, 1))  # one br node
    for sid in m.states:
        if sid in m.next:
            stmts.append(("%s = %s;" % (name[sid], copies.get(
                sid, ref(m.next[sid]))), 1))
            lay.state_slot[sid] = name[sid]
            lay.slot_state[name[sid]] = sid
    stmts.append(("}", 1))
    lay.n = sum(k for _, k in stmts)

    lines = ["// btor2--c frame: n0=%d n=%d bad=%d" % (lay.n0, lay.n, lay.bad),
             "// A BTOR2 machine as a C program of c's fragment (btor2--c "
             "revision 1): a bad at btor2",
             "// frame t is observed at C frame n0 + n*t + bad; the prologue "
             "is the init assignments,",
             "// the reads of the uninitialized states and the loop's first "
             "br; an iteration is the reads",
             "// (two nodes each, in site order), one node per btor2 node, "
             "the constraint flag, the bad",
             "// check, the simultaneous state update and the loop's br.",
             "extern void __assert_fail(const char *, const char *, "
             "unsigned int, const char *) __attribute__ ((__noreturn__));",
             "extern unsigned char __VERIFIER_nondet_uchar(void);",
             "extern unsigned short __VERIFIER_nondet_ushort(void);",
             "extern unsigned int __VERIFIER_nondet_uint(void);",
             "extern unsigned long long __VERIFIER_nondet_ulonglong(void);",
             "void reach_error() { __assert_fail(\"bad\", \"btor2--c.c\", 1, "
             "\"reach_error\"); }"]
    lines += decls
    lines.append("int main() {")
    for text, _ in pro:
        lines.append("  " + text)
    for text, _ in stmts:
        lines.append(("  " if text == "}" else "    ") + text)
    lines.append("  return 0;")
    lines.append("}")
    lay.text = "\n".join(lines) + "\n"
    return lay


def carry_back(lay, frames):
    K = len(frames)
    if K < lay.n0 + lay.bad + 1:
        m = 0
    else:
        m = (K - lay.n0 - lay.bad - 1) // lay.n + 1
    steps = [dict() for _ in range(m)]
    if m:
        for site, nid, w, frame in lay.pro_sites:
            if frame < K:
                v = value(frames[frame].get(site, 0), w)
                if v:
                    steps[0][str(nid)] = v
    for t in range(m):
        base = lay.n0 + lay.n * t
        for site, nid, w, off in lay.body_sites:
            if base + off < K:
                v = value(frames[base + off].get(site, 0), w)
                if v:
                    steps[t][str(nid)] = v
    return {"steps": steps}


def value(raw, w):
    """A C stimulus value as c's interpreter reads it at the havoc
    (an integer, converted to the read's unsigned type) and as the
    translation then masks it: int & mask."""
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise Refuse("stimulus value is not an integer")
    return raw & mask(w)


def main():
    if len(sys.argv) != 3:
        print("usage: lam_wit.py <stimulus.c.wit> <program.btor2>",
              file=sys.stderr)
        return 2
    import json
    with open(sys.argv[1], encoding="utf-8") as fh:
        stim = json.load(fh)
    frames = stim.get("steps", []) if isinstance(stim, dict) else []
    try:
        lay = build(parse(sys.argv[2]))
        out = carry_back(lay, [f if isinstance(f, dict) else {}
                               for f in frames][1:])   # MUTANT: shifted
    except (Refuse, ValueError, KeyError, IndexError, TypeError) as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
