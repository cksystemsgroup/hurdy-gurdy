"""The ledger beside the path (KERNEL.md §5) for btor2-pdr.

Usage: ledger.py <program.btor2> <value.json> -> ledger JSON

What the play bought, in bits, under the uniform measure the
interpreter's havoc rule fixes — at frame 0 every input and every
uninitialized state is free, later every input and every next-less
state — read off the program and the value the search wrote:

- ``stimulus_bits``: the free bits at frame 0 and at each later frame;
- ``B_bits``: on a universal claim all(k), the log-size of the stimulus
  space it exhausts (frames 0..k), ``"inf"`` at bound inf;
- ``witness_bits``: on a witness of depth d, the log-size of the space
  it was found in (frames 0..d);
- ``L_bytes`` and ``clauses``: on a certificate, its zlib-compressed
  length (level 9, canonical JSON) and its clause count — with B/L the
  compression a proof achieves over exhaustive checking;
- ``bound_reached``: on a partial, the typed core the kernel orders on.

Profiling only, never ranked, never a grade; two runs emit the same
bytes.
"""

import json
import sys
import zlib


def scan(path):
    sorts, free0, later = {}, 0, 0
    inits, nexts, decl = set(), set(), []
    with open(path, encoding='utf-8') as fh:
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
                    sorts[int(t[0])] = sorts[int(t[4])] << sorts[int(t[3])]
            elif op == 'init':
                inits.add(int(t[3]))
            elif op == 'next':
                nexts.add(int(t[3]))
            elif op in ('input', 'state'):
                decl.append((int(t[0]), op, sorts.get(int(t[2]), 0)))
    for nid, op, w in decl:
        if op == 'input':
            free0 += w
            later += w
        else:
            if nid not in inits:
                free0 += w
            if nid not in nexts:
                later += w
    return free0, later


def main():
    f0, f1 = scan(sys.argv[1])
    with open(sys.argv[2], encoding='utf-8') as fh:
        value = json.load(fh)
    out = {"stimulus_bits": {"frame0": f0, "later": f1}}
    kind = value.get("kind")
    if kind == "all":
        b = value.get("bound")
        if b == "inf":
            out["B_bits"] = "inf"
        elif isinstance(b, int) and b >= 0:
            out["B_bits"] = f0 + b * f1
        cert = value.get("cert")
        if isinstance(cert, dict) and cert.get("schema") == "clauses":
            payload = cert.get("payload") or {}
            text = json.dumps(payload, sort_keys=True,
                              separators=(',', ':')).encode('utf-8')
            out["L_bytes"] = len(zlib.compress(text, 9))
            out["clauses"] = len(payload.get("clauses") or [])
    elif kind == "witness":
        d = value.get("depth")
        if isinstance(d, int) and d >= 0:
            out["witness_bits"] = f0 + d * f1
    elif kind == "partial":
        br = (value.get("progress") or {}).get("bound_reached")
        if isinstance(br, int):
            out["bound_reached"] = br
    print(json.dumps(out, sort_keys=True))


if __name__ == '__main__':
    main()
