"""Operator tables for the C fragment, as programs that never fail,
and what clang says about them.

Each program declares a few variables at the corners of one integer
type and asserts, in one expression, a conjunction of *checks*: one
operator applied to those variables, compared with the value ISO C
gives it under ILP32's sizes and two's-complement wrap. The programs
are safe — no assertion can fail — which is what makes them certificate
vectors: a checker that builds its own machine from the program text
discharges a certificate for one only if it computes every operator in
it as C does.

The expected values are computed here, from the standard's conversion
and arithmetic rules and from no interpreter in the registry, and then
put to the oracle: ``clang -O0 -fwrapv`` on this host. As written each
program must return from ``main``; and for every check, the program
with that one expected value moved by one must reach
``__assert_fail``. Programs that read inputs are run by a driver over
every input (two 8-bit inputs) or a fixed grid of corners (wider
ones). The testimony is recorded in ``testimony.jsonl`` beside this
file; a disagreement stops the build (KERNEL.md §6: a dispute to
adjudicate, never a verdict).

Programs whose expectation is a stipulation of the fragment, where C
leaves the behaviour undefined, are written out and *not* put to the
oracle; ``testimony.jsonl`` says so for each.

    python3 build.py <out-dir>

writes ``<name>.c`` for every program. The programs avoid ``long`` and
plain ``char``, the two types this host's ABI gives differently from
ILP32. Nothing here is imported or run by the kernel.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

TYPES = {"signed char": (8, True), "unsigned char": (8, False),
         "short": (16, True), "unsigned short": (16, False),
         "int": (32, True), "unsigned int": (32, False),
         "long long": (64, True), "unsigned long long": (64, False)}
INT = (32, True)


def conv(v: int, t) -> int:
    w, signed = t
    v &= (1 << w) - 1
    return v - (1 << w) if signed and v >> (w - 1) else v


def promote(t):
    return INT if t[0] < 32 else t


def usual(a, b):
    """The usual arithmetic conversions, ILP32, on promoted types."""
    a, b = promote(a), promote(b)
    if a[0] != b[0]:
        wide, narrow = (a, b) if a[0] > b[0] else (b, a)
        return wide          # the wider type holds every narrower value
    return a if not a[1] else b


def lit(v: int, t) -> str:
    """A C expression of promoted type ``t`` and value ``v``."""
    w, signed = t
    if not signed:
        return f"{v}{'u' if w == 32 else 'ULL'}"
    suffix = "" if w == 32 else "LL"
    if v == -(1 << (w - 1)):
        return f"(-{-(v + 1)}{suffix} - 1)"
    return f"({v}{suffix})" if v < 0 else f"{v}{suffix}"


def tdiv(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def binary(op: str, a: int, ta, b: int, tb):
    """(value, type) of ``a op b`` for operands of the given types."""
    if op in ("<<", ">>"):
        r = promote(ta)
        return (conv(a << b, r) if op == "<<" else a >> b), r
    r = usual(ta, tb)
    x, y = conv(a, r), conv(b, r)
    if op in ("<", "<=", ">", ">=", "==", "!="):
        return int({"<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y,
                    "==": x == y, "!=": x != y}[op]), INT
    m = (1 << r[0]) - 1
    v = {"+": lambda: x + y, "-": lambda: x - y, "*": lambda: x * y,
         "/": lambda: tdiv(x, y), "%": lambda: x - tdiv(x, y) * y,
         "&": lambda: (x & m) & (y & m), "|": lambda: (x & m) | (y & m),
         "^": lambda: (x & m) ^ (y & m)}[op]()
    return conv(v, r), r


def unary(op: str, a: int, ta):
    if op == "!":
        return int(a == 0), INT
    r = promote(ta)
    return conv({"-": -a, "~": ~a, "+": a}[op], r), r


# -- programs -----------------------------------------------------------------

HEAD = """extern void __assert_fail(const char *, const char *, unsigned int, \
const char *) __attribute__ ((__noreturn__));
void reach_error() { __assert_fail("0", "%s.c", 2, "reach_error"); }
void __VERIFIER_assert(int cond) {
  if (!(cond)) { ERROR: {reach_error();} }
  return;
}
"""

CORNERS = {"signed char": ((100, 27), (-128, 3)),
           "unsigned char": ((200, 100), (255, 7)),
           "short": ((30000, 2767), (-32768, 5)),
           "unsigned short": ((65535, 65535), (40000, 3)),
           "int": ((2147483647, 1), (-7, 2)),
           "unsigned int": ((4294967295, 2), (7, 4294967290)),
           "long long": ((9223372036854775807, 1), (-7, 2)),
           "unsigned long long": ((18446744073709551615, 2), (7, 3))}


class Program:
    def __init__(self, name: str, comment: str):
        self.name, self.comment = name, comment
        self.decls: list[str] = []      # lines before main (externs)
        self.vars: list[str] = []       # declarations inside main
        self.checks: list[tuple[str, int, tuple]] = []
        self.inputs: list[tuple[str, str]] = []   # (function, C type)
        self.oracle = True

    def check(self, expr: str, value: int, t) -> None:
        self.checks.append((expr, value, t))

    def holds(self, expr: str) -> None:
        """A check that is a truth: an identity over the inputs."""
        self.checks.append((expr, 1, INT))

    def text(self, moved: int | None = None) -> str:
        terms = []
        for i, (expr, v, t) in enumerate(self.checks):
            if i == moved:
                v = conv(v + 1, t)
            terms.append(f"(({expr}) == {lit(v, t)})")
        body = "\n      & ".join(terms)
        return (f"/* {self.comment} */\n" + HEAD % self.name
                + "".join(d + "\n" for d in self.decls)
                + "int main() {\n"
                + "".join(f"  {v}\n" for v in self.vars)
                + f"  __VERIFIER_assert(\n        {body});\n"
                + "  return 0;\n}\n")


def programs() -> list[Program]:
    out = []
    for name, t in TYPES.items():
        tag = name.replace(" ", "_")
        (a, b), (c, d) = CORNERS[name]
        decl = [f"{name} a = {lit(a, promote(t))};",
                f"{name} b = {lit(b, promote(t))};",
                f"{name} c = {lit(c, promote(t))};",
                f"{name} d = {lit(d, promote(t))};"]

        p = Program(f"arith_{tag}",
                    f"addition, subtraction, multiplication and the bitwise "
                    f"operators on {name}: the operands promote, the result "
                    "wraps at its own type")
        p.vars = decl
        for op in ("+", "-", "&", "|", "^"):
            for x, y, ex in ((a, b, "a {} b"), (c, d, "c {} d"),
                             (b, c, "b {} c")):
                p.check(ex.format(op), *binary(op, x, t, y, t))
        # a multiplier is the costly circuit: one product at 64 bits
        for x, y, ex in ((a, b, "a * b"), (c, d, "c * d"))[:1 if t[0] == 64
                                                           else 2]:
            p.check(ex, *binary("*", x, t, y, t))
        out.append(p)

        p = Program(f"order_{tag}",
                    f"comparisons, shifts within the width, and the unary "
                    f"operators on {name}")
        p.vars = decl
        for op in ("<", "<=", ">", ">=", "==", "!="):
            for x, y, ex in ((a, b, "a {} b"), (c, d, "c {} d"),
                             (a, a, "a {} a"), (d, c, "d {} c")):
                p.check(ex.format(op), *binary(op, x, t, y, t))
        r = promote(t)
        for x, ex in ((a, "a"), (c, "c")):
            for n in (0, 1, r[0] - 1):
                p.check(f"{ex} >> {n}", *binary(">>", x, t, n, INT))
            for op in ("-", "~", "!", "+"):
                p.check(f"{op}{ex}", *unary(op, x, t))
        if not r[1]:                    # << on unsigned results only:
            for n in (0, 1, r[0] - 1):  # a signed overflow is undefined
                p.check(f"a << {n}", *binary("<<", a, t, n, INT))
        else:
            p.check("d << 3", *binary("<<", d, t, 3, INT))
        out.append(p)

        p = Program(f"cast_{tag}",
                    f"casts from {name} to every integer type: truncation, "
                    "sign extension, zero extension")
        p.vars = decl[:1] + decl[2:3]
        for target, tt in TYPES.items():
            for x, ex in ((a, "a"), (c, "c")):
                p.check(f"({target}){ex}", conv(conv(x, tt), promote(tt)),
                        promote(tt))
        out.append(p)

    # division is the costliest circuit a checker blasts: two operands
    # and two checks per program, one program per instruction pair the
    # machine has for it (32 and 64 bits, signed and unsigned)
    for name, pairs in (("int", ((-7, 2), (7, -2))),
                        ("unsigned int", ((4294967290, 7),)),
                        ("long long", ((-7, 2),)),
                        ("unsigned long long", ((18446744073709551610, 7),))):
        t, tag = TYPES[name], name.replace(" ", "_")
        for n, (x, y) in enumerate(pairs):
            p = Program(f"div_{tag}" + ("" if not n else f"_{n}"),
                        f"division and remainder on {name}: truncation "
                        "toward zero, the remainder taking the dividend's "
                        "sign")
            p.vars = [f"{name} a = {lit(x, t)};", f"{name} b = {lit(y, t)};"]
            p.check("a / b", *binary("/", x, t, y, t))
            p.check("a % b", *binary("%", x, t, y, t))
            out.append(p)

    p = Program("mixed", "operands of different types: the usual arithmetic "
                         "conversions decide signedness and width")
    vals = {"a": ("int", -1), "b": ("unsigned int", 1),
            "c": ("long long", -1), "d": ("unsigned long long", 1),
            "e": ("unsigned char", 255), "f": ("signed char", -1),
            "g": ("unsigned short", 65535), "h": ("short", -2)}
    p.vars = [f"{ty} {n} = {lit(v, promote(TYPES[ty]))};"
              for n, (ty, v) in vals.items()]
    for x, op, y in (("a", "<", "b"), ("a", ">", "b"), ("c", "<", "b"),
                     ("c", "<", "d"), ("e", "==", "f"), ("a", "==", "f"),
                     ("a", "<", "e"), ("g", ">", "h"), ("a", "+", "b"),
                     ("a", "*", "b"), ("c", "+", "b"), ("c", "*", "d"),
                     ("f", "+", "e"), ("h", "*", "g"), ("a", "&", "g"),
                     ("c", "^", "b"), ("e", "-", "g"), ("b", "-", "e"),
                     ("d", "-", "e"), ("a", ">>", "b"), ("e", "<<", "b")):
        (tx, vx), (ty, vy) = vals[x], vals[y]
        p.check(f"{x} {op} {y}", *binary(op, vx, TYPES[tx], vy, TYPES[ty]))
    out.append(p)

    p = Program("store", "initialisation converts to the type stored into")
    p.vars = ["unsigned char a = 300;", "signed char b = 200;",
              "short c = 70000;", "unsigned short d = -1;",
              "int e = 3000000000u;", "unsigned int f = -1;"]
    for ex, v, t in (("a", 44, INT), ("b", -56, INT), ("c", 4464, INT),
                     ("d", 65535, INT), ("e", -1294967296, INT),
                     ("f", 4294967295, (32, False))):
        p.check(ex, v, t)
    out.append(p)

    p = Program("update", "compound assignment and increment convert to the "
                          "type updated")
    p.vars = ["unsigned char g = 250;", "g += 10;", "signed char h = 127;",
              "h++;", "unsigned short i = 0;", "i--;", "int j = 7;",
              "j <<= 4;", "j ^= 5;"]
    for ex, v, t in (("g", 4, INT), ("h", -128, INT), ("i", 65535, INT),
                     ("j", 117, INT)):
        p.check(ex, v, t)
    out.append(p)

    p = Program("bytes", "identities over every pair of bytes: the checker "
                         "must hold them for all inputs, not for constants")
    p.decls = ["extern unsigned char __VERIFIER_nondet_uchar(void);"]
    p.inputs = [("__VERIFIER_nondet_uchar", "unsigned char")] * 2
    p.vars = ["unsigned char u = __VERIFIER_nondet_uchar();",
              "unsigned char v = __VERIFIER_nondet_uchar();"]
    for ex in ("(unsigned char)(u + v) == (unsigned char)(v + u)",
               "((u ^ v) ^ v) == u", "(u & v) <= u", "(u | v) >= u",
               "(unsigned char)(u - v + v) == u", "(u >> 1) <= 127",
               "((u << 1) & 1) == 0", "(unsigned char)~u == 255 - u",
               "(u < v) == (v > u)", "(u <= v) == !(u > v)",
               "(u * 2) == (u + u)", "(u & 128) == 0 | (signed char)u < 0",
               "(u == v) == !(u != v)", "-(-u) == u", "(~u & u) == 0"):
        p.holds(ex)
    out.append(p)

    p = Program("words", "identities over two ints and two unsigned ints, "
                         "for all inputs")
    p.decls = ["extern int __VERIFIER_nondet_int(void);",
               "extern unsigned int __VERIFIER_nondet_uint(void);"]
    p.inputs = [("__VERIFIER_nondet_int", "int")] * 2 + \
               [("__VERIFIER_nondet_uint", "unsigned int")] * 2
    p.vars = ["int x = __VERIFIER_nondet_int();",
              "int y = __VERIFIER_nondet_int();",
              "unsigned int m = __VERIFIER_nondet_uint();",
              "unsigned int n = __VERIFIER_nondet_uint();"]
    for ex in ("(x + y) - y == x", "(x ^ y) == (x | y) - (x & y)",
               "-(-x) == x", "~x == -x - 1", "(x < y) == (y > x)",
               "(x <= y) == !(x > y)", "((unsigned int)x >> 31) == (x < 0)",
               "(x >> 31) == -(x < 0)", "(m + n) - n == m",
               "(m < n) == (n > m)", "(m & n) <= m", "(m | n) >= m",
               "(m >> 1) <= 2147483647u", "((m << 1) & 1u) == 0u",
               "(long long)x + (long long)y == (long long)y + (long long)x",
               "(unsigned long long)m + n >= m",
               "(m == (unsigned int)x) == ((int)m == x)"):
        p.holds(ex)
    out.append(p)

    for name, comment, decls, checks in (
            ("stipulated_shift",
             "the fragment's stipulation on shift counts, where C leaves "
             "the behaviour undefined: a count at or beyond the width or "
             "below zero gives 0, or the sign fill for a signed right shift "
             "of a negative value",
             ["int a = 7;", "int b = -7;", "int w = 32;", "int o = -1;",
              "unsigned int t = 2147483648u;"],
             (("a << w", 0, INT), ("t >> w", 0, (32, False)),
              ("b >> w", -1, INT), ("a >> w", 0, INT), ("a << o", 0, INT),
              ("b >> o", -1, INT), ("a << (w - 1)", -2147483648, INT),
              ("t >> (w - 1)", 1, (32, False)))),
            ("stipulated_zero",
             "the fragment's stipulation on a zero divisor, as SMT-LIB has "
             "it: the quotient is all ones (1 for a negative signed "
             "dividend), the remainder is the dividend",
             ["int a = 7;", "int b = -7;", "unsigned int u = 7;",
              "int z = 0;"],
             (("a / z", -1, INT), ("b / z", 1, INT), ("b % z", -7, INT),
              ("u / z", 4294967295, (32, False)),
              ("u % z", 7, (32, False)))),
            ("stipulated_overflow",
             "the fragment's stipulation on the one signed overflow of "
             "division: the quotient wraps to the dividend, the remainder "
             "is 0",
             ["int m = (-2147483647 - 1);", "int o = -1;"],
             (("m / o", -2147483648, INT), ("m % o", 0, INT)))):
        p = Program(name, comment)
        p.oracle = False
        p.vars = decls
        for ex, v, t in checks:
            p.check(ex, v, t)
        out.append(p)
    return out


# -- the oracle ---------------------------------------------------------------

STUB = """
void _exit(int);
void __assert_fail(const char *a, const char *b, unsigned int c,
                   const char *d) { _exit(99); }
