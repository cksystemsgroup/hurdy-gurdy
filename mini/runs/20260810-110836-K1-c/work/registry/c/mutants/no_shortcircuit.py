#!/usr/bin/env python3
"""Deterministic interpreter for a small subset of C: int-only variables,
if/else, for/while, assert, and the usual expression grammar. nondet_int()
reads from the supplied input stream. observables: violation (bool),
depth (loop iterations executed)."""
import json
import re
import sys

MASK = 0xFFFFFFFF
SIGN = 0x80000000


def i32(v):
    v &= MASK
    return v - 0x100000000 if v & SIGN else v


def c_div(a, b):
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return i32(q)


def c_mod(a, b):
    return i32(a - c_div(a, b) * b)


def apply_bin(op, a, b):
    if op == '+':
        return i32(a + b)
    if op == '-':
        return i32(a - b)
    if op == '*':
        return i32(a * b)
    if op == '/':
        return c_div(a, b)
    if op == '%':
        return c_mod(a, b)
    if op == '&':
        return i32((a & b) & MASK)
    if op == '|':
        return i32((a | b) & MASK)
    if op == '^':
        return i32((a ^ b) & MASK)
    if op == '<<':
        return i32((a << b) & MASK)
    if op == '>>':
        return i32(a >> b)
    if op == '<':
        return 1 if a < b else 0
    if op == '>':
        return 1 if a > b else 0
    if op == '<=':
        return 1 if a <= b else 0
    if op == '>=':
        return 1 if a >= b else 0
    if op == '==':
        return 1 if a == b else 0
    if op == '!=':
        return 1 if a != b else 0
    raise ValueError(f'bad op {op}')


