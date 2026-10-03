"""Instruction tables for RV64IM, and what the Sail model says about them.

Each *check* runs one instruction (or one short idiom: a branch, a
store and a load, a call and its return) on fixed operands and
compares the result with the value the RISC-V specification gives; a
failed check halts, and a vector reaches its closing ``ebreak`` — bad
— only when every check of its family held. The vector's expectation
is therefore ``{"bad": true, "depth": 0}``.

The expected values are computed here, from the specification's text
and not from any interpreter in the registry, and then put to the
oracle: the same instruction lines are assembled bare-metal with
``riscv64-unknown-elf-gcc`` and run on ``sail_riscv_sim``, the
executable of the Sail model that is the architecture's formal
specification. As written the program must succeed; and for every
check, the program with that one expected value moved by one must
fail with that check's number. The
testimony is recorded in ``checks.jsonl`` beside this file; a
disagreement stops the build (KERNEL.md §6: a dispute to adjudicate,
never a verdict).

    python3 build.py <vectors-dir> <first-number>

writes ``NNN.program``, ``NNN.input``, ``NNN.expect`` from
``<first-number>`` on. Nothing here is imported or run by the kernel.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

M64, M32 = (1 << 64) - 1, (1 << 32) - 1
MIN64, MIN32 = 1 << 63, 1 << 31


def s(v, w=64):
    v &= (1 << w) - 1
    return v - (1 << w) if v >> (w - 1) else v


def sx(v, w=32):
    """Sign-extend the low ``w`` bits to 64."""
    return s(v, w) & M64


def tdiv(a, b):
    """Division rounding toward zero, on Python integers, b != 0."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


# -- the specification's semantics, written out -------------------------------