"""


def driver(p: Program) -> str:
    """For a program that reads inputs: its ``main`` renamed, the input
    functions answering from globals, and a ``main`` that runs it over
    every pair of bytes, or over a grid of corners for wider inputs."""
    if not p.inputs:
        return ""
    corners = {"unsigned char": [str(i) for i in range(256)],
               "int": ["0", "1", "-1", "2", "-2", "7", "-7", "2147483647",
                       "(-2147483647 - 1)", "65536", "-65536", "123456789"],
               "unsigned int": ["0u", "1u", "2u", "7u", "4294967295u",
                                "2147483648u", "2147483647u", "65536u",
                                "4294967290u", "123456789u"]}
    kinds = []
    for fn, ty in p.inputs:
        if (fn, ty) not in kinds:
            kinds.append((fn, ty))
    out = ["#undef main"]
    for k, (fn, ty) in enumerate(kinds):
        out += [f"static {ty} in{k}[2]; static int at{k};",
                f"{ty} {fn}(void) {{ return in{k}[at{k}++]; }}"]
    out.append("int main() {")
    for k, (fn, ty) in enumerate(kinds):
        vals = ", ".join(corners[ty])
        out.append(f"  static const {ty} grid{k}[] = {{{vals}}};")
        out.append(f"  int n{k} = sizeof(grid{k}) / sizeof(grid{k}[0]);")
    loops = [f"for (int i{k}{j} = 0; i{k}{j} < n{k}; i{k}{j}++)"
             for k in range(len(kinds)) for j in range(2)]
    sets = "".join(f" in{k}[{j}] = grid{k}[i{k}{j}]; at{k} = 0;"
                   for k in range(len(kinds)) for j in range(2))
    out.append("  " + " ".join(loops) + " {" + sets + " vector_main(); }")
    out += ["  return 0;", "}"]
    return "\n".join(out) + "\n"


def clang(p: Program, moved: int | None = None) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "p.c"), "w") as fh:
            fh.write(("#define main vector_main\n" if p.inputs else "")
                     + p.text(moved) + STUB + driver(p))
        exe = os.path.join(tmp, "p")
        subprocess.run(["clang", "-O0", "-fwrapv", "-w", "-o", exe,
                        os.path.join(tmp, "p.c")], check=True)
        return subprocess.run([exe], timeout=300).returncode


def main(argv: list[str]) -> int:
    out_dir = argv[0]
    here = os.path.dirname(os.path.abspath(__file__))
    version = subprocess.run(["clang", "--version"], capture_output=True,
                             text=True).stdout.split("\n")[0]
    os.makedirs(out_dir, exist_ok=True)
    records, asked = [], 0
    for p in programs():
        with open(os.path.join(out_dir, p.name + ".c"), "w") as fh:
            fh.write(p.text())
        record = {"program": p.name, "checks": len(p.checks)}
        if p.oracle:
            if clang(p) != 0:
                raise SystemExit(f"dispute: {p.name}: clang fails an "
                                 "assertion of the program as written")
            for i, (expr, _, _) in enumerate(p.checks):
                if clang(p, moved=i) != 99:
                    raise SystemExit(f"dispute: {p.name}: with the "
                                     f"expectation of `{expr}` moved, "
                                     "clang still returns")
            asked += len(p.checks)
            record.update(oracle=f"{version}, -O0 -fwrapv",
                          as_written="returns", each_check_moved="fails",
                          inputs=("every pair of bytes" if p.inputs
                                  and p.inputs[0][1] == "unsigned char"
                                  else "a grid of corners" if p.inputs
                                  else "none"))
        else:
            record.update(oracle=None, why="a stipulation of the fragment "
                          "where C leaves the behaviour undefined")
        records.append(record)
    with open(os.path.join(here, "testimony.jsonl"), "w") as fh:
        for r in records:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    sys.stdout.write(f"{len(records)} programs; clang agreeing on "
                     f"{asked} checks as written and with each expected "
                     "value moved\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