def extract_main_body(src):
    src_nc = re.sub(r'/\*.*?\*/', ' ', src, flags=re.DOTALL)
    src_nc = re.sub(r'//[^\n]*', ' ', src_nc)
    m = re.search(r'\bint\s+main\s*\(\s*(?:void)?\s*\)\s*\{', src_nc)
    if not m:
        raise ValueError('no main() found')
    i = m.end()
    depth, j = 1, m.end()
    while depth > 0:
        c = src_nc[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        j += 1
    return src_nc[i:j - 1]


TOKEN_RE = re.compile(r"""
    (?P<NUM>\d+)
  | (?P<ID>[A-Za-z_]\w*)
  | (?P<OP><<=|>>=|==|!=|<=|>=|&&|\|\||\+\+|--|\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<|>>|[-+*/%&|^~!<>=(){}\[\];,?:])
  | (?P<WS>\s+)
""", re.VERBOSE)


def tokenize(s):
    toks, pos, n = [], 0, len(s)
    while pos < n:
        m = TOKEN_RE.match(s, pos)
        if not m:
            raise ValueError(f'bad token at {pos}: {s[pos:pos + 20]!r}')
        pos = m.end()
        if m.lastgroup != 'WS':
            toks.append((m.lastgroup, m.group()))
    toks.append(('EOF', ''))
    return toks


COMPOUND = {'+=': '+', '-=': '-', '*=': '*', '/=': '/', '%=': '%',
            '&=': '&', '|=': '|', '^=': '^', '<<=': '<<', '>>=': '>>'}


class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def val(self):
        return self.toks[self.i][1]

    def advance(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, v):
        if self.val() != v:
            raise ValueError(f'expected {v!r} got {self.val()!r}')
        return self.advance()

    def parse_block_stmts(self):
        stmts = []
        while self.val() != '':
            stmts.append(self.parse_stmt())
        return stmts

    def parse_stmt(self):
        v = self.val()
        if v == '{':
            self.advance()
            stmts = []
            while self.val() != '}':
                stmts.append(self.parse_stmt())
            self.advance()
            return ('block', stmts)
        if v == 'if':
            self.advance()
            self.expect('(')
            cond = self.parse_expr()
            self.expect(')')
            then_s = self.parse_stmt()
            else_s = None
            if self.val() == 'else':
                self.advance()
                else_s = self.parse_stmt()
            return ('if', cond, then_s, else_s)
        if v == 'for':
            self.advance()
            self.expect('(')
            init = None if self.val() == ';' else self.parse_for_init()
            self.expect(';')
            cond = None if self.val() == ';' else self.parse_expr()
            self.expect(';')
            update = None if self.val() == ')' else self.parse_expr()
            self.expect(')')
            body = self.parse_stmt()
            return ('for', init, cond, update, body)
        if v == 'while':
            self.advance()
            self.expect('(')
            cond = self.parse_expr()
            self.expect(')')
            body = self.parse_stmt()
            return ('while', cond, body)
        if v == 'int':
            self.advance()
            name = self.advance()[1]
            expr = None
            if self.val() == '=':
                self.advance()
                expr = self.parse_expr()
            self.expect(';')
            return ('decl', name, expr)
        if v == 'assert':
            self.advance()
            self.expect('(')
            expr = self.parse_expr()
            self.expect(')')
            self.expect(';')
            return ('assert', expr)
        if v == 'return':
            self.advance()
            expr = None if self.val() == ';' else self.parse_expr()
            self.expect(';')
            return ('return', expr)
        if v == ';':
            self.advance()
            return ('empty',)
        expr = self.parse_expr()
        self.expect(';')
        return ('expr', expr)

    def parse_for_init(self):
        if self.val() == 'int':
            self.advance()
            name = self.advance()[1]
            self.expect('=')
            expr = self.parse_expr()
            return ('decl', name, expr)
        return ('expr', self.parse_expr())

    def parse_expr(self):
        return self.parse_assign()

    def parse_assign(self):
        left = self.parse_ternary()
        v = self.val()
        if v == '=':
            self.advance()
            right = self.parse_assign()
            if left[0] != 'var':
                raise ValueError('bad assignment target')
            return ('assign', left[1], right)
        if v in COMPOUND:
            self.advance()
            right = self.parse_assign()
            if left[0] != 'var':
                raise ValueError('bad assignment target')
            return ('cassign', COMPOUND[v], left[1], right)
        return left

    def parse_ternary(self):
        cond = self.parse_logic_or()
        if self.val() == '?':
            self.advance()
            a = self.parse_expr()
            self.expect(':')
            b = self.parse_ternary()
            return ('ternary', cond, a, b)
        return cond

    def parse_logic_or(self):
        left = self.parse_logic_and()
        while self.val() == '||':
            self.advance()
            left = ('logic', '||', left, self.parse_logic_and())
        return left

    def parse_logic_and(self):
        left = self.parse_bit_or()
        while self.val() == '&&':
            self.advance()
            left = ('logic', '&&', left, self.parse_bit_or())
        return left

    def parse_bit_or(self):
        left = self.parse_bit_xor()
        while self.val() == '|':
            self.advance()
            left = ('bin', '|', left, self.parse_bit_xor())
        return left

    def parse_bit_xor(self):
        left = self.parse_bit_and()
        while self.val() == '^':
            self.advance()
            left = ('bin', '^', left, self.parse_bit_and())
        return left

    def parse_bit_and(self):
        left = self.parse_equality()
        while self.val() == '&':
            self.advance()
            left = ('bin', '&', left, self.parse_equality())
        return left

    def parse_equality(self):
        left = self.parse_relational()
        while self.val() in ('==', '!='):
            op = self.advance()[1]
            left = ('bin', op, left, self.parse_relational())
        return left

    def parse_relational(self):
        left = self.parse_shift()
        while self.val() in ('<', '>', '<=', '>='):
            op = self.advance()[1]
            left = ('bin', op, left, self.parse_shift())
        return left

    def parse_shift(self):
        left = self.parse_additive()
        while self.val() in ('<<', '>>'):
            op = self.advance()[1]
            left = ('bin', op, left, self.parse_additive())
        return left

    def parse_additive(self):
        left = self.parse_mult()
        while self.val() in ('+', '-'):
            op = self.advance()[1]
            left = ('bin', op, left, self.parse_mult())
        return left

    def parse_mult(self):
        left = self.parse_unary()
        while self.val() in ('*', '/', '%'):
            op = self.advance()[1]
            left = ('bin', op, left, self.parse_unary())
        return left

    def parse_unary(self):
        v = self.val()
        if v in ('-', '!', '~', '+'):
            self.advance()
            return ('unop', v, self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self):
        e = self.parse_primary()
        if self.val() in ('++', '--'):
            op = self.advance()[1]
            if e[0] != 'var':
                raise ValueError('bad postfix target')
            return ('postop', op, e[1])
        return e

    def parse_primary(self):
        k, v = self.advance()
        if k == 'NUM':
            return ('num', int(v))
        if k == 'ID':
            if self.val() == '(':
                self.advance()
                args = []
                if self.val() != ')':
                    args.append(self.parse_expr())
                    while self.val() == ',':
                        self.advance()
                        args.append(self.parse_expr())
                self.expect(')')
                return ('call', v, args)
            return ('var', v)
        if v == '(':
            e = self.parse_expr()
            self.expect(')')
            return e
        raise ValueError(f'unexpected token {k} {v!r}')


class AssertFail(Exception):
    pass


class ReturnSignal(Exception):
    pass


class Interp:
    def __init__(self, nondet_vals):
        self.env = {}
        self.nondet_vals = nondet_vals
        self.idx = 0
        self.steps = 0
        self.violation = False

    def next_nondet(self):
        v = self.nondet_vals[self.idx] if self.idx < len(self.nondet_vals) else 0
        self.idx += 1
        return i32(v)

    def eval(self, node):
        kind = node[0]
        if kind == 'num':
            return i32(node[1])
        if kind == 'var':
            return self.env[node[1]]
        if kind == 'call':
            if node[1] == 'nondet_int':
                return self.next_nondet()
            raise ValueError(f'unknown function {node[1]}')
        if kind == 'unop':
            op, v = node[1], self.eval(node[2])
            if op == '-':
                return i32(-v)
            if op == '+':
                return v
            if op == '!':
                return 1 if v == 0 else 0
            if op == '~':
                return i32(~v)
        if kind == 'postop':
            old = self.env[node[2]]
            self.env[node[2]] = i32(old + (1 if node[1] == '++' else -1))
            return old
        if kind == 'bin':
            return apply_bin(node[1], self.eval(node[2]), self.eval(node[3]))
        if kind == 'logic':
            a = self.eval(node[2])
            b = self.eval(node[3])
            if node[1] == '&&':
                return 1 if (a != 0 and b != 0) else 0
            return 1 if (a != 0 or b != 0) else 0
        if kind == 'ternary':
            return self.eval(node[2]) if self.eval(node[1]) != 0 else self.eval(node[3])
        if kind == 'assign':
            v = self.eval(node[2])
            self.env[node[1]] = v
            return v
        if kind == 'cassign':
            v = apply_bin(node[1], self.env[node[2]], self.eval(node[3]))
            self.env[node[2]] = v
            return v
        raise ValueError(f'bad expr node {node}')

    def exec_stmt(self, stmt):
        kind = stmt[0]
        if kind == 'block':
            for s in stmt[1]:
                self.exec_stmt(s)
        elif kind == 'if':
            if self.eval(stmt[1]) != 0:
                self.exec_stmt(stmt[2])
            elif stmt[3] is not None:
                self.exec_stmt(stmt[3])
        elif kind == 'for':
            init, cond, update, body = stmt[1], stmt[2], stmt[3], stmt[4]
            if init is not None:
                self.exec_stmt(init)
            while cond is None or self.eval(cond) != 0:
                self.steps += 1
                self.exec_stmt(body)
                if update is not None:
                    self.eval(update)
        elif kind == 'while':
            cond, body = stmt[1], stmt[2]
            while self.eval(cond) != 0:
                self.steps += 1
                self.exec_stmt(body)
        elif kind == 'decl':
            self.env[stmt[1]] = self.eval(stmt[2]) if stmt[2] is not None else 0
        elif kind == 'assert':
            if self.eval(stmt[1]) == 0:
                self.violation = True
                raise AssertFail()
        elif kind == 'return':
            raise ReturnSignal()
        elif kind == 'expr':
            self.eval(stmt[1])
        elif kind == 'empty':
            pass
        else:
            raise ValueError(f'bad stmt {stmt}')


def parse_program(src):
    body_src = extract_main_body(src)
    return Parser(tokenize(body_src)).parse_block_stmts()


def run_program(src, nondet_vals):
    stmts = parse_program(src)
    it = Interp(nondet_vals)
    try:
        for s in stmts:
            it.exec_stmt(s)
    except (AssertFail, ReturnSignal):
        pass
    return {"violation": it.violation, "depth": it.steps}


def main():
    program_path, input_path = sys.argv[1], sys.argv[2]
    with open(program_path, encoding='utf-8') as fh:
        src = fh.read()
    with open(input_path, encoding='utf-8') as fh:
        inp = json.load(fh)
    nondet_vals = inp.get('nondet', []) if isinstance(inp, dict) else list(inp)
    obs = run_program(src, nondet_vals)
    print(json.dumps(obs, sort_keys=True))


if __name__ == '__main__':
    main()
