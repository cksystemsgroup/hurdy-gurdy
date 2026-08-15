"""Negative control: shifts every node id by one — the machine is
isomorphic, but the stimulus contract (ids name the inputs) breaks."""
import sys

UNARY = {'not', 'inc', 'dec', 'neg', 'redand', 'redor', 'redxor',
         'slice', 'uext', 'sext'}
BINARY = {'and', 'or', 'xor', 'nand', 'nor', 'xnor', 'implies', 'iff',
          'eq', 'neq', 'ult', 'ulte', 'ugt', 'ugte', 'slt', 'slte',
          'sgt', 'sgte', 'add', 'sub', 'mul', 'udiv', 'urem',
          'sll', 'srl', 'sra', 'concat'}
CONSTS = {'const', 'constd', 'consth', 'zero', 'one', 'ones'}


def sh(tok):
    r = int(tok)
    return str(r + 1 if r >= 0 else r - 1)


def shift_positions(op, n):
    if op == 'sort':
        return [0]
    if op in ('input', 'state') or op in CONSTS:
        return [0, 2]
    if op in ('bad', 'constraint'):
        return [0, 2]
    if op in ('init', 'next'):
        return [0, 2, 3, 4]
    if op in UNARY:
        return [0, 2, 3]
    if op in BINARY:
        return [0, 2, 3, 4]
    if op == 'ite':
        return [0, 2, 3, 4, 5]
    raise ValueError('unsupported op: ' + op)


out = []
with open(sys.argv[1], encoding='utf-8') as fh:
    for raw in fh:
        body = raw.split(';', 1)[0].strip()
        if not body:
            continue
        t = body.split()
        op = t[1]
        if op == 'output':
            continue
        for p in shift_positions(op, len(t)):
            t[p] = sh(t[p])
        out.append(' '.join(t))
print('\n'.join(out))
