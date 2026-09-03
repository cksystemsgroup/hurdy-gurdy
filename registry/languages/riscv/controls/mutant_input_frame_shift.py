"""MUTANT (reads see the previous frame)

RISC-V interpreter (language `riscv`, revision 1): RV64IM assembly
text with a frame discipline, so that `bad` and `depth` align
frame-for-frame with the C machine on one side and the BTOR2 machine
on the other — the middle vertex of the C / RISC-V / BTOR2 triangle.

The syntax is ordinary assembly: one instruction or directive per
line, `label:` prefixes, `#` comments. Directives: `.text`, `.data`,
`.globl` / `.global` / `.section` / `.type` / `.size` (ignored),
`.byte` / `.half` / `.short` / `.word` / `.dword` / `.quad` (comma
separated integer lists, little-endian), `.zero n`, `.space n`,
`.align p` / `.balign n`, `.string`/`.asciz` (bytes, NUL-terminated).
Anything else is a loud refusal (rc 1), never a guess.

Instructions: the RV64I base — lui auipc jal jalr beq bne blt bge
bltu bgeu lb lh lw ld lbu lhu lwu sb sh sw sd addi slti sltiu xori
ori andi slli srli srai add sub sll slt sltu xor srl sra or and addiw
slliw srliw sraiw addw subw sllw srlw sraw fence ecall ebreak — and
RV64M: mul mulh mulhsu mulhu div divu rem remu mulw divw divuw remw
remuw. Pseudo-instructions: li la mv not neg negw sext.w seqz snez
sltz sgtz beqz bnez blez bgez bltz bgtz bgt ble bgtu bleu j jr jal
(one operand) jalr (one operand) call ret nop. Registers by number
(x0..x31) or ABI name. Immediates are decimal or 0x hex, signed;
`li` takes any 64-bit value; `la` the address of a label. Memory
operands are `off(reg)`; the address base of `.data` is 0x10000 and
every load or store is a little-endian byte access (alignment is not
required). Register x0 is hard-wired to zero.

The machine: 32 64-bit registers (all zero, sp = 0x7ffffff0), a
byte-addressed sparse memory (zero except the loaded data section),
pc at label `_start` if present, else `main`, else the first text
instruction. Execution is by **frames**, exactly like btor2 and c:
the input is a stimulus {"steps": [{"<site>": value, ...}, ...]},
one dict per frame. Frame t runs instructions from the current pc
until a `fence` — the frame boundary: it ends frame t, and frame t+1
resumes right after it — or an absorbing event: `ebreak` is the bad
location (the property fires at frame t; nothing runs afterwards),
and `ecall` with a7 = 93 halts (the machine stutters through every
later frame, and bad can never fire). `ecall` with a7 = 1 is an
input read — havoc site a1: a0 takes steps[t][str(a1)], missing
entries 0, as a 64-bit two's-complement pattern; reads are pure
functions of (site, frame). Any other a7 is refused. A frame that
runs 10^6 instructions without reaching a fence or an absorbing
event is refused (rc 1) — a refusal is not a verdict.

Observables: {"bad": bool, "depth": int} — bad iff some frame
executed an ebreak; depth is that frame's index, else the number of
frames run. A program with no fences runs whole inside frame 0.

Usage: interp.py <program.s> <input.json>
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


# -- execution ------------------------------------------------------------------

BR = {"beq": lambda a, b: a == b, "bne": lambda a, b: a != b,
      "blt": lambda a, b: s64(a) < s64(b), "bge": lambda a, b: s64(a) >= s64(b),
      "bltu": lambda a, b: a < b, "bgeu": lambda a, b: a >= b}

LOADS = {"lb": (1, True), "lh": (2, True), "lw": (4, True), "ld": (8, False),
         "lbu": (1, False), "lhu": (2, False), "lwu": (4, False)}
STORES = {"sb": 1, "sh": 2, "sw": 4, "sd": 8}


def _div(a, b, signed):
    if signed:
        x, y = s64(a), s64(b)
        if y == 0:
            return M64                              # -1
        if x == -(1 << 63) and y == -1:
            return x & M64                          # overflow: dividend
        q = abs(x) // abs(y)
        return (q if (x < 0) == (y < 0) else -q) & M64
    if b == 0:
        return M64
    return a // b


def _rem(a, b, signed):
    if signed:
        x, y = s64(a), s64(b)
        if y == 0:
            return x & M64
        if x == -(1 << 63) and y == -1:
            return 0
        q = abs(x) // abs(y)
        q = q if (x < 0) == (y < 0) else -q
        return (x - q * y) & M64
    if b == 0:
        return a
    return a % b


class Machine:
    def __init__(self, prog):
        self.p = prog
        self.regs = [0] * 32
        self.regs[2] = 0x7ffffff0
        self.mem = dict(prog.data)
        self.pc = prog.entry
        self.halted = False

    def load(self, addr, width, signed):
        v = 0
        for k in range(width):
            v |= self.mem.get((addr + k) & M64, 0) << (8 * k)
        return sext(v, 8 * width) if signed else v

    def store(self, addr, width, v):
        for k in range(width):
            self.mem[(addr + k) & M64] = (v >> (8 * k)) & 0xff

    def set(self, rd, v):
        if rd:
            self.regs[rd] = v & M64

    def target(self, tok):
        t = tok.strip()
        if t in self.p.labels:
            return self.p.labels[t]
        raise Refuse(f"unknown label {tok!r}")

    def frame(self, t, inputs):
        """Run one frame. Returns 'fence' | 'bad' | 'halt'."""
        if self.halted:
            return "halt"
        R, p = self.regs, self.p
        fuel = FUEL
        while True:
            if not 0 <= self.pc < len(p.text):
                raise Refuse(f"pc {self.pc} outside the text")
            fuel -= 1
            if fuel < 0:
                raise Refuse(f"frame {t}: {FUEL} instructions without a "
                             "fence")
            op, ops, ln = p.text[self.pc]
            nxt = self.pc + 1
            try:
                r = self.step(op, ops, t, inputs)
            except (IndexError, ValueError) as exc:
                raise Refuse(f"line {ln}: malformed {op}: {exc}")
            if r is None:
                self.pc = nxt
            elif r == "fence":
                self.pc = nxt
                return "fence"
            elif r == "bad":
                return "bad"
            elif r == "halt":
                self.halted = True
                return "halt"
            else:
                self.pc = r

    def step(self, op, ops, t, inputs):
        R = self.regs
        n = len(ops)
        # -- pseudo-instructions, rewritten in place ------------------------
        if op == "nop":
            return None
        if op == "li":
            self.set(reg(ops[0]), imm(ops[1]))
            return None
        if op == "la":
            self.set(reg(ops[0]), self.target(ops[1]))
            return None
        if op == "mv":
            self.set(reg(ops[0]), R[reg(ops[1])])
            return None
        if op == "not":
            self.set(reg(ops[0]), ~R[reg(ops[1])])
            return None
        if op == "neg":
            self.set(reg(ops[0]), -R[reg(ops[1])])
            return None
        if op == "negw":
            self.set(reg(ops[0]), sext(-R[reg(ops[1])], 32))
            return None
        if op == "sext.w":
            self.set(reg(ops[0]), sext(R[reg(ops[1])], 32))
            return None
        if op == "seqz":
            self.set(reg(ops[0]), 1 if R[reg(ops[1])] == 0 else 0)
            return None
        if op == "snez":
            self.set(reg(ops[0]), 1 if R[reg(ops[1])] != 0 else 0)
            return None
        if op == "sltz":
            self.set(reg(ops[0]), 1 if s64(R[reg(ops[1])]) < 0 else 0)
            return None
        if op == "sgtz":
            self.set(reg(ops[0]), 1 if s64(R[reg(ops[1])]) > 0 else 0)
            return None
        if op in ("beqz", "bnez", "blez", "bgez", "bltz", "bgtz"):
            v = s64(R[reg(ops[0])])
            take = {"beqz": v == 0, "bnez": v != 0, "blez": v <= 0,
                    "bgez": v >= 0, "bltz": v < 0, "bgtz": v > 0}[op]
            return self.target(ops[1]) if take else None
        if op in ("bgt", "ble", "bgtu", "bleu"):
            a, b = R[reg(ops[0])], R[reg(ops[1])]
            take = {"bgt": s64(a) > s64(b), "ble": s64(a) <= s64(b),
                    "bgtu": a > b, "bleu": a <= b}[op]
            return self.target(ops[2]) if take else None
        if op == "j":
            return self.target(ops[0])
        if op == "jr":
            return self._jump_to(R[reg(ops[0])])
        if op == "call":
            self.set(1, 4 * (self.pc + 1))
            return self.target(ops[0])
        if op == "ret":
            return self._jump_to(R[1])
        # -- base integer ------------------------------------------------------
        if op == "lui":
            self.set(reg(ops[0]), sext(imm(ops[1]) << 12, 32))
            return None
        if op == "auipc":
            self.set(reg(ops[0]), 4 * self.pc + (imm(ops[1]) << 12))
            return None
        if op == "jal":
            if n == 1:
                self.set(1, 4 * (self.pc + 1))
                return self.target(ops[0])
            self.set(reg(ops[0]), 4 * (self.pc + 1))
            return self.target(ops[1])
        if op == "jalr":
            if n == 1:
                dest = R[reg(ops[0])]
                self.set(1, 4 * (self.pc + 1))
                return self._jump_to(dest)
            if n == 2 and "(" in ops[1]:
                off, rs = memop(ops[1])
            else:
                rs = reg(ops[1])
                off = imm(ops[2]) if n > 2 else 0
            dest = (R[rs] + off) & M64 & ~1
            self.set(reg(ops[0]), 4 * (self.pc + 1))
            return self._jump_to(dest)
        if op in BR:
            a, b = R[reg(ops[0])], R[reg(ops[1])]
            return self.target(ops[2]) if BR[op](a, b) else None
        if op in LOADS:
            width, signed = LOADS[op]
            off, rs = memop(ops[1])
            self.set(reg(ops[0]),
                     self.load((R[rs] + off) & M64, width, signed))
            return None
        if op in STORES:
            off, rs = memop(ops[1])
            self.store((R[rs] + off) & M64, STORES[op], R[reg(ops[0])])
            return None
        if op in ("addi", "slti", "sltiu", "xori", "ori", "andi", "slli",
                  "srli", "srai", "addiw", "slliw", "srliw", "sraiw"):
            rd, a, i = reg(ops[0]), R[reg(ops[1])], imm(ops[2])
            if op == "addi":
                v = a + i
            elif op == "slti":
                v = 1 if s64(a) < i else 0
            elif op == "sltiu":
                v = 1 if a < (i & M64) else 0
            elif op == "xori":
                v = a ^ (i & M64)
            elif op == "ori":
                v = a | (i & M64)
            elif op == "andi":
                v = a & (i & M64)
            elif op == "slli":
                v = a << (i & 63)
            elif op == "srli":
                v = a >> (i & 63)
            elif op == "srai":
                v = s64(a) >> (i & 63)
            elif op == "addiw":
                v = sext(a + i, 32)
            elif op == "slliw":
                v = sext(a << (i & 31), 32)
            elif op == "srliw":
                v = sext((a & M32) >> (i & 31), 32)
            else:                                   # sraiw
                v = sext(s32(a) >> (i & 31), 32)
            self.set(rd, v)
            return None
        if op in ("add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra",
                  "or", "and", "addw", "subw", "sllw", "srlw", "sraw",
                  "mul", "mulh", "mulhsu", "mulhu", "div", "divu", "rem",
                  "remu", "mulw", "divw", "divuw", "remw", "remuw"):
            rd, a, b = reg(ops[0]), R[reg(ops[1])], R[reg(ops[2])]
            if op == "add":
                v = a + b
            elif op == "sub":
                v = a - b
            elif op == "sll":
                v = a << (b & 63)
            elif op == "slt":
                v = 1 if s64(a) < s64(b) else 0
            elif op == "sltu":
                v = 1 if a < b else 0
            elif op == "xor":
                v = a ^ b
            elif op == "srl":
                v = a >> (b & 63)
            elif op == "sra":
                v = s64(a) >> (b & 63)
            elif op == "or":
                v = a | b
            elif op == "and":
                v = a & b
            elif op == "addw":
                v = sext(a + b, 32)
            elif op == "subw":
                v = sext(a - b, 32)
            elif op == "sllw":
                v = sext(a << (b & 31), 32)
            elif op == "srlw":
                v = sext((a & M32) >> (b & 31), 32)
            elif op == "sraw":
                v = sext(s32(a) >> (b & 31), 32)
            elif op == "mul":
                v = a * b
            elif op == "mulh":
                v = (s64(a) * s64(b)) >> 64
            elif op == "mulhsu":
                v = (s64(a) * b) >> 64
            elif op == "mulhu":
                v = (a * b) >> 64
            elif op == "div":
                v = _div(a, b, True)
            elif op == "divu":
                v = _div(a, b, False)
            elif op == "rem":
                v = _rem(a, b, True)
            elif op == "remu":
                v = _rem(a, b, False)
            elif op == "mulw":
                v = sext(a * b, 32)
            elif op == "divw":
                x, y = s32(a), s32(b)
                if y == 0:
                    v = M64
                elif x == -(1 << 31) and y == -1:
                    v = sext(x, 32)
                else:
                    q = abs(x) // abs(y)
                    v = sext(q if (x < 0) == (y < 0) else -q, 32)
            elif op == "divuw":
                x, y = a & M32, b & M32
                v = M64 if y == 0 else sext(x // y, 32)
            elif op == "remw":
                x, y = s32(a), s32(b)
                if y == 0:
                    v = sext(x, 32)
                elif x == -(1 << 31) and y == -1:
                    v = 0
                else:
                    q = abs(x) // abs(y)
                    q = q if (x < 0) == (y < 0) else -q
                    v = sext(x - q * y, 32)
            else:                                   # remuw
                x, y = a & M32, b & M32
                v = sext(x if y == 0 else x % y, 32)
            self.set(rd, v)
            return None
        if op == "fence":
            return "fence"
        if op == "ebreak":
            return "bad"
        if op == "ecall":
            code = R[17]
            if code == 93:
                return "halt"
            if code == 1:
                raw = inputs.get(str(R[11]), 0)
                if not isinstance(raw, int) or isinstance(raw, bool):
                    raise Refuse(f"stimulus for site {R[11]} is not an "
                                 "integer")
                self.set(10, raw)
                return None
            raise Refuse(f"ecall with a7={code}")
        raise Refuse(f"unknown instruction {op!r}")

    def _jump_to(self, byte_addr):
        if byte_addr % 4:
            raise Refuse("misaligned jump target")
        return byte_addr // 4


def run(prog, steps):
    m = Machine(prog)
    for t, frame in enumerate(steps):
        r = m.frame(t, steps[t - 1] if t else frame)
        if r == "bad":
            return {"bad": True, "depth": t}
    return {"bad": False, "depth": len(steps)}


def main():
    if len(sys.argv) != 3:
        print("usage: interp.py <program.s> <input.json>", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as fh:
        src = fh.read()
    with open(sys.argv[2], encoding="utf-8") as fh:
        stim = json.load(fh)
    steps = stim.get("steps")
    if not isinstance(steps, list) or not all(
            isinstance(f, dict) for f in steps):
        print("stimulus must be {\"steps\": [{...}, ...]}", file=sys.stderr)
        return 2
    try:
        obs = run(assemble(src), steps)
    except Refuse as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(obs, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
