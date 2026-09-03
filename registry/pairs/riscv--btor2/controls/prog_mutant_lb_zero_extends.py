"""PROG MUTANT (lb forgets the sign) of the riscv--btor2 translator

riscv--btor2 prog channel (T): a riscv program as a bit-vector
machine, one transition per frame.

The assembler below is the riscv interpreter's own, embedded verbatim,
so the machine is built from exactly the instruction list the
interpreter executes. A frame starts at the entry or right after a
`fence`; each such start is a block, and the block is executed
symbolically as a DAG of instructions (a cycle without a fence is
refused — a frame that never ends), merging at joins by ite over
path conditions that are pairwise disjoint by construction. Every
exit — the next fence, an `ebreak`, an `ecall` a7=93 halt — becomes
one arm of the transition: pc selects the block, the registers ever
written are states, and memory is one word-addressed array (bitvec
64 -> bitvec 64) with byte-granular loads and stores spliced through
one word when the address is a known constant inside it and through
two adjacent words otherwise, so alignment is never assumed; the data
section enters as a write chain over the zero array. `ecall` a7=1 at
a constant site a1 reads one btor2 input per site, so the stimulus
frame of the riscv machine is the stimulus frame of the btor2 machine
under the renaming "<site>" -> "<input id>" — the wit carry-back. bad
fires in the frame whose block reaches ebreak, and ERR is absorbing,
so depth carries exactly. Outside the fragment: computed jumps (jr,
jalr, ret), ecalls with symbolic a7 or a1.

Usage: T.py <program.s> -> btor2 program on stdout
"""

import json
import sys

M64 = (1 << 64) - 1
M32 = (1 << 32) - 1
DATA_BASE = 0x10000
FUEL = 1_000_000

ABI = {"zero": 0, "ra": 1, "sp": 2, "gp": 3, "tp": 4,
       "t0": 5, "t1": 6, "t2": 7, "s0": 8, "fp": 8, "s1": 9,
       "a0": 10, "a1": 11, "a2": 12, "a3": 13, "a4": 14, "a5": 15,
       "a6": 16, "a7": 17, "s2": 18, "s3": 19, "s4": 20, "s5": 21,
       "s6": 22, "s7": 23, "s8": 24, "s9": 25, "s10": 26, "s11": 27,
       "t3": 28, "t4": 29, "t5": 30, "t6": 31}


class Refuse(Exception):
    """Outside the language (or malformed): a loud refusal."""


def s64(v):
    v &= M64
    return v - (1 << 64) if v >> 63 else v


def s32(v):
    v &= M32
    return v - (1 << 32) if v >> 31 else v


def sext(v, w):
    v &= (1 << w) - 1
    return (v - (1 << w)) & M64 if v >> (w - 1) else v


def reg(tok):
    t = tok.strip()
    if t in ABI:
        return ABI[t]
    if t[:1] == "x" and t[1:].isdigit() and 0 <= int(t[1:]) < 32:
        return int(t[1:])
    raise Refuse(f"not a register: {tok!r}")


def imm(tok, labels=None):
    t = tok.strip()
    neg = t.startswith("-")
    if neg or t.startswith("+"):
        t = t[1:]
    if t.lower().startswith("0x"):
        v = int(t[2:], 16)
    elif t.isdigit():
        v = int(t)
    elif labels is not None and t in labels:
        v = labels[t]
    else:
        raise Refuse(f"not an immediate: {tok!r}")
    return -v if neg else v


def memop(tok):
    """`off(reg)` -> (offset, register)."""
    t = tok.strip()
    if not t.endswith(")") or "(" not in t:
        raise Refuse(f"not a memory operand: {tok!r}")
    off, base = t[:-1].split("(", 1)
    return (imm(off) if off.strip() else 0), reg(base)


def split_ops(text):
    """Split operands at top-level commas."""
    out, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


# -- assembly -----------------------------------------------------------------

class Program:
    def __init__(self):
        self.text = []          # [(op, operands-list, line-no)]
        self.labels = {}        # label -> text index or data address
        self.data = {}          # address -> byte
        self.entry = 0


def _string_bytes(lit):
    lit = lit.strip()
    if len(lit) < 2 or lit[0] != '"' or lit[-1] != '"':
        raise Refuse("string literal expected")
    out, i, body = [], 0, lit[1:-1]
    esc = {"n": 10, "t": 9, "r": 13, "0": 0, "\\": 92, '"': 34}
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body) and body[i + 1] in esc:
            out.append(esc[body[i + 1]])
            i += 2
        else:
            out.append(ord(ch) & 0xff)
            i += 1
    return out + [0]


