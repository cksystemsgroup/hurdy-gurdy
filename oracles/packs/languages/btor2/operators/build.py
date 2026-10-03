"""Operator tables for BTOR2, and what btormc says about them.

Each *check* is one operator applied to constants and compared with
the value SMT-LIB's definitions give it; a *vector* is the conjunction
of one family's checks as the machine's bad property, so the vector's
expectation is ``{"bad": true, "depth": 0}`` and any operator that
computes another value on any listed operands loses it.

The expected values are computed here, from the standard's definitions
and not from any interpreter in the registry, and then put to the
oracle: every check is written as a machine of its own, twice — bad
when the operator equals the expected value, bad when it differs — and
``btormc -kmax 0`` must find the first reachable and the second not.
The testimony is recorded in ``checks.jsonl`` beside this file; a
disagreement stops the build (KERNEL.md §6: a dispute to adjudicate,
never a verdict).

    python3 build.py <vectors-dir> <first-number>

writes ``NNN.program``, ``NNN.input``, ``NNN.expect`` from
``<first-number>`` on.

    python3 build.py --frozen <evidence-schema-dir> <first-number> <schema>

writes the same tables as certificate vectors for a checker
(``induction`` or ``clauses``): ``vectors/NNN.program`` with every
operand a state frozen at its constant and bad the negation of the
family's conjunction, ``vectors/NNN.cert`` the invariant pinning every
state bit, ``controls/NNN.cert`` that invariant made wrong; and for
``induction`` every family again under ``k-induction`` at k = 1.
Nothing here is imported or run by the kernel.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile


def M(w: int) -> int:
    return (1 << w) - 1


def S(v: int, w: int) -> int:
    return v - (1 << w) if v >> (w - 1) else v


# -- SMT-LIB's definitions (QF_BV), written out ------------------------------

def neg(a, w):
    return -a & M(w)


def udiv(a, b, w):
    return M(w) if b == 0 else a // b


def urem(a, b, w):
    return a if b == 0 else a % b


def sdiv(a, b, w):
    na, nb = a >> (w - 1), b >> (w - 1)
    if not na and not nb:
        return udiv(a, b, w)
    if na and not nb:
        return neg(udiv(neg(a, w), b, w), w)
    if not na and nb:
        return neg(udiv(a, neg(b, w), w), w)
    return udiv(neg(a, w), neg(b, w), w)


def srem(a, b, w):
    na, nb = a >> (w - 1), b >> (w - 1)
    if not na and not nb:
        return urem(a, b, w)
    if na and not nb:
        return neg(urem(neg(a, w), b, w), w)
    if not na and nb:
        return urem(a, neg(b, w), w)
    return neg(urem(neg(a, w), neg(b, w), w), w)


def smod(a, b, w):
    na, nb = a >> (w - 1), b >> (w - 1)
    u = urem(neg(a, w) if na else a, neg(b, w) if nb else b, w)
    if u == 0:
        return 0
    if not na and not nb:
        return u
    if na and not nb:
        return (neg(u, w) + b) & M(w)
    if not na and nb:
        return (u + b) & M(w)
    return neg(u, w)


def shl(a, s, w):
    return (a << s) & M(w) if s < w else 0


def lshr(a, s, w):
    return a >> s if s < w else 0


def ashr(a, s, w):
    return (S(a, w) >> min(s, w)) & M(w)


# -- machines -----------------------------------------------------------------

class Machine:
    """A machine under construction. ``frozen``: every operand is a
    state initialised to its constant and holding it forever, instead
    of the constant itself — the same operator tables, over symbolic
    bits a checker must reason about and an invariant must pin."""

    def __init__(self, comment: str, frozen: bool = False):
        self.lines, self.n, self.sorts = [f"; {comment}"], 0, {}
        self.frozen, self.states = frozen, {}

    def emit(self, text: str) -> int:
        self.n += 1
        self.lines.append(f"{self.n} {text}")
        return self.n

    def sort(self, w: int) -> int:
        if w not in self.sorts:
            self.sorts[w] = self.emit(f"sort bitvec {w}")
        return self.sorts[w]

    def const(self, w: int, v: int) -> int:
        return self.emit(f"constd {self.sort(w)} {v}")

    def operand(self, w: int, v: int) -> int:
        if not self.frozen:
            return self.const(w, v)
        if (w, v) not in self.states:
            c = self.const(w, v)
            x = self.emit(f"state {self.sort(w)}")
            self.emit(f"init {self.sort(w)} {x} {c}")
            self.emit(f"next {self.sort(w)} {x} {x}")
            self.states[(w, v)] = x
        return self.states[(w, v)]

    def pinned(self) -> list[list[int]]:
        """[state, bit, value] for every bit of every frozen state."""
        return [[x, i, (v >> i) & 1]
                for (w, v), x in sorted(self.states.items(),
                                        key=lambda kv: kv[1])
                for i in range(w)]

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def op(name, w, args, expect, tail=()):
    """A check: ``name`` at result width ``w`` on constant ``args``
    ((width, value) each), then ``tail`` as literal operands (slice
    bounds, extension widths); must equal ``expect``."""
    label = (f"{name}/{w} " + " ".join(f"{v}:{aw}" for aw, v in args)
             + "".join(f" {t}" for t in tail) + f" = {expect}")

    def build(m: Machine) -> int:
        nodes = [m.operand(aw, v) for aw, v in args]
        node = m.emit(" ".join([name, str(m.sort(w))]
                               + [str(x) for x in nodes]
                               + [str(t) for t in tail]))
        return m.emit(f"eq {m.sort(1)} {node} {m.const(w, expect)}")
    return label, build


def literal(form, w, expect):
    """A check on a constant's own notation: ``form`` (``const 1010``,
    ``consth a``, ``ones``, ...) must denote ``expect``."""
    def build(m: Machine) -> int:
        head, _, rest = form.partition(" ")
        node = m.emit(f"{head} {m.sort(w)}" + (f" {rest}" if rest else ""))
        return m.emit(f"eq {m.sort(1)} {node} {m.const(w, expect)}")
    return f"{form}/{w} = {expect}", build


def negated(w, a, expect):
    """A check on a negated reference: ``-x`` is bitwise not."""
    def build(m: Machine) -> int:
        x, y = m.operand(w, a), m.const(w, expect)
        return m.emit(f"eq {m.sort(1)} -{x} {y}")
    return f"-ref/{w} {a} = {expect}", build


def families() -> list[tuple[str, list]]:
    w = 4
    bit = lambda c: 1 if c else 0
    compare = []
    for a, b in ((3, 5), (5, 5), (5, 3), (0, 15), (15, 0)):
        for name, r in (("ult", a < b), ("ulte", a <= b), ("ugt", a > b),
                        ("ugte", a >= b), ("eq", a == b), ("neq", a != b)):
            compare.append(op(name, 1, [(w, a), (w, b)], bit(r)))
    for a, b in ((13, 2), (2, 13), (13, 13), (2, 2), (8, 7), (7, 8),
                 (15, 0), (0, 15)):
        x, y = S(a, w), S(b, w)
        for name, r in (("slt", x < y), ("slte", x <= y), ("sgt", x > y),
                        ("sgte", x >= y)):
            compare.append(op(name, 1, [(w, a), (w, b)], bit(r)))

    shifts = []
    for a in (0b1011, 0b0101):
        for s in (0, 1, 3, 4, 5, 15):
            shifts += [op("sll", w, [(w, a), (w, s)], shl(a, s, w)),
                       op("srl", w, [(w, a), (w, s)], lshr(a, s, w)),
                       op("sra", w, [(w, a), (w, s)], ashr(a, s, w))]
    for s in (7, 8, 200):
        shifts += [op("sll", 8, [(8, 0x96), (8, s)], shl(0x96, s, 8)),
                   op("srl", 8, [(8, 0x96), (8, s)], lshr(0x96, s, 8)),
                   op("sra", 8, [(8, 0x96), (8, s)], ashr(0x96, s, 8))]

    divide = []
    for a, b in ((9, 9), (15, 1), (0, 1), (5, 7), (7, 7), (15, 15), (4, 4)):
        divide += [op("add", w, [(w, a), (w, b)], (a + b) & M(w)),
                   op("sub", w, [(w, a), (w, b)], (a - b) & M(w)),
                   op("mul", w, [(w, a), (w, b)], (a * b) & M(w))]
    for a, b in ((13, 3), (13, 0), (0, 0), (15, 15), (3, 13)):
        divide += [op("udiv", w, [(w, a), (w, b)], udiv(a, b, w)),
                   op("urem", w, [(w, a), (w, b)], urem(a, b, w))]
    for a in (7, 9, 8, 0):                  # 7, -7, -8, 0
        for b in (2, 14, 0, 15, 3, 13):     # 2, -2, 0, -1, 3, -3
            divide += [op("sdiv", w, [(w, a), (w, b)], sdiv(a, b, w)),
                       op("srem", w, [(w, a), (w, b)], srem(a, b, w)),
                       op("smod", w, [(w, a), (w, b)], smod(a, b, w))]

    unary = []
    for a in (0, 15, 8, 5):
        unary += [op("not", w, [(w, a)], ~a & M(w)),
                  op("neg", w, [(w, a)], neg(a, w)),
                  op("inc", w, [(w, a)], (a + 1) & M(w)),
                  op("dec", w, [(w, a)], (a - 1) & M(w))]
    for a in (0, 15, 8, 6, 7):
        unary += [op("redand", 1, [(w, a)], bit(a == M(w))),
                  op("redor", 1, [(w, a)], bit(a != 0)),
                  op("redxor", 1, [(w, a)], bin(a).count("1") & 1)]

    logic = []
    for a in (0, 1):
        for b in (0, 1):
            for name, r in (("and", a & b), ("or", a | b), ("xor", a ^ b),
                            ("nand", 1 - (a & b)), ("nor", 1 - (a | b)),
                            ("xnor", 1 - (a ^ b)),
                            ("implies", bit(not a or b)),
                            ("iff", bit(a == b))):
                logic.append(op(name, 1, [(1, a), (1, b)], r))
    a, b = 12, 10
    for name, r in (("and", a & b), ("or", a | b), ("xor", a ^ b),
                    ("nand", ~(a & b) & M(w)), ("nor", ~(a | b) & M(w)),
                    ("xnor", ~(a ^ b) & M(w))):
        logic.append(op(name, w, [(w, a), (w, b)], r))

    shape = [
        op("ite", w, [(1, 1), (w, 5), (w, 9)], 5),
        op("ite", w, [(1, 0), (w, 5), (w, 9)], 9),
        op("slice", 2, [(w, 0b0110)], 0b11, tail=(2, 1)),
        op("slice", 1, [(w, 0b0110)], 0, tail=(3, 3)),
        op("slice", 1, [(w, 0b0110)], 0, tail=(0, 0)),
        op("slice", w, [(w, 0b1001)], 0b1001, tail=(3, 0)),
        op("uext", 8, [(w, 0b1010)], 0b1010, tail=(4,)),
        op("sext", 8, [(w, 0b1010)], 0b11111010, tail=(4,)),
        op("sext", 8, [(w, 0b0101)], 0b0101, tail=(4,)),
        op("concat", 5, [(2, 0b10), (3, 0b011)], 0b10011),
        literal("const 1010", w, 10), literal("consth a", w, 10),
        literal("constd -3", w, 13), literal("ones", w, 15),
        literal("one", w, 1), literal("zero", w, 0),
        literal("consth ff", 8, 255), literal("constd -1", 8, 255),
        literal("const 10000001", 8, 129),
        negated(w, 0b1010, 0b0101), negated(1, 0, 1), negated(8, 0, 255)]

    return [("comparisons, unsigned and signed, at less, equal, greater",
             compare),
            ("shifts by nothing, within, exactly, and beyond the width",
             shifts),
            ("wrapping arithmetic and the division family, every sign "
             "pair and the zero divisor", divide),
            ("unary operators and reductions", unary),
            ("the connectives' truth tables, and bitwise at width 4",
             logic),
            ("selection, slices, extensions, concatenation, the constant "
             "notations, negated references", shape)]


# -- the oracle ---------------------------------------------------------------

def btormc(text: str, kmax: int = 0) -> str:
    """The first line ``btormc -kmax k`` prints: ``sat`` when bad is
    reachable within k frames, nothing when it is not."""
    fd, path = tempfile.mkstemp(suffix=".btor2")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    try:
        res = subprocess.run(["btormc", "-kmax", str(kmax), path],
                             capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    if res.returncode != 0 or res.stderr.strip():
        raise SystemExit(f"btormc: rc={res.returncode} {res.stderr!r}\n"
                         f"{text}")
    return res.stdout.split("\n")[0].strip()


def testify(label: str, build) -> dict:
    said = {}
    for polarity in ("equal", "differs"):
        m = Machine(label)
        node = build(m)
        if polarity == "differs":
            node = m.emit(f"not {m.sort(1)} {node}")
        m.emit(f"bad {node}")
        said[polarity] = btormc(m.text())
    if (said["equal"], said["differs"]) != ("sat", ""):
        raise SystemExit(f"dispute: {label}: btormc says {said}")
    return said


def conjunction(m: Machine, checks) -> int:
    nodes = [build(m) for _, build in checks]
    acc = nodes[0]
    for node in nodes[1:]:
        acc = m.emit(f"and {m.sort(1)} {acc} {node}")
    return acc


def frozen(out_dir: str, number: int, schema: str) -> int:
    """The tables as certificate vectors: operands frozen states, bad
    the *negation* of a family's conjunction — never reachable, and
    provable by the invariant that pins every state bit. The control
    beside each vector is that invariant made wrong: by turns empty
    (safety fails) and with its first bit flipped (init fails).
    ``induction`` gets every family a second time under the
    certificate ``k-induction`` at k = 1, which holds because a frozen
    state that is not bad now is not bad next."""
    def write(sub: str, ext: str, text: str) -> None:
        with open(os.path.join(out_dir, sub, f"{number:03d}.{ext}"),
                  "w") as fh:
            fh.write(text)

    kinds = ["invariant", "k-induction"] if schema == "induction" \
        else ["invariant"]
    for kind in kinds:
        for comment, checks in families():
            m = Machine(f"operator table over frozen states, never bad: "
                        f"{comment}", frozen=True)
            acc = conjunction(m, checks)
            m.emit(f"bad {m.emit(f'not {m.sort(1)} {acc}')}")
            if btormc(m.text(), kmax=2) != "":
                raise SystemExit(f"dispute: btormc reaches bad: {comment}")
            bits = m.pinned()
            wrong = [] if number % 2 else \
                [[bits[0][0], bits[0][1], 1 - bits[0][2]]] + bits[1:]
            if kind == "k-induction":
                cert, control = {"kind": "k-induction", "k": 1}, None
            elif schema == "induction":
                cert = {"kind": "bit-invariant", "bits": bits}
                control = {"kind": "bit-invariant", "bits": wrong}
            else:
                cert = {"kind": "clause-invariant",
                        "clauses": [[b] for b in bits]}
                control = {"kind": "clause-invariant",
                           "clauses": [[b] for b in wrong]}
            write("vectors", "program", m.text())
            write("vectors", "cert", json.dumps(cert, sort_keys=True) + "\n")
            if control is not None:
                write("controls", "cert",
                      json.dumps(control, sort_keys=True) + "\n")
            number += 1
    sys.stdout.write(f"frozen tables for {schema} up to "
                     f"{number - 1:03d}; btormc reaches no bad within 2\n")
    return 0


def main(argv: list[str]) -> int:
    if argv[0] == "--frozen":
        return frozen(argv[1], int(argv[2]), argv[3])
    out_dir, number = argv[0], int(argv[1])
    here = os.path.dirname(os.path.abspath(__file__))
    version = subprocess.run(["btormc", "--version"], capture_output=True,
                             text=True).stdout.strip()
    records = []
    for comment, checks in families():
        m = Machine(f"operator table: {comment}")
        nodes = []
        for label, build in checks:
            nodes.append(build(m))
            records.append({"vector": f"{number:03d}", "check": label,
                            "oracle": f"btormc {version} -kmax 0",
                            **testify(label, build)})
        acc = nodes[0]
        for node in nodes[1:]:
            acc = m.emit(f"and {m.sort(1)} {acc} {node}")
        m.emit(f"bad {acc}")
        stem = os.path.join(out_dir, f"{number:03d}")
        with open(stem + ".program", "w") as fh:
            fh.write(m.text())
        with open(stem + ".input", "w") as fh:
            fh.write('{\n "steps": [\n  {}\n ]\n}\n')
        with open(stem + ".expect", "w") as fh:
            fh.write('{\n  "bad": true,\n  "depth": 0\n}\n')
        number += 1
    with open(os.path.join(here, "checks.jsonl"), "w") as fh:
        for r in records:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    sys.stdout.write(f"{len(records)} checks, btormc agreeing on every "
                     f"one in both polarities; vectors up to "
                     f"{number - 1:03d}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
