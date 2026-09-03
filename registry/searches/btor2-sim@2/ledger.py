"""The ledger beside the path (KERNEL.md §5), for a BTOR2 search.

Usage: ledger.py <program.btor2> <value.json>

Reads the program and the value the search wrote and reports what the
play bought, in bits, under the uniform measure the interpreter's
havoc rule fixes: at frame 0 every input and every uninitialized
state is free, at later frames every input and every next-less state.
An array-sorted free node contributes elem_bits * 2^index_bits.

- ``stimulus_bits``: free bits at frame 0 and at each later frame — the
  static profile that makes the other numbers legible.
- ``S_bits_min``: on a sampling partial reporting ``sampled`` failed
  trials, log2 of that count — the free lower bound on witness
  surprisal that every failed concrete trial tightens.
- ``B_bits``: on a universal claim ``all(k)``, the log-size of the
  stimulus space it exhausts, sum over frames 0..k; ``"inf"`` at
  bound inf.
- ``witness_bits``: on a witness of depth d, the log-size of the space
  the witness was found in (frames 0..d) — a trivial upper bound on S.

Profiling only: recorded beside the path, never ranked, never a grade.
Two runs emit identical bytes.
"""

import json
import math
import sys


def parse(path):
    sorts, width, kind, init, nxt = {}, {}, {}, set(), set()
    with open(path) as fh:
        for raw in fh:
            line = raw.split(';', 1)[0].strip()
            if not line:
                continue
            t = line.split()
            op = t[1]
            if op == 'sort':
                if t[2] == 'bitvec':
                    sorts[int(t[0])] = int(t[3])
                elif t[2] == 'array':
                    sorts[int(t[0])] = ('a', sorts[int(t[3])],
                                        sorts[int(t[4])])
                continue
            if op == 'init':
                init.add(int(t[3]))
                continue
            if op == 'next':
                nxt.add(int(t[3]))
                continue
            if op in ('input', 'state'):
                nid = int(t[0])
                width[nid] = sorts[int(t[2])]
                kind[nid] = op
    return width, kind, init, nxt


def bits(w):
    if isinstance(w, tuple):
        return bits(w[2]) << (w[1] if not isinstance(w[1], tuple) else 0)
    return w


def free_bits(model, t):
    width, kind, init, nxt = model
    total = 0
    for nid, w in width.items():
        if kind[nid] == 'input':
            total += bits(w)
        elif (t == 0 and nid not in init) or (t > 0 and nid not in nxt):
            total += bits(w)
    return total


def main():
    model = parse(sys.argv[1])
    with open(sys.argv[2], encoding='utf-8') as fh:
        value = json.load(fh)
    f0, f1 = free_bits(model, 0), free_bits(model, 1)
    out = {"stimulus_bits": {"frame0": f0, "later": f1}}
    kind = value.get("kind")
    if kind == "partial":
        n = value.get("progress", {}).get("sampled")
        if isinstance(n, int) and n > 0:
            out["S_bits_min"] = round(math.log2(n), 2)
    elif kind == "all":
        b = value.get("bound")
        if b == "inf":
            out["B_bits"] = "inf"
        elif isinstance(b, int) and b >= 0:
            out["B_bits"] = f0 + b * f1
    elif kind == "witness":
        d = value.get("depth")
        if isinstance(d, int) and d >= 0:
            out["witness_bits"] = f0 + d * f1
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