def r_type(op, a, b):
    if op == "add":
        return (a + b) & M64
    if op == "sub":
        return (a - b) & M64
    if op == "and":
        return a & b
    if op == "or":
        return a | b
    if op == "xor":
        return a ^ b
    if op == "sll":
        return (a << (b & 63)) & M64
    if op == "srl":
        return a >> (b & 63)
    if op == "sra":
        return (s(a) >> (b & 63)) & M64
    if op == "slt":
        return int(s(a) < s(b))
    if op == "sltu":
        return int(a < b)
    if op == "addw":
        return sx(a + b)
    if op == "subw":
        return sx(a - b)
    if op == "sllw":
        return sx(a << (b & 31))
    if op == "srlw":
        return sx((a & M32) >> (b & 31))
    if op == "sraw":
        return sx(s(a, 32) >> (b & 31))
    if op == "mul":
        return (a * b) & M64
    if op == "mulh":
        return ((s(a) * s(b)) >> 64) & M64
    if op == "mulhsu":
        return ((s(a) * b) >> 64) & M64
    if op == "mulhu":
        return (a * b) >> 64
    if op == "mulw":
        return sx(a * b)
    if op == "div":
        if b == 0:
            return M64
        if a == MIN64 and b == M64:
            return MIN64
        return tdiv(s(a), s(b)) & M64
    if op == "divu":
        return M64 if b == 0 else a // b
    if op == "rem":
        if b == 0:
            return a
        if a == MIN64 and b == M64:
            return 0
        return (s(a) - tdiv(s(a), s(b)) * s(b)) & M64
    if op == "remu":
        return a if b == 0 else a % b
    x, y = s(a, 32), s(b, 32)
    ux, uy = a & M32, b & M32
    if op == "divw":
        if y == 0:
            return M64
        if x == -MIN32 and y == -1:
            return sx(MIN32)
        return sx(tdiv(x, y))
    if op == "divuw":
        return M64 if uy == 0 else sx(ux // uy)
    if op == "remw":
        if y == 0:
            return sx(x)
        if x == -MIN32 and y == -1:
            return 0
        return sx(x - tdiv(x, y) * y)
    if op == "remuw":
        return sx(ux if uy == 0 else ux % uy)
    raise ValueError(op)


def i_type(op, a, i):
    u = i & M64
    if op == "addi":
        return (a + i) & M64
    if op == "slti":
        return int(s(a) < i)
    if op == "sltiu":
        return int(a < u)
    if op == "xori":
        return a ^ u
    if op == "ori":
        return a | u
    if op == "andi":
        return a & u
    if op == "slli":
        return (a << i) & M64
    if op == "srli":
        return a >> i
    if op == "srai":
        return (s(a) >> i) & M64
    if op == "addiw":
        return sx(a + i)
    if op == "slliw":
        return sx(a << i)
    if op == "srliw":
        return sx((a & M32) >> i)
    if op == "sraiw":
        return sx(s(a, 32) >> i)
    raise ValueError(op)


def unary(op, a):
    return {"mv": a, "not": ~a & M64, "neg": -a & M64, "negw": sx(-a),
            "sext.w": sx(a), "seqz": int(a == 0), "snez": int(a != 0),
            "sltz": int(s(a) < 0), "sgtz": int(s(a) > 0)}[op]


def taken(op, a, b=0):
    return {"beq": a == b, "bne": a != b, "blt": s(a) < s(b),
            "bge": s(a) >= s(b), "bltu": a < b, "bgeu": a >= b,
            "bgt": s(a) > s(b), "ble": s(a) <= s(b), "bgtu": a > b,
            "bleu": a <= b, "beqz": a == 0, "bnez": a != 0,
            "blez": s(a) <= 0, "bgez": s(a) >= 0, "bltz": s(a) < 0,
            "bgtz": s(a) > 0}[op]


# -- checks: (label, lines computing t2, expected value of t2) ----------------

def li(reg, v):
    return f"    li {reg}, {v & M64:#x}"


def families() -> list[tuple[str, list, list[str], list[str]]]:
    """(comment, checks, subroutines, data) per vector."""
    arith = []
    for op in ("add", "sub", "and", "or", "xor", "slt", "sltu", "addw",
               "subw", "mul", "mulh", "mulhsu", "mulhu", "mulw"):
        for a, b in ((7, -7 & M64), (M64, 1), (MIN64, M64), (MIN64 - 1, 1),
                     (0x123456789abcdef0, 0xfedcba9876543210),
                     (0x7fffffff, 1), (M32, M32), (0, 0), (1, MIN64)):
            arith.append((f"{op} {a:#x} {b:#x}",
                          [li("t0", a), li("t1", b), f"    {op} t2, t0, t1"],
                          r_type(op, a, b)))
    for op in ("addi", "slti", "sltiu", "xori", "ori", "andi", "addiw"):
        for a, i in ((0, -1), (M64, 1), (5, -2048), (MIN64, 2047),
                     (0x7fffffff, 1), (M32, -1), (7, 7)):
            arith.append((f"{op} {a:#x} {i}",
                          [li("t0", a), f"    {op} t2, t0, {i}"],
                          i_type(op, a, i)))

    shift = []
    for op in ("sll", "srl", "sra", "sllw", "srlw", "sraw"):
        for a in (MIN64 | 1, 0x123456789abcdef0, M64, 0x80000001):
            for b in (0, 1, 31, 32, 33, 63, 64, 65):
                shift.append((f"{op} {a:#x} {b}",
                              [li("t0", a), li("t1", b),
                               f"    {op} t2, t0, t1"], r_type(op, a, b)))
    shift_imm = []
    for op, counts in (("slli", (0, 1, 31, 32, 63)),
                       ("srli", (0, 1, 31, 32, 63)),
                       ("srai", (0, 1, 31, 32, 63)),
                       ("slliw", (0, 1, 31)), ("srliw", (0, 1, 31)),
                       ("sraiw", (0, 1, 31))):
        for a in (MIN64 | 1, 0x123456789abcdef0, 0x80000001):
            for i in counts:
                shift_imm.append((f"{op} {a:#x} {i}",
                                  [li("t0", a), f"    {op} t2, t0, {i}"],
                                  i_type(op, a, i)))

    divide = []
    for op in ("div", "divu", "rem", "remu", "divw", "divuw", "remw",
               "remuw"):
        for a in (7, -7 & M64, MIN64, 0, 0x80000000, M32):
            for b in (2, -2 & M64, 0, M64, 0x100000003):
                divide.append((f"{op} {a:#x} {b:#x}",
                               [li("t0", a), li("t1", b),
                                f"    {op} t2, t0, t1"], r_type(op, a, b)))

    control, n = [], 0
    for op in ("mv", "not", "neg", "negw", "sext.w", "seqz", "snez",
               "sltz", "sgtz"):
        for a in (0, 1, M64, MIN64, 0x80000000, 0x7fffffff):
            control.append((f"{op} {a:#x}",
                            [li("t0", a), f"    {op} t2, t0"],
                            unary(op, a)))
    for imm in (0x80000, 0x12345, 0xfffff, 0, 1):
        control.append((f"lui {imm:#x}", [f"    lui t2, {imm:#x}"],
                        sx(imm << 12)))
    pairs = ((3, 5), (5, 5), (5, 3), (M64, 0), (0, M64), (MIN64, 1),
             (M64, M64))
    for op in ("beq", "bne", "blt", "bge", "bltu", "bgeu", "bgt", "ble",
               "bgtu", "bleu"):
        for a, b in pairs:
            n += 1
            control.append((f"{op} {a:#x} {b:#x}",
                            [li("t0", a), li("t1", b), "    li t2, 1",
                             f"    {op} t0, t1, over{n}", "    li t2, 0",
                             f"over{n}:"], int(taken(op, a, b))))
    for op in ("beqz", "bnez", "blez", "bgez", "bltz", "bgtz"):
        for a in (0, 1, M64, MIN64):
            n += 1
            control.append((f"{op} {a:#x}",
                            [li("t0", a), "    li t2, 1",
                             f"    {op} t0, over{n}", "    li t2, 0",
                             f"over{n}:"], int(taken(op, a))))
    returns = {"ret": ["    ret"], "jr": ["    jr ra"],
               "jalr0": ["    jalr zero, ra, 0"],
               "jalrm": ["    jalr zero, 0(ra)"],
               "jalrl": ["    mv t5, ra", "    jalr t4, t5, 0"],
               "jalr1": ["    mv t5, ra", "    jalr t5"]}
    subs = []
    for name, back in returns.items():
        subs += [f"sub_{name}:", "    addi t2, t2, 10"] + back
        for call in (f"    call sub_{name}", f"    jal ra, sub_{name}",
                     f"    jal sub_{name}"):
            control.append((f"{call.strip()} / {back[-1].strip()}",
                            ["    li t2, 0", call, "    addi t2, t2, 1"],
                            11))
    subs += ["sub_link:", "    addi t2, t2, 10", "    mv t5, ra",
             "    jalr t5", "    addi t2, t2, 100", "    j after_link"]
    control.append(("jalr with one operand links like a call",
                    ["    li t2, 0", "    jal ra, sub_link", "    jr ra",
                     "after_link:"], 110))
    for name in ("s0", "fp", "x8"):
        control.append((f"s0, fp and x8 are one register ({name})",
                        ["    li s0, 5", "    li s1, 9",
                         f"    mv t2, {name}"], 5))
    for imm in (0, 1):
        n += 1
        control.append((f"auipc {imm} against jal's link",
                        [f"    auipc t3, {imm}", f"    jal t4, over{n}",
                         f"over{n}:", "    sub t2, t4, t3"],
                        (8 - (imm << 12)) & M64))

    memory = []
    v = 0x8182838485868788
    for store, at, load, off, expect in (
            ("sd", 8, "ld", 8, v), ("sd", 8, "lw", 8, sx(v)),
            ("sd", 8, "lwu", 8, v & M32), ("sd", 8, "lw", 12, sx(v >> 32)),
            ("sd", 8, "lwu", 12, v >> 32), ("sd", 8, "lh", 8, sx(v, 16)),
            ("sd", 8, "lhu", 10, (v >> 16) & 0xffff),
            ("sd", 8, "lh", 14, sx(v >> 48, 16)),
            ("sd", 8, "lb", 15, sx(v >> 56, 8)),
            ("sd", 8, "lbu", 15, v >> 56),
            ("sd", 8, "lb", 9, sx(v >> 8, 8)),
            ("sw", 16, "ld", 16, v & M32), ("sh", 24, "ld", 24, v & 0xffff),
            ("sb", 32, "ld", 32, v & 0xff), ("sw", 20, "lw", 20, sx(v)),
            ("sh", 30, "lhu", 30, v & 0xffff),
            ("sb", 39, "lbu", 39, v & 0xff)):
        memory.append((f"{store} at {at} then {load} at {off}",
                       ["    la t0, buf", li("t1", v),
                        f"    {store} t1, {at}(t0)",
                        f"    {load} t2, {off}(t0)"], expect))
    memory.append(("sd then ld at a negative offset",
                   ["    la t0, buf", "    addi t3, t0, 48", li("t1", v),
                    "    sd t1, 40(t0)", "    ld t2, -8(t3)"], v))
    memory.append(("sb overwrites one byte of a doubleword",
                   ["    la t0, buf", li("t1", M64), "    sd t1, 48(t0)",
                    "    sb zero, 50(t0)", "    ld t2, 48(t0)"],
                   M64 & ~(0xff << 16)))
    for label, load, off, expect in (
            ("vb", "lb", 0, sx(0x80, 8)), ("vb", "lbu", 0, 0x80),
            ("vb", "lb", 1, 0x7f), ("vh", "lh", 0, sx(0x8001, 16)),
            ("vh", "lhu", 0, 0x8001), ("vw", "lw", 0, sx(0x80000002)),
            ("vw", "lwu", 0, 0x80000002),
            ("vd", "ld", 0, 0x8000000000000003), ("vq", "ld", 0, 0x55),
            ("vs", "lbu", 0, 97), ("vs", "lbu", 1, 10), ("vs", "lbu", 2, 34),
            ("vs", "lbu", 3, 92), ("vs", "lbu", 4, 0)):
        memory.append((f"{load} {off}({label})",
                       [f"    la t0, {label}", f"    {load} t2, {off}(t0)"],
                       expect))
    for a, b, expect in (("al1", "al2", 8), ("vb", "vh", 2), ("vh", "vw", 2),
                         ("vw", "vd", 4), ("vd", "vq", 8), ("vq", "vs", 8),
                         ("sp1", "sp2", 5)):
        memory.append((f"{b} - {a}",
                       [f"    la t0, {a}", f"    la t1, {b}",
                        "    sub t2, t1, t0"], expect))
    data = ["    .balign 8", "buf:", "    .zero 64",
            "vb:", "    .byte 0x80, 0x7f",
            "vh:", "    .half 0x8001",
            "vw:", "    .word 0x80000002",
            "vd:", "    .dword 0x8000000000000003",
            "vq:", "    .quad 0x55",
            "vs:", '    .string "a\\n\\"\\\\"',
            "    .balign 8", "al1:", "    .byte 1", "    .align 3",
            "al2:", "    .dword 5",
            "sp1:", "    .space 5", "sp2:", "    .byte 2"]

    return [("the integer register and immediate instructions", arith, [],
             []),
            ("shifts by a register, 64 and 32 bits wide, at and beyond "
             "the width", shift, [], []),
            ("shifts by an immediate, 64 and 32 bits wide", shift_imm, [],
             []),
            ("the division family: every sign pair, the zero divisor, the "
             "overflow", divide, [], []),
            ("the unary pseudo-instructions, lui, every branch at less, "
             "equal and greater, calls and each way of returning, auipc",
             control, subs, []),
            ("stores and loads at every width and non-zero offsets, the "
             "data directives, strings, alignment", memory, [], data)]


def body(checks, moved: int | None = None) -> list[str]:
    lines = []
    for k, (_, compute, expect) in enumerate(checks, 1):
        if k == moved:
            expect = (expect + 1) & M64
        lines += [f"    li gp, {k}"] + compute + [li("t6", expect),
                                                    "    bne t2, t6, fail"]
    return lines


def vector(comment, checks, subs, data) -> str:
    return "\n".join(
        [f"# instruction table: {comment}", "_start:"] + body(checks)
        + ["    ebreak", "fail:", "    li a7, 93", "    ecall"] + subs
        + (["    .data"] + data if data else [])) + "\n"


# -- the oracle ---------------------------------------------------------------

LINK = """OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {
  . = 0x80000000;
  .text : { *(.text.init) *(.text) }
  . = ALIGN(0x1000);
  .tohost : { *(.tohost) }
  . = ALIGN(0x1000);
  .data : { *(.data) }
  .bss : { *(.bss) }
}
"""


def bare_metal(checks, subs, data, moved) -> str:
    """The same checks for the oracle: success when all hold, else
    the number of the first that does not (riscv-tests' tohost
    protocol)."""
    return "\n".join(
        ["    .section .text.init", "    .globl _start", "_start:"]
        + body(checks, moved)
        + ["    li a0, 1", "    j report", "fail:", "    slli a0, gp, 1",
           "    ori a0, a0, 1", "report:", "    la t0, tohost",
           "    sd a0, 0(t0)", "forever:", "    j forever"] + subs
        + ["    .data"] + data
        + ['    .section .tohost,"aw",@progbits', "    .balign 64",
           "    .globl tohost", "tohost:", "    .dword 0",
           "    .globl fromhost", "fromhost:", "    .dword 0"]) + "\n"


def sail(checks, subs, data, moved=None) -> int:
    """0 when the model reports success, else the failure number."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in (("t.S", bare_metal(checks, subs, data, moved)),
                           ("link.ld", LINK)):
            with open(os.path.join(tmp, name), "w") as fh:
                fh.write(text)
        subprocess.run(
            ["riscv64-unknown-elf-gcc", "-nostdlib", "-nostartfiles",
             "-march=rv64im", "-mabi=lp64", "-mcmodel=medany", "-T",
             os.path.join(tmp, "link.ld"), "-o", os.path.join(tmp, "t.elf"),
             os.path.join(tmp, "t.S")], check=True)
        res = subprocess.run(
            ["sail_riscv_sim", "--inst-limit", "2000000",
             os.path.join(tmp, "t.elf")], capture_output=True, text=True,
            timeout=300)
    failure = re.search(r"FAILURE: (\d+)", res.stdout)
    if res.returncode == 0 and not failure:
        return 0
    if failure:
        return int(failure.group(1))
    raise SystemExit(f"sail_riscv_sim: rc={res.returncode} "
                     f"{res.stdout[-300:]!r} {res.stderr[-300:]!r}")


def main(argv: list[str]) -> int:
    out_dir, number = argv[0], int(argv[1])
    here = os.path.dirname(os.path.abspath(__file__))
    tools = "sail_riscv_sim " + subprocess.run(
        ["sail_riscv_sim", "--version"], capture_output=True,
        text=True).stdout.strip() + "; " + subprocess.run(
        ["riscv64-unknown-elf-gcc", "--version"], capture_output=True,
        text=True).stdout.split("\n")[0]
    records = []
    for comment, checks, subs, data in families():
        said = sail(checks, subs, data)
        if said != 0:
            raise SystemExit(f"dispute: the model fails check {said} "
                             f"({checks[said - 1][0]}) of: {comment}")
        for k, (label, _, expect) in enumerate(checks, 1):
            said = sail(checks, subs, data, moved=k)
            if said != k:
                raise SystemExit(f"dispute: {label}: with its expected "
                                 f"value moved the model fails {said}, "
                                 f"not {k}")
            records.append({"vector": f"{number:03d}", "check": k,
                            "what": label, "expect": f"{expect:#x}",
                            "oracle": tools, "as written": 0,
                            "expected value moved": said})
        stem = os.path.join(out_dir, f"{number:03d}")
        with open(stem + ".program", "w") as fh:
            fh.write(vector(comment, checks, subs, data))
        with open(stem + ".input", "w") as fh:
            fh.write('{\n  "steps": [\n    {}\n  ]\n}\n')
        with open(stem + ".expect", "w") as fh:
            fh.write('{\n  "bad": true,\n  "depth": 0\n}\n')
        number += 1
    with open(os.path.join(here, "checks.jsonl"), "w") as fh:
        for r in records:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    sys.stdout.write(f"{len(records)} checks, the model agreeing on every one "
                     f"as written and with its expected value moved; "
                     f"vectors up to {number - 1:03d}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