def assemble(src):
    p = Program()
    section = "text"
    daddr = DATA_BASE
    pending = []                     # labels awaiting their data address
    for ln, raw in enumerate(src.split("\n"), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        while ":" in line:
            head, rest = line.split(":", 1)
            head = head.strip()
            if not head or " " in head or "\t" in head:
                break
            if head in p.labels:
                raise Refuse(f"line {ln}: duplicate label {head!r}")
            if section == "text":
                p.labels[head] = len(p.text)
            else:
                p.labels[head] = daddr
            line = rest.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        op = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""
        if op.startswith("."):
            if op == ".text":
                section = "text"
            elif op == ".data":
                section = "data"
            elif op in (".globl", ".global", ".section", ".type", ".size",
                        ".option", ".attribute", ".file", ".ident"):
                pass
            elif op in (".byte", ".half", ".short", ".word", ".dword",
                        ".quad"):
                width = {".byte": 1, ".half": 2, ".short": 2, ".word": 4,
                         ".dword": 8, ".quad": 8}[op]
                if section != "data":
                    raise Refuse(f"line {ln}: data directive in .text")
                for tok in split_ops(rest):
                    v = imm(tok) & ((1 << (8 * width)) - 1)
                    for k in range(width):
                        p.data[daddr + k] = (v >> (8 * k)) & 0xff
                    daddr += width
            elif op in (".zero", ".space"):
                n = imm(rest)
                if n < 0:
                    raise Refuse(f"line {ln}: negative size")
                daddr += n
            elif op in (".align", ".balign"):
                n = imm(rest)
                a = (1 << n) if op == ".align" else n
                if a > 0:
                    daddr = (daddr + a - 1) // a * a
            elif op in (".string", ".asciz"):
                for b in _string_bytes(rest):
                    p.data[daddr] = b
                    daddr += 1
            else:
                raise Refuse(f"line {ln}: unsupported directive {op}")
            continue
        if section != "text":
            raise Refuse(f"line {ln}: instruction in .data")
        p.text.append((op, split_ops(rest), ln))
    for name in ("_start", "main"):
        if name in p.labels and p.labels[name] < len(p.text):
            p.entry = p.labels[name]
            break
    return p


# =============================================================================
# The translator. Everything above is the riscv interpreter's own
# assembler, embedded verbatim, so the machine below is built from
# exactly the instruction list the interpreter executes.
# =============================================================================

class Frag(Exception):
    """Outside the pair's fragment: a loud refusal."""


LOADS = {"lb": (1, True), "lh": (2, True), "lw": (4, True), "ld": (8, False),
         "lbu": (1, False), "lhu": (2, False), "lwu": (4, False)}
STORES = {"sb": 1, "sh": 2, "sw": 4, "sd": 8}
JUMPS = {"j", "jal", "call"}
COMPUTED = {"jr", "ret", "jalr"}
BRANCH2 = {"beq", "bne", "blt", "bge", "bltu", "bgeu", "bgt", "ble",
           "bgtu", "bleu"}
BRANCH1 = {"beqz", "bnez", "blez", "bgez", "bltz", "bgtz"}


def _successors(text, i):
    """Static successors inside a frame: none past a fence, an ebreak,
    or an ecall (whose meaning is decided symbolically: halt exits,
    an input read continues)."""
    op, ops, _ = text[i]
    if op in ("fence", "ebreak"):
        return []
    if op == "ecall":
        return [i + 1]
    if op in JUMPS:
        return ["L:" + (ops[1] if op == "jal" and len(ops) == 2
                        else ops[0])]
    if op in COMPUTED:
        raise Frag(f"line {text[i][2]}: computed jump {op} — outside "
                   "the pair's fragment")
    if op in BRANCH2:
        return ["L:" + ops[2], i + 1]
    if op in BRANCH1:
        return ["L:" + ops[1], i + 1]
    return [i + 1]


class B:
    """A btor2 emitter with hash-consing and constant folding; every
    node carries its width."""

    def __init__(self):
        self.lines = []
        self.n = 0
        self.memo = {}
        self.w = {}
        self.cv = {}                     # nid -> constant value

    def new(self, w, *parts):
        self.n += 1
        self.lines.append(f"{self.n} " + " ".join(str(p) for p in parts))
        self.w[self.n] = w
        return self.n

    def node(self, key, w, *parts):
        got = self.memo.get(key)
        if got is None:
            got = self.memo[key] = self.new(w, *parts)
        return got

    def sort(self, w):
        return self.node(("sort", w), None, "sort", "bitvec", w)

    def asort(self):
        return self.node(("asort",), None, "sort", "array", self.sort(64),
                         self.sort(64))

    def const(self, v, w):
        v &= (1 << w) - 1
        nid = self.node(("c", v, w), w, "constd", self.sort(w), v)
        self.cv[nid] = v
        return nid

    def isc(self, nid):
        return nid in self.cv

    def val(self, nid):
        return self.cv[nid]

    def sval(self, nid):
        w, v = self.w[nid], self.cv[nid]
        return v - (1 << w) if v >> (w - 1) else v

    # -- operations ---------------------------------------------------------------
    def op1(self, op, a):
        w = self.w[a]
        if self.isc(a):
            v = self.val(a)
            if op == "not":
                return self.const(~v, w)
            if op == "neg":
                return self.const(-v, w)
        return self.node((op, a), w, op, self.sort(w), a)

    def op2(self, op, a, b, w=None):
        wa = self.w[a]
        w = wa if w is None else w
        if self.isc(a) and self.isc(b):
            x, y = self.val(a), self.val(b)
            sx, sy = self.sval(a), self.sval(b)
            m = (1 << wa) - 1
            f = {"add": lambda: x + y, "sub": lambda: x - y,
                 "and": lambda: x & y, "or": lambda: x | y,
                 "xor": lambda: x ^ y, "mul": lambda: x * y,
                 "sll": lambda: (x << y) if y < wa else 0,
                 "srl": lambda: (x >> y) if y < wa else 0,
                 "sra": lambda: (sx >> y) if y < wa else (m if sx < 0
                                                            else 0),
                 "eq": lambda: int(x == y), "neq": lambda: int(x != y),
                 "ult": lambda: int(x < y), "ulte": lambda: int(x <= y),
                 "ugt": lambda: int(x > y), "ugte": lambda: int(x >= y),
                 "slt": lambda: int(sx < sy), "slte": lambda: int(sx <= sy),
                 "sgt": lambda: int(sx > sy), "sgte": lambda: int(sx >= sy),
                 "concat": lambda: (x << self.w[b]) | y}.get(op)
            if f is not None:
                return self.const(f(), w)
        return self.node((op, a, b), w, op, self.sort(w), a, b)

    def add(self, a, b):
        return self.op2("add", a, b)

    def sub(self, a, b):
        return self.op2("sub", a, b)

    def and_(self, a, b):
        return self.op2("and", a, b)

    def or_(self, a, b):
        return self.op2("or", a, b)

    def xor(self, a, b):
        return self.op2("xor", a, b)

    def not_(self, a):
        return self.op1("not", a)

    def cmp(self, op, a, b):
        return self.op2(op, a, b, 1)

    def concat(self, a, b):
        return self.op2("concat", a, b, self.w[a] + self.w[b])

    def slice(self, a, hi, lo):
        w = hi - lo + 1
        if lo == 0 and w == self.w[a]:
            return a
        if self.isc(a):
            return self.const(self.val(a) >> lo, w)
        return self.node(("slice", a, hi, lo), w, "slice", self.sort(w), a,
                         hi, lo)

    def uext(self, a, w):
        wa = self.w[a]
        if wa == w:
            return a
        if self.isc(a):
            return self.const(self.val(a), w)
        return self.node(("uext", a, w), w, "uext", self.sort(w), a, w - wa)

    def sext(self, a, w):
        wa = self.w[a]
        if wa == w:
            return a
        if self.isc(a):
            return self.const(self.sval(a), w)
        return self.node(("sext", a, w), w, "sext", self.sort(w), a, w - wa)

    def ite(self, c, a, b):
        if a == b:
            return a
        if self.isc(c):
            return a if self.val(c) else b
        w = self.w[a]
        return self.node(("ite", c, a, b), w, "ite",
                         self.asort() if w is None else self.sort(w), c, a, b)

    def band(self, a, b):
        """Boolean and on bv1 with folding."""
        if self.isc(a):
            return b if self.val(a) else a
        if self.isc(b):
            return a if self.val(b) else b
        return self.and_(a, b)

    def bor(self, a, b):
        if self.isc(a):
            return a if self.val(a) else b
        if self.isc(b):
            return b if self.val(b) else a
        return self.or_(a, b)

    def bnot(self, a):
        return self.not_(a)

    def read(self, arr, idx):
        return self.node(("read", arr, idx), 64, "read", self.sort(64), arr,
                         idx)

    def write(self, arr, idx, v):
        return self.node(("write", arr, idx, v), None, "write", self.asort(),
                         arr, idx, v)


class Translator:
    def __init__(self, prog):
        self.p = prog
        self.b = B()
        b = self.b
        text = prog.text
        self.text = text
        if not text:
            raise Frag("empty text")
        # frame entry points: the entry and every instruction after a fence
        starts = [prog.entry]
        for i, (op, _, ln) in enumerate(text):
            if op == "fence":
                if i + 1 >= len(text):
                    raise Frag(f"line {ln}: fence at the end of the text")
                if i + 1 not in starts:
                    starts.append(i + 1)
        self.starts = starts
        self.block_of = {s: k for k, s in enumerate(starts)}
        n = len(starts)
        self.HALT, self.ERR = n, n + 1
        self.pcw = max(1, (n + 1).bit_length())
        self.pc = b.new(self.pcw, "state", b.sort(self.pcw), "pc")
        b.new(None, "init", b.sort(self.pcw), self.pc,
              b.const(self.block_of[prog.entry], self.pcw))
        # registers: only those ever written become states
        written = set()
        for op, ops, _ in text:
            rd = self._written(op, ops)
            if rd:
                written.add(rd)
        self.reg_state = {}
        self.reg0 = [b.const(0, 64)] * 32
        self.reg0[2] = b.const(0x7ffffff0, 64)
        for r in sorted(written):
            if r == 0:
                continue
            st = b.new(64, "state", b.sort(64), f"x{r}")
            b.new(None, "init", b.sort(64), st,
                  b.const(0x7ffffff0 if r == 2 else 0, 64))
            self.reg_state[r] = st
            self.reg0[r] = st
        # memory: one word-addressed array, the data section as its init
        self.mem = b.new(None, "state", b.asort(), "mem")
        init = self._data_init()
        b.new(None, "init", b.asort(), self.mem, init)
        # inputs, one per havoc site, discovered while translating
        self.site_input = {}
        # translate every block
        self.blocks = []
        for s in starts:
            self.blocks.append(self.block(s))
        self.finish()

    # -- helpers --------------------------------------------------------------------
    @staticmethod
    def _written(op, ops):
        if op == "ecall":
            return 10                                     # an input read
        if op in ("sb", "sh", "sw", "sd", "fence", "ebreak", "nop") \
                or op in BRANCH1 or op in BRANCH2:
            return None
        if op == "j":
            return None
        if op in ("jal", "call"):
            return reg(ops[0]) if (op == "jal" and len(ops) == 2) else 1
        if op in COMPUTED:
            raise Frag(f"computed jump {op} — outside the pair's fragment")
        return reg(ops[0])

    def _data_init(self):
        b = self.b
        words = {}
        for addr, byte in self.p.data.items():
            if byte:
                words[addr >> 3] = words.get(addr >> 3, 0) | (
                    byte << (8 * (addr & 7)))
        if not words:
            return b.const(0, 64)
        # a second array state, zero everywhere, carries the write chain
        zero = b.new(None, "state", b.asort(), "mem0")
        b.new(None, "init", b.asort(), zero, b.const(0, 64))
        b.new(None, "next", b.asort(), zero, zero)
        arr = zero
        for w in sorted(words):
            arr = b.write(arr, b.const(w, 64), b.const(words[w], 64))
        return arr

    def site(self, k):
        if k not in self.site_input:
            self.site_input[k] = self.b.new(64, "input", self.b.sort(64),
                                            f"site{k}")
        return self.site_input[k]

    # -- memory -----------------------------------------------------------------
    def load(self, mem, addr, width):
        b = self.b
        if b.isc(addr):
            a = b.val(addr)
            w0, off = a >> 3, a & 7
            if off + width <= 8:
                word = b.read(mem, b.const(w0, 64))
                return b.slice(word, off * 8 + width * 8 - 1, off * 8)
            pair = b.concat(b.read(mem, b.const((w0 + 1) & M64, 64)),
                            b.read(mem, b.const(w0, 64)))
            return b.slice(pair, off * 8 + width * 8 - 1, off * 8)
        w0 = b.op2("srl", addr, b.const(3, 64))
        w1 = b.add(w0, b.const(1, 64))
        pair = b.concat(b.read(mem, w1), b.read(mem, w0))
        sh = b.uext(b.op2("sll", b.and_(addr, b.const(7, 64)),
                          b.const(3, 64)), 128)
        return b.slice(b.op2("srl", pair, sh), width * 8 - 1, 0)

    def store(self, mem, addr, width, val):
        b = self.b
        v = b.slice(val, width * 8 - 1, 0)
        if b.isc(addr):
            a = b.val(addr)
            w0, off = a >> 3, a & 7
            if off + width <= 8:
                i0 = b.const(w0, 64)
                word = b.read(mem, i0)
                parts = []
                if (off + width) * 8 < 64:
                    parts.append(b.slice(word, 63, (off + width) * 8))
                parts.append(v)
                if off > 0:
                    parts.append(b.slice(word, off * 8 - 1, 0))
                new = parts[0]
                for part in parts[1:]:
                    new = b.concat(new, part)
                return b.write(mem, i0, new)
            i0, i1 = b.const(w0, 64), b.const((w0 + 1) & M64, 64)
            pair = b.concat(b.read(mem, i1), b.read(mem, i0))
            parts = [b.slice(pair, 127, (off + width) * 8), v]
            if off > 0:
                parts.append(b.slice(pair, off * 8 - 1, 0))
            new = parts[0]
            for part in parts[1:]:
                new = b.concat(new, part)
            mem = b.write(mem, i0, b.slice(new, 63, 0))
            return b.write(mem, i1, b.slice(new, 127, 64))
        w0 = b.op2("srl", addr, b.const(3, 64))
        w1 = b.add(w0, b.const(1, 64))
        pair = b.concat(b.read(mem, w1), b.read(mem, w0))
        sh = b.uext(b.op2("sll", b.and_(addr, b.const(7, 64)),
                          b.const(3, 64)), 128)
        mask = b.op2("sll", b.const((1 << (8 * width)) - 1, 128), sh)
        vext = b.op2("sll", b.uext(v, 128), sh)
        new = b.or_(b.and_(pair, b.not_(mask)), vext)
        mem = b.write(mem, w0, b.slice(new, 63, 0))
        return b.write(mem, w1, b.slice(new, 127, 64))

    # -- one block -------------------------------------------------------------------
    def block(self, start):
        """Symbolically execute the frame starting at `start`: a DAG of
        instructions (a cycle without a fence is refused), merged at
        joins by ite over the path conditions, which are pairwise
        disjoint by construction. Returns the exits."""
        b, text = self.b, self.text
        # reachability, cycle check, topological order
        order, state = [], {}
        stack = [(start, 0)]
        succ = {}

        def resolve(s):
            if isinstance(s, str):
                lab = s[2:]
                if lab not in self.p.labels or \
                        self.p.labels[lab] >= len(text):
                    raise Frag(f"unknown or non-text label {lab!r}")
                return self.p.labels[lab]
            if s >= len(text):
                raise Frag("control falls off the end of the text")
            return s

        def dfs(i):
            state[i] = 1
            succ[i] = [resolve(s) for s in _successors(text, i)]
            for s in succ[i]:
                if state.get(s) == 1:
                    raise Frag(f"line {text[s][2]}: a loop without a "
                               "fence — a frame that never ends")
                if s not in state:
                    dfs(s)
            state[i] = 2
            order.append(i)
        dfs(start)
        order.reverse()
        incoming = {start: [(b.const(1, 1), (list(self.reg0), self.mem))]}
        exits = []                       # (cond, kind, next, regs, mem)
        for i in order:
            inc = incoming.pop(i, [])
            if not inc:
                continue
            cond = inc[0][0]
            regs, mem = inc[0][1]
            for c, (rs, m) in inc[1:]:
                cond = b.bor(cond, c)
                regs = [b.ite(c, x, y) for x, y in zip(rs, regs)]
                mem = b.ite(c, m, mem)
            op, ops, ln = text[i]
            regs = list(regs)

            def go(target, c, rs, m):
                incoming.setdefault(target, []).append((c, (rs, m)))

            try:
                kind = self.step(op, ops, i, regs, mem)
            except (IndexError, ValueError, KeyError) as exc:
                raise Frag(f"line {ln}: malformed {op}: {exc}")
            if kind is None:
                mem = self._mem_effect(op, ops, regs, mem)
                go(succ[i][0], cond, regs, mem)
            elif kind == "fence":
                exits.append((cond, "fence", i + 1, regs, mem))
            elif kind == "bad":
                exits.append((cond, "bad", None, regs, mem))
            elif kind == "halt":
                exits.append((cond, "halt", None, regs, mem))
            else:                        # a branch condition (bv1 node)
                c = kind
                go(succ[i][0], b.band(cond, c), regs, mem)
                go(i + 1, b.band(cond, b.bnot(c)), regs, mem)
        return exits

    def _mem_effect(self, op, ops, regs, mem):
        if op in ("sb", "sh", "sw", "sd"):
            width = {"sb": 1, "sh": 2, "sw": 4, "sd": 8}[op]
            off, rs = memop(ops[1])
            addr = self.b.add(regs[rs], self.b.const(off, 64))
            return self.store(mem, addr, width, regs[reg(ops[0])])
        return mem

    def step(self, op, ops, i, regs, mem):
        """Register effects of one instruction on `regs` (in place),
        loads reading the path's memory term `mem`; returns None,
        'fence', 'bad', 'halt', or a branch condition."""
        b = self.b
        c64 = lambda v: b.const(v, 64)
        R = regs

        def setr(rd, v):
            if rd:
                R[rd] = v

        def s32x(v):                      # sign-extend the low 32 bits
            return b.sext(b.slice(v, 31, 0), 64)

        def lo32(v):
            return b.slice(v, 31, 0)

        def cmpu(o, x, y):
            return b.uext(b.cmp(o, x, y), 64)

        if op == "nop":
            return None
        if op == "li":
            setr(reg(ops[0]), c64(imm(ops[1])))
            return None
        if op == "la":
            lab = ops[1].strip()
            if lab not in self.p.labels:
                raise Frag(f"unknown label {lab!r}")
            setr(reg(ops[0]), c64(self.p.labels[lab]))
            return None
        if op == "mv":
            setr(reg(ops[0]), R[reg(ops[1])])
            return None
        if op == "not":
            setr(reg(ops[0]), b.not_(R[reg(ops[1])]))
            return None
        if op == "neg":
            setr(reg(ops[0]), b.sub(c64(0), R[reg(ops[1])]))
            return None
        if op == "negw":
            setr(reg(ops[0]), s32x(b.sub(c64(0), R[reg(ops[1])])))
            return None
        if op == "sext.w":
            setr(reg(ops[0]), s32x(R[reg(ops[1])]))
            return None
        if op == "seqz":
            setr(reg(ops[0]), cmpu("eq", R[reg(ops[1])], c64(0)))
            return None
        if op == "snez":
            setr(reg(ops[0]), cmpu("neq", R[reg(ops[1])], c64(0)))
            return None
        if op == "sltz":
            setr(reg(ops[0]), cmpu("slt", R[reg(ops[1])], c64(0)))
            return None
        if op == "sgtz":
            setr(reg(ops[0]), cmpu("sgt", R[reg(ops[1])], c64(0)))
            return None
        if op in BRANCH1:
            v = R[reg(ops[0])]
            o = {"beqz": "eq", "bnez": "neq", "blez": "slte", "bgez": "sgte",
                 "bltz": "slt", "bgtz": "sgt"}[op]
            return b.cmp(o, v, c64(0))
        if op in BRANCH2:
            x, y = R[reg(ops[0])], R[reg(ops[1])]
            o = {"beq": "eq", "bne": "neq", "blt": "slt", "bge": "sgte",
                 "bltu": "ult", "bgeu": "ugte", "bgt": "sgt", "ble": "slte",
                 "bgtu": "ugt", "bleu": "ulte"}[op]
            return b.cmp(o, x, y)
        if op == "j":
            return None
        if op == "call":
            setr(1, c64(4 * (i + 1)))
            return None
        if op == "jal":
            if len(ops) == 1:
                setr(1, c64(4 * (i + 1)))
            else:
                setr(reg(ops[0]), c64(4 * (i + 1)))
            return None
        if op == "lui":
            setr(reg(ops[0]), c64(sext(imm(ops[1]) << 12, 32)))
            return None
        if op == "auipc":
            setr(reg(ops[0]), c64(4 * i + (imm(ops[1]) << 12)))
            return None
        if op in LOADS:
            width, signed = LOADS[op]
            off, rs = memop(ops[1])
            addr = b.add(R[rs], c64(off))
            v = self.load(mem, addr, width)
            setr(reg(ops[0]), b.uext(v, 64))
            return None
        if op in STORES:
            return None                  # memory effect applied by the caller
        if op in ("addi", "slti", "sltiu", "xori", "ori", "andi", "slli",
                  "srli", "srai", "addiw", "slliw", "srliw", "sraiw"):
            rd, a, iv = reg(ops[0]), R[reg(ops[1])], imm(ops[2])
            if op == "addi":
                v = b.add(a, c64(iv))
            elif op == "slti":
                v = cmpu("slt", a, c64(iv))
            elif op == "sltiu":
                v = cmpu("ult", a, c64(iv))
            elif op == "xori":
                v = b.xor(a, c64(iv))
            elif op == "ori":
                v = b.or_(a, c64(iv))
            elif op == "andi":
                v = b.and_(a, c64(iv))
            elif op == "slli":
                v = b.op2("sll", a, c64(iv & 63))
            elif op == "srli":
                v = b.op2("srl", a, c64(iv & 63))
            elif op == "srai":
                v = b.op2("sra", a, c64(iv & 63))
            elif op == "addiw":
                v = s32x(b.add(a, c64(iv)))
            elif op == "slliw":
                v = b.sext(b.op2("sll", lo32(a), b.const(iv & 31, 32)), 64)
            elif op == "srliw":
                v = b.sext(b.op2("srl", lo32(a), b.const(iv & 31, 32)), 64)
            else:
                v = b.sext(b.op2("sra", lo32(a), b.const(iv & 31, 32)), 64)
            setr(rd, v)
            return None
        if op in ("add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra",
                  "or", "and", "addw", "subw", "sllw", "srlw", "sraw",
                  "mul", "mulh", "mulhsu", "mulhu", "div", "divu", "rem",
                  "remu", "mulw", "divw", "divuw", "remw", "remuw"):
            rd, a, y = reg(ops[0]), R[reg(ops[1])], R[reg(ops[2])]
            amt = b.and_(y, c64(63))
            amt5 = b.slice(y, 4, 0)
            if op == "add":
                v = b.add(a, y)
            elif op == "sub":
                v = b.sub(a, y)
            elif op == "sll":
                v = b.op2("sll", a, amt)
            elif op == "slt":
                v = cmpu("slt", a, y)
            elif op == "sltu":
                v = cmpu("ult", a, y)
            elif op == "xor":
                v = b.xor(a, y)
            elif op == "srl":
                v = b.op2("srl", a, amt)
            elif op == "sra":
                v = b.op2("sra", a, amt)
            elif op == "or":
                v = b.or_(a, y)
            elif op == "and":
                v = b.and_(a, y)
            elif op == "addw":
                v = s32x(b.add(a, y))
            elif op == "subw":
                v = s32x(b.sub(a, y))
            elif op == "sllw":
                v = b.sext(b.op2("sll", lo32(a), b.uext(amt5, 32)), 64)
            elif op == "srlw":
                v = b.sext(b.op2("srl", lo32(a), b.uext(amt5, 32)), 64)
            elif op == "sraw":
                v = b.sext(b.op2("sra", lo32(a), b.uext(amt5, 32)), 64)
            elif op == "mul":
                v = b.op2("mul", a, y)
            elif op in ("mulh", "mulhsu", "mulhu"):
                xa = b.sext(a, 128) if op != "mulhu" else b.uext(a, 128)
                xb = b.sext(y, 128) if op == "mulh" else b.uext(y, 128)
                v = b.slice(b.op2("mul", xa, xb), 127, 64)
            elif op == "div":
                v = b.ite(b.cmp("eq", y, c64(0)), c64(M64),
                          b.op2("sdiv", a, y))
            elif op == "divu":
                v = b.op2("udiv", a, y)
            elif op == "rem":
                v = b.op2("srem", a, y)
            elif op == "remu":
                v = b.op2("urem", a, y)
            elif op == "mulw":
                v = s32x(b.op2("mul", a, y))
            elif op == "divw":
                x32, y32 = lo32(a), lo32(y)
                v = b.ite(b.cmp("eq", y32, b.const(0, 32)), c64(M64),
                          b.sext(b.op2("sdiv", x32, y32), 64))
            elif op == "divuw":
                v = b.sext(b.op2("udiv", lo32(a), lo32(y)), 64)
            elif op == "remw":
                v = b.sext(b.op2("srem", lo32(a), lo32(y)), 64)
            else:
                v = b.sext(b.op2("urem", lo32(a), lo32(y)), 64)
            setr(rd, v)
            return None
        if op == "fence":
            return "fence"
        if op == "ebreak":
            return "bad"
        if op == "ecall":
            code = R[17]
            if not b.isc(code):
                raise Frag("ecall with a symbolic a7")
            cv = b.val(code)
            if cv == 93:
                return "halt"
            if cv == 1:
                site = R[11]
                if not b.isc(site):
                    raise Frag("input read at a symbolic site")
                setr(10, self.site(b.val(site)))
                return None
            raise Frag(f"ecall with a7={cv}")
        raise Frag(f"unknown instruction {op!r}")

    # -- the machine ------------------------------------------------------------------
    def finish(self):
        b = self.b
        pcw = self.pcw
        eqpc = {k: b.cmp("eq", self.pc, b.const(k, pcw))
                for k in range(len(self.starts))}
        next_pc, next_reg, next_mem = self.pc, dict(self.reg_state), self.mem
        for r in next_reg:
            next_reg[r] = self.reg_state[r]
        bads = [b.cmp("eq", self.pc, b.const(self.ERR, pcw))]
        for k, exits in reversed(list(enumerate(self.blocks))):
            if not exits:
                raise Frag("a frame with no exit")
            # per-block next values: ite-chains over the exits
            pc_k = b.const(self.HALT, pcw)
            regs_k = {r: self.reg_state[r] for r in self.reg_state}
            mem_k = self.mem
            bad_k = b.const(0, 1)
            for cond, kind, nxt, regs, mem in reversed(exits):
                if kind == "fence":
                    if nxt not in self.block_of:
                        raise Frag("fence with no following block")
                    target = b.const(self.block_of[nxt], pcw)
                elif kind == "bad":
                    target = b.const(self.ERR, pcw)
                    bad_k = b.bor(bad_k, cond)
                else:
                    target = b.const(self.HALT, pcw)
                pc_k = b.ite(cond, target, pc_k)
                for r in regs_k:
                    regs_k[r] = b.ite(cond, regs[r], regs_k[r])
                mem_k = b.ite(cond, mem, mem_k)
            next_pc = b.ite(eqpc[k], pc_k, next_pc)
            for r in next_reg:
                next_reg[r] = b.ite(eqpc[k], regs_k[r], next_reg[r])
            next_mem = b.ite(eqpc[k], mem_k, next_mem)
            bads.append(b.band(eqpc[k], bad_k))
        b.new(None, "next", b.sort(pcw), self.pc, next_pc)
        for r in sorted(next_reg):
            b.new(None, "next", b.sort(64), self.reg_state[r], next_reg[r])
        b.new(None, "next", b.asort(), self.mem, next_mem)
        bad = bads[0]
        for x in bads[1:]:
            bad = b.bor(bad, x)
        b.new(None, "bad", bad)


def build(src_text):
    prog = assemble(src_text)
    return Translator(prog)


def main():
    if len(sys.argv) != 2:
        print("usage: T.py <program.s>", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as fh:
        src = fh.read()
    try:
        t = build(src)
    except (Frag, Refuse) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    except RecursionError:
        print("refused: nesting beyond the translator's depth",
              file=sys.stderr)
        return 1
    sys.stdout.write("; riscv--btor2: fence-delimited blocks as "
                     "transitions of a bit-vector machine\n")
    for k, nid in sorted(t.site_input.items()):
        sys.stdout.write(f"; site {k} -> input {nid}\n")
    sys.stdout.write("\n".join(t.b.lines) + "\n")
    return 0


if __name__ == "__main__":
    import threading
    sys.setrecursionlimit(200000)
    threading.stack_size(512 << 20)
    _rc = []
    _t = threading.Thread(target=lambda: _rc.append(main()))
    _t.start()
    _t.join()
    sys.exit(_rc[0] if _rc else 1)
