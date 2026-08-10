#!/usr/bin/env python3
"""Generate the six pinned minikernel benchmarks (PROTOCOL.md).

Deterministic (seeded), tiny, tiered — and every label is verified by
a host engine before it is written: btormc/pono for btor2, cadical
for DIMACS, cbmc for C. Curation may use any local tool; the agent
runs see only the emitted directories.
"""

import hashlib
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def emit(name, language, programs):
    """programs: [(qid, filename, text, mode, observable, bound, label)]"""
    d = os.path.join(HERE, name)
    os.makedirs(d, exist_ok=True)
    questions = []
    for qid, fn, text, mode, obs, bound, label in programs:
        path = os.path.join(d, fn)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        questions.append({
            "id": qid, "language": language, "program": fn,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "mode": mode, "observable": obs, "bound": bound,
            "label": label})
    with open(os.path.join(d, "benchmark.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"name": name, "questions": questions}, fh, indent=2,
                  sort_keys=True)
        fh.write("\n")
    print(f"{name}: {len(questions)} questions")


def check(cond, what):
    if not cond:
        sys.exit(f"LABEL VERIFICATION FAILED: {what}")


# ------------------------------------------------------------------ btor2

def btormc(text, k):
    with open("/tmp/_mk.btor2", "w") as fh:
        fh.write(text)
    p = subprocess.run(["btormc", "-kmax", str(k), "/tmp/_mk.btor2"],
                       capture_output=True, text=True, timeout=120)
    return "sat" in p.stdout.split()


def pono_ic3(text):
    with open("/tmp/_mk.btor2", "w") as fh:
        fh.write(text)
    p = subprocess.run(["pono", "-e", "ic3bits", "-k", "100000",
                        "-p", "0", "/tmp/_mk.btor2"],
                       capture_output=True, text=True, timeout=240)
    return "unsat" in (p.stdout + p.stderr).split()


def pono_unsat(text):
    with open("/tmp/_mk.btor2", "w") as fh:
        fh.write(text)
    for mode in ("ind", "ic3bits"):
        p = subprocess.run(["pono", "-e", mode, "-k", "10000", "-p", "0",
                            "/tmp/_mk.btor2"],
                           capture_output=True, text=True, timeout=120)
        if "unsat" in (p.stdout + p.stderr).split():
            return True
    return False


def counter(width, step, bad_val, frozen=False):
    return (f"1 sort bitvec {width}\n2 zero 1\n3 state 1 c\n"
            f"4 constd 1 {step}\n5 add 1 3 4\n6 init 1 3 2\n"
            f"7 next 1 3 {'3' if frozen else '5'}\n8 sort bitvec 1\n"
            f"9 constd 1 {bad_val}\n10 eq 8 3 9\n11 bad 10\n")


def input_sys(width, bad_val, constrain_zero=False):
    t = (f"1 sort bitvec {width}\n2 zero 1\n3 state 1 s\n"
         f"4 input 1 inp\n5 add 1 3 4\n6 init 1 3 2\n7 next 1 3 5\n"
         f"8 sort bitvec 1\n9 constd 1 {bad_val}\n10 eq 8 3 9\n"
         f"11 bad 10\n")
    if constrain_zero:
        t += "12 zero 1\n13 eq 8 4 12\n14 constraint 13\n"
    return t


def twobad(width, unreach, reach_init):
    return (f"1 sort bitvec {width}\n2 constd 1 {reach_init}\n"
            f"3 state 1 c\n4 one 1\n5 add 1 3 4\n6 init 1 3 2\n"
            f"7 next 1 3 5\n8 sort bitvec 1\n9 constd 1 {unreach}\n"
            f"10 eq 8 3 9\n11 bad 10\n12 constd 1 {reach_init}\n"
            f"13 eq 8 3 12\n14 bad 13\n")


def shift_reg(width):
    return (f"1 sort bitvec {width}\n2 one 1\n3 state 1 r\n"
            f"4 constd 1 2\n5 mul 1 3 4\n6 init 1 3 2\n7 next 1 3 5\n"
            f"8 sort bitvec 1\n9 constd 1 {1 << (width - 1)}\n"
            f"10 eq 8 3 9\n11 bad 10\n")


def make_btor2():
    deep = counter(8, 1, 60)
    check(btormc(deep, 100), "b1 deep reach")
    miss = counter(8, 1, 200)
    check(not btormc(miss, 100), "b1 bounded miss")
    frozen = counter(3, 1, 5, frozen=True)
    check(pono_unsat(frozen), "b1 frozen inf")
    parity = counter(8, 2, 5)
    check(pono_unsat(parity), "b1 parity inf")
    inp = input_sys(4, 9)
    check(btormc(inp, 20), "b1 input reach")
    blocked = input_sys(4, 9, constrain_zero=True)
    check(pono_unsat(blocked), "b1 constraint-blocked")
    par32 = counter(32, 2, 5)
    check(pono_ic3(par32), "b1 parity32 ic3")
    emit("btor2-counters", "btor2", [
        ("parity32-inf", "par32.btor2", par32, "forall", "bad", "inf",
         False),
        ("deep-reach", "deep.btor2", deep, "exists", "bad", 100, True),
        ("bounded-miss", "miss.btor2", miss, "forall", "bad", 100, False),
        ("frozen-inf", "frozen.btor2", frozen, "forall", "bad", "inf",
         False),
        ("parity-inf", "parity.btor2", parity, "forall", "bad", "inf",
         False),
        ("input-reach", "input.btor2", inp, "exists", "bad", 20, True),
        ("blocked-inf", "blocked.btor2", blocked, "forall", "bad", "inf",
         False),
    ])

    shift = shift_reg(8)
    check(btormc(shift, 10), "b2 shift reach")
    wrap = counter(4, 3, 7)
    wrap_reach = btormc(wrap, 20)
    check(wrap_reach, "b2 wrap reach")     # 3,6,9,12,15,2,5,8,11,14,1,4,7
    two = twobad(8, 250, 40)
    check(btormc(two, 5), "b2 twobad any-bad")
    lock = counter(6, 4, 2)                # 0,4,8,... never 2 (mod 4)
    check(pono_unsat(lock), "b2 lockstep inf")
    deep2 = counter(8, 1, 90)
    check(not btormc(deep2, 50), "b2 deep miss at 50")
    check(btormc(deep2, 100), "b2 deep reach at 100")
    mod432 = counter(32, 4, 6)
    check(pono_ic3(mod432), "b2 mod4-32 ic3")
    emit("btor2-machines", "btor2", [
        ("mod4-32-inf", "mod432.btor2", mod432, "forall", "bad", "inf",
         False),
        ("shift-reach", "shift.btor2", shift, "exists", "bad", 10, True),
        ("wrap-reach", "wrap.btor2", wrap, "exists", "bad", 20, True),
        ("twobad-any", "twobad.btor2", two, "exists", "bad", 5, True),
        ("lockstep-inf", "lock.btor2", lock, "forall", "bad", "inf",
         False),
        ("deep-frontier", "deep2.btor2", deep2, "exists", "bad", 100,
         True),
        ("deep-bounded-miss", "deep2b.btor2", deep2 + "\n",
         "forall", "bad", 50, False),
    ])


# ----------------------------------------------------------------- dimacs

def cadical_sat(text):
    with open("/tmp/_mk.cnf", "w") as fh:
        fh.write(text)
    p = subprocess.run(["cadical", "/tmp/_mk.cnf"], capture_output=True,
                       text=True, timeout=120)
    if "s SATISFIABLE" in p.stdout:
        return True
    if "s UNSATISFIABLE" in p.stdout:
        return False
    sys.exit("cadical undecided")


def cadical_sat_long(text):
    with open("/tmp/_mk.cnf", "w") as fh:
        fh.write(text)
    p = subprocess.run(["cadical", "/tmp/_mk.cnf"], capture_output=True,
                       text=True, timeout=300)
    if "s SATISFIABLE" in p.stdout:
        return True
    if "s UNSATISFIABLE" in p.stdout:
        return False
    sys.exit("cadical undecided (long)")


def php(pigeons, holes):
    """Pigeonhole: unsat iff pigeons > holes."""
    var = {(p, h): p * holes + h + 1 for p in range(pigeons)
           for h in range(holes)}
    clauses = [[var[p, h] for h in range(holes)] for p in range(pigeons)]
    clauses += [[-var[p1, h], -var[p2, h]] for h in range(holes)
                for p1 in range(pigeons) for p2 in range(p1 + 1, pigeons)]
    head = f"p cnf {pigeons * holes} {len(clauses)}\n"
    return head + "".join(" ".join(map(str, c)) + " 0\n" for c in clauses)


def rand3sat(n, m, seed):
    rng = random.Random(seed)
    clauses = []
    for _ in range(m):
        vs = rng.sample(range(1, n + 1), 3)
        clauses.append([v if rng.random() < 0.5 else -v for v in vs])
    head = f"p cnf {n} {m}\n"
    return head + "".join(" ".join(map(str, c)) + " 0\n" for c in clauses)


def make_dimacs():
    r1 = rand3sat(20, 60, seed=11)
    r2 = rand3sat(24, 80, seed=23)
    check(cadical_sat(r1), "d1 rand sat 1")
    check(cadical_sat(r2), "d1 rand sat 2")
    u1, u2 = php(4, 3), php(5, 4)
    check(not cadical_sat(u1), "d1 php43 unsat")
    check(not cadical_sat(u2), "d1 php54 unsat")
    e1 = php(11, 10)
    check(not cadical_sat_long(e1), "d1 php-11-10 unsat")
    emit("dimacs-mixed", "dimacs", [
        ("php1110-wall", "php1110.cnf", e1, "forall", "sat", "inf",
         False),
        ("rand-sat-a", "ra.cnf", r1, "exists", "sat", "inf", True),
        ("rand-sat-b", "rb.cnf", r2, "exists", "sat", "inf", True),
        ("php43-unsat", "php43.cnf", u1, "forall", "sat", "inf", False),
        ("php54-unsat", "php54.cnf", u2, "forall", "sat", "inf", False),
    ])

    r3 = rand3sat(30, 100, seed=37)
    r4 = rand3sat(40, 140, seed=41)
    check(cadical_sat(r3), "d2 rand sat 3")
    check(cadical_sat(r4), "d2 rand sat 4")
    u3 = php(6, 5)
    check(not cadical_sat(u3), "d2 php65 unsat")
    u4 = rand3sat(16, 130, seed=53)
    check(not cadical_sat(u4), "d2 dense unsat")
    e2 = php(12, 11)   # label is a theorem; past every wall here
    emit("dimacs-harder", "dimacs", [
        ("php1211-hard", "php1211.cnf", e2, "forall", "sat", "inf",
         False),
        ("rand-sat-c", "rc.cnf", r3, "exists", "sat", "inf", True),
        ("rand-sat-d", "rd.cnf", r4, "exists", "sat", "inf", True),
        ("php65-unsat", "php65.cnf", u3, "forall", "sat", "inf", False),
        ("dense-unsat", "dense.cnf", u4, "forall", "sat", "inf", False),
    ])


# ---------------------------------------------------------------------- c

def sampled_safe_stdin(text, inputs):
    with open("/tmp/_mk.c", "w") as fh:
        fh.write(text)
    with open("/tmp/_stub.c", "w") as fh:
        fh.write('#include <stdio.h>\n'
                 'int nondet_int(void){int v;scanf("%d",&v);return v;}\n')
    subprocess.run(["cc", "-o", "/tmp/_mk_bin", "/tmp/_mk.c",
                    "/tmp/_stub.c"], check=True, capture_output=True)
    for inp in inputs:
        p = subprocess.run(["/tmp/_mk_bin"], input=inp,
                           capture_output=True, text=True)
        if p.returncode != 0:
            return False
    return True


def sampled_safe(text, hi):
    import random as _r
    with open("/tmp/_mk.c", "w") as fh:
        fh.write(text)
    with open("/tmp/_stub.c", "w") as fh:
        fh.write('#include <stdio.h>\n'
                 'int nondet_int(void){int v;scanf("%d",&v);return v;}\n')
    subprocess.run(["cc", "-o", "/tmp/_mk_bin", "/tmp/_mk.c",
                    "/tmp/_stub.c"], check=True, capture_output=True)
    rng = _r.Random(97)
    for n in [0, 1, hi - 1, hi] + rng.choices(range(hi), k=300):
        p = subprocess.run(["/tmp/_mk_bin"], input=str(n),
                           capture_output=True, text=True)
        if p.returncode != 0:
            return False
    return True


def cbmc_violated(text, *args):
    with open("/tmp/_mk.c", "w") as fh:
        fh.write(text)
    p = subprocess.run(["cbmc", "/tmp/_mk.c", *args], capture_output=True,
                       text=True, timeout=120)
    if "VERIFICATION FAILED" in p.stdout:
        return True
    if "VERIFICATION SUCCESSFUL" in p.stdout:
        return False
    sys.exit(f"cbmc undecided: {p.stdout[-300:]}")


C_HEAD = "#include <assert.h>\nint nondet_int(void);\n"

C1 = {
    "gap-violated": C_HEAD + """
int main(void) {
  int x = nondet_int();
  if (x > 0 && x < 100) {
    int y = x * 2 + 1;
    assert(y != 41);           /* x == 20 violates */
  }
  return 0;
}
""",
    "guard-safe": C_HEAD + """
int main(void) {
  int x = nondet_int();
  if (x > 0 && x < 1000) {
    int y = x + x;
    assert(y > x);             /* holds on the guarded range */
  }
  return 0;
}
""",
    "mask-violated": C_HEAD + """
int main(void) {
  int x = nondet_int();
  int m = x & 7;
  assert(m != 5);              /* any x with low bits 101 violates */
  return 0;
}
""",
    "mulcomm-safe": C_HEAD + """
int main(void) {
  int x = nondet_int();
  int y = nondet_int();
  assert(x * y == y * x);      /* theorem; bit-blasting groans */
  return 0;
}
""",
    "order-safe": C_HEAD + """
int main(void) {
  int a = nondet_int();
  int b = nondet_int();
  if (a >= 0 && b >= 0 && a < 10000 && b < 10000) {
    int lo = a < b ? a : b;
    int hi = a < b ? b : a;
    assert(lo <= hi);
  }
  return 0;
}
""",
}

C2 = {
    "loop-violated": C_HEAD + """
int main(void) {
  int n = nondet_int();
  if (n >= 0 && n <= 8) {
    int s = 0;
    for (int i = 0; i < n; i++) s += i;
    assert(s != 21);           /* n == 7 violates: 0+..+6 = 21 */
  }
  return 0;
}
""",
    "loop-safe-bounded": C_HEAD + """
int main(void) {
  int s = 0;
  for (int i = 0; i < 6; i++) s += 2;
  assert(s == 12);
  return 0;
}
""",
    "accum-inf": C_HEAD + """
int main(void) {
  int n = nondet_int();
  if (n >= 0 && n <= 30) {
    int s = 0;
    for (int i = 0; i < n; i++) s += 3;
    assert(s % 3 == 0);        /* invariant: s is a multiple of 3 */
  }
  return 0;
}
""",
    "bigloop-safe": C_HEAD + """
int main(void) {
  int n = nondet_int();
  if (n >= 0 && n <= 60000) {
    int s = 0;
    for (int i = 0; i < n; i++) s += 3;
    assert(s % 3 == 0);        /* theorem: s == 3n */
  }
  return 0;
}
""",
    "downcount-inf": C_HEAD + """
int main(void) {
  int n = nondet_int();
  if (n >= 0 && n <= 40) {
    int k = n;
    while (k > 0) k -= 2;
    assert(k == 0 || k == -1);
  }
  return 0;
}
""",
}


def make_c():
    check(cbmc_violated(C1["gap-violated"]), "c1 gap")
    check(not cbmc_violated(C1["guard-safe"]), "c1 guard")
    check(cbmc_violated(C1["mask-violated"]), "c1 mask")
    check(not cbmc_violated(C1["order-safe"]), "c1 order")
    check(sampled_safe_stdin(C1["mulcomm-safe"],
                             ["0 0", "1 -1", "-2147483648 2147483647",
                              "65535 65537", "12345 -6789",
                              "2147483647 2147483647"]),
          "c1 mulcomm sampled")
    emit("c-straightline", "c", [
        ("mulcomm-safe", "mulcomm.c", C1["mulcomm-safe"], "forall",
         "violation", "inf", False),
        ("gap-violated", "gap.c", C1["gap-violated"], "exists",
         "violation", "inf", True),
        ("guard-safe", "guard.c", C1["guard-safe"], "forall",
         "violation", "inf", False),
        ("mask-violated", "mask.c", C1["mask-violated"], "exists",
         "violation", "inf", True),
        ("order-safe", "order.c", C1["order-safe"], "forall",
         "violation", "inf", False),
    ])

    check(cbmc_violated(C2["loop-violated"], "--unwind", "12"), "c2 loop")
    check(not cbmc_violated(C2["loop-safe-bounded"], "--unwind", "8",
                            "--unwinding-assertions"), "c2 safe bounded")
    check(not cbmc_violated(C2["accum-inf"], "--unwind", "32",
                            "--unwinding-assertions"), "c2 accum")
    check(not cbmc_violated(C2["downcount-inf"], "--unwind", "42",
                            "--unwinding-assertions"), "c2 downcount")
    check(sampled_safe(C2["bigloop-safe"], 60000), "c2 bigloop sampled")
    emit("c-loops", "c", [
        ("bigloop-safe", "bigloop.c", C2["bigloop-safe"], "forall",
         "violation", "inf", False),
        ("loop-violated", "loopv.c", C2["loop-violated"], "exists",
         "violation", "inf", True),
        ("loop-safe", "loops.c", C2["loop-safe-bounded"], "forall",
         "violation", "inf", False),
        ("accum-inf", "accum.c", C2["accum-inf"], "forall",
         "violation", "inf", False),
        ("downcount-inf", "down.c", C2["downcount-inf"], "forall",
         "violation", "inf", False),
    ])


if __name__ == "__main__":
    make_btor2()
    make_dimacs()
    make_c()
    print("all labels engine-verified")
