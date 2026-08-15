"""T: cone-of-influence reduction, btor2 -> btor2, generated whole.

Usage: T.py <program.btor2>  ->  reduced program on stdout

Keeps exactly the lines that can influence the bad properties: the
bads, every constraint (a constraint anywhere gates every bad), and
the transitive fan-in through operator arguments and through kept
states' init and next definitions. Node ids are preserved verbatim, so
a stimulus for the source drives the target unchanged — the identity
is the carry-back — and observables ("bad", "depth") are exact.
Output lines are dropped; comments are dropped; everything kept is
emitted byte-for-byte in original order.
"""

import sys

UNARY = {'not', 'inc', 'dec', 'neg', 'redand', 'redor', 'redxor',
         'slice', 'uext', 'sext'}
BINARY = {'and', 'or', 'xor', 'nand', 'nor', 'xnor', 'implies', 'iff',
          'eq', 'neq', 'ult', 'ulte', 'ugt', 'ugte', 'slt', 'slte',
          'sgt', 'sgte', 'add', 'sub', 'mul', 'udiv', 'urem',
          'sll', 'srl', 'sra', 'concat'}
CONSTS = {'const', 'constd', 'consth', 'zero', 'one', 'ones'}
LEAVES = {'input', 'state'}


def refs_of(op, t):
    """Node ids referenced by a parsed line (absolute values)."""
    if op in ('bad', 'constraint'):
        return [abs(int(t[2]))]
    if op in ('init', 'next'):
        return [abs(int(t[3])), abs(int(t[4]))]
    if op in CONSTS or op in LEAVES:
        return []
    if op in UNARY:
        return [abs(int(t[3]))]
    if op in BINARY:
        return [abs(int(t[3])), abs(int(t[4]))]
    if op == 'ite':
        return [abs(int(t[3])), abs(int(t[4])), abs(int(t[5]))]
    raise ValueError('unsupported op: ' + op)


def reduce_btor2(text):
    lines = []                   # (nid|None, op, tokens, raw)
    for raw in text.splitlines():
        body = raw.split(';', 1)[0].strip()
        if not body:
            continue
        t = body.split()
        lines.append((int(t[0]), t[1], t, body))

    init_of, next_of = {}, {}
    bads, constraints = [], []
    node_line = {}
    sort_line = {}
    for rec in lines:
        nid, op, t, raw = rec
        if op == 'sort':
            sort_line[nid] = rec
        elif op == 'init':
            init_of[abs(int(t[3]))] = rec
        elif op == 'next':
            next_of[abs(int(t[3]))] = rec
        elif op == 'bad':
            bads.append(rec)
        elif op == 'constraint':
            constraints.append(rec)
        elif op in ('output', 'fair', 'justice'):
            if op != 'output':
                raise ValueError('unsupported op: ' + op)
        else:
            node_line[nid] = rec

    keep_nodes = set()
    keep_sorts = set()
    work = []
    for rec in bads:
        work.extend(refs_of(rec[1], rec[2]))
    while work:
        nid = work.pop()
        if nid in keep_nodes:
            continue
        keep_nodes.add(nid)
        rec = node_line[nid]
        _, op, t, _ = rec
        keep_sorts.add(int(t[2]))
        work.extend(refs_of(op, t))
        if op == 'state':
            for extra in (init_of.get(nid), next_of.get(nid)):
                if extra is not None:
                    keep_sorts.add(int(extra[2][2]))
                    work.extend(r for r in refs_of(extra[1], extra[2])
                                if r != nid)

    out = []
    for rec in lines:
        nid, op, t, raw = rec
        if op == 'sort':
            if nid in keep_sorts:
                out.append(raw)
        elif op in ('init', 'next'):
            if abs(int(t[3])) in keep_nodes:
                out.append(raw)
        elif op == 'bad':
            out.append(raw)
        elif op == 'constraint':
            continue
        elif op == 'output':
            continue
        elif nid in keep_nodes:
            out.append(raw)
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8') as fh:
        sys.stdout.write(reduce_btor2(fh.read()))
