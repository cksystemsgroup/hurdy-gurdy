"""BOUND MUTANT (off by one: every image one frame late, back adjusted to stay its lower adjoint)

btor2--c bound map (lam_bound): an ask carried forward, a claim
carried back, across the frame granularity the translation changes
(KERNEL.md §2, §5).

The translation's first line is the header

    // btor2--c frame: n0=<prologue nodes> n=<nodes per iteration> bad=<offset>

written by T.py from the frame structure it emits (the same numbers
the stimulus map and the witness carry-back recompute from the btor2
program). A bad at btor2 frame t is observed by c's interpreter at C
frame n0 + n*t + bad, so

    fwd(t)  = n0 + n*t + bad            (inf -> inf)
    back(k) = the largest t with fwd(t) <= k, i.e. (k - n0 - bad) // n,
              null when k < fwd(0)      (inf -> inf)

fwd is strictly monotone and back is its lower adjoint: back(fwd(t))
= t and fwd(back(k)) <= k < fwd(back(k) + 1) wherever back answers. A
C claim "no bad within k' frames" therefore comes home as the btor2
claim "no bad within back(k') frames" — every btor2 frame whose bad
check the C bound covers, and not one more — and a btor2 ask of t
frames goes out as the C ask fwd(t), the frame at which a bad at t
would be observed. A program without the header is refused (rc 1):
the map reads only translations this pair wrote.

Usage: lam_bound.py <program.c> fwd|back <bound> -> JSON bound on stdout
       (a non-negative integer, "inf", or null)
"""

import json
import re
import sys

HEADER = re.compile(r"^// btor2--c frame: n0=(\d+) n=(\d+) bad=(\d+)\s*$")


def frame_structure(path):
    with open(path, encoding="utf-8") as fh:
        first = fh.readline()
    m = HEADER.match(first)
    if m is None:
        raise ValueError("no btor2--c frame header on the first line")
    n0, n, bad = (int(x) for x in m.groups())
    if n < 1 or bad < 1 or bad >= n:
        raise ValueError("malformed frame header")
    return n0, n, bad


def fwd(n0, n, bad, t):
    return n0 + n * t + bad + 1            # MUTANT: one late


def back(n0, n, bad, k):
    if k < n0 + bad + 1:
        return None
    return (k - n0 - bad - 1) // n


def main():
    if len(sys.argv) != 4 or sys.argv[2] not in ("fwd", "back"):
        print("usage: lam_bound.py <program.c> fwd|back <bound>",
              file=sys.stderr)
        return 2
    way, bound = sys.argv[2], sys.argv[3]
    try:
        n0, n, bad = frame_structure(sys.argv[1])
        if bound == "inf":
            out = "inf"
        else:
            b = int(bound)
            if b < 0:
                raise ValueError("negative bound")
            out = fwd(n0, n, bad, b) if way == "fwd" else back(n0, n, bad, b)
    except (OSError, ValueError) as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
