"""A second, independent front end for the same small C subset as
registry/c/interp.py — its own lexer and recursive-descent parser — feeding
a Z3 bitvector symbolic executor instead of concrete evaluation. Loops are
unrolled with explicit state-freezing (ite merge) up to a bound; a
"residual" formula captures whether the loop guard could still be true
after that many iterations (the analogue of cbmc's unwinding assertion).
Kept deliberately separate from the cbmc-based solver and from the
language's own interpreter so a verdict from each rests on a different
codebase."""
import re

import z3

z3.set_param('smt.random_seed', 0)
z3.set_param('sat.random_seed', 0)

MASK = 0xFFFFFFFF
COMPOUND = {'+=': '+', '-=': '-', '*=': '*', '/=': '/', '%=': '%',
            '&=': '&', '|=': '|', '^=': '^', '<<=': '<<', '>>=': '>>'}

TOKEN_RE = re.compile(r"""
    (?P<NUM>\d+)
  | (?P<ID>[A-Za-z_]\w*)
  | (?P<OP><<=|>>=|==|!=|<=|>=|&&|\|\||\+\+|--|\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<|>>|[-+*/%&|^~!<>=(){}\[\];,?:])
  | (?P<WS>\s+)
""", re.VERBOSE)


def extract_main_body(src):
    nc = re.sub(r'/\*.*?\*/', ' ', src, flags=re.DOTALL)
    nc = re.sub(r'//[^\n]*', ' ', nc)
    m = re.search(r'\bint\s+main\s*\(\s*(?:void)?\s*\)\s*\{', nc)
    if not m:
        raise ValueError('no main() found')
    depth, j = 1, m.end()
    while depth > 0:
        if nc[j] == '{':
            depth += 1
        elif nc[j] == '}':
            depth -= 1
        j += 1
    return nc[m.end():j - 1]


def lex(s):
    toks, pos, n = [], 0, len(s)
    while pos < n:
        m = TOKEN_RE.match(s, pos)
        if not m:
            raise ValueError(f'bad token at {pos}')
        pos = m.end()
        if m.lastgroup != 'WS':
            toks.append((m.lastgroup, m.group()))
    toks.append(('EOF', ''))
    return toks


class Parser:
    """Recursive descent over the standard C precedence ladder, restricted
    to int arithmetic/bitwise/logic ops, if/for/while, assert, decl."""

    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def cur(self):
        return self.t[self.i][1]

    def take(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def eat(self, v):
        if self.cur() != v:
            raise ValueError(f'expected {v!r}, found {self.cur()!r}')
        return self.take()

    def program(self):
        out = []
        while self.cur() != '':
            out.append(self.stmt())
        return out

    def stmt(self):
        v = self.cur()
        if v == '{':
            self.take()
            body = []
            while self.cur() != '}':
                body.append(self.stmt())
            self.take()
            return ('block', body)
        if v == 'if':
            self.take()
            self.eat('(')
            c = self.expr()
            self.eat(')')
            th = self.stmt()
            el = None
            if self.cur() == 'else':
                self.take()
                el = self.stmt()
            return ('if', c, th, el)
        if v == 'for':
            self.take()
            self.eat('(')
            init = None if self.cur() == ';' else self.for_init()
            self.eat(';')
            cond = None if self.cur() == ';' else self.expr()
            self.eat(';')
            upd = None if self.cur() == ')' else self.expr()
            self.eat(')')
            return ('for', init, cond, upd, self.stmt())
        if v == 'while':
            self.take()
            self.eat('(')
            c = self.expr()
            self.eat(')')
            return ('while', c, self.stmt())
        if v == 'int':
            self.take()
            name = self.take()[1]
            e = None
            if self.cur() == '=':
                self.take()
                e = self.expr()
            self.eat(';')
            return ('decl', name, e)
        if v == 'assert':
            self.take()
            self.eat('(')
            e = self.expr()
            self.eat(')')
            self.eat(';')
            return ('assert', e)
        if v == 'return':
            self.take()
            e = None if self.cur() == ';' else self.expr()
            self.eat(';')
            return ('return', e)
        if v == ';':
            self.take()
            return ('empty',)
        e = self.expr()
        self.eat(';')
        return ('expr', e)

    def for_init(self):
        if self.cur() == 'int':
            self.take()
            name = self.take()[1]
            self.eat('=')
            return ('decl', name, self.expr())
        return ('expr', self.expr())

    def expr(self):
        return self.assign()

    def assign(self):
        left = self.ternary()
        v = self.cur()
        if v == '=':
            self.take()
            if left[0] != 'var':
                raise ValueError('bad assignment target')
            return ('assign', left[1], self.assign())
        if v in COMPOUND:
            self.take()
            if left[0] != 'var':
                raise ValueError('bad assignment target')
            return ('cassign', COMPOUND[v], left[1], self.assign())
        return left

    def ternary(self):
        c = self.lor()
        if self.cur() == '?':
            self.take()
            a = self.expr()
            self.eat(':')
            return ('ternary', c, a, self.ternary())
        return c

    def _binlevel(self, sub, ops, tag='bin'):
        left = sub()
        while self.cur() in ops:
            op = self.take()[1]
            left = (tag, op, left, sub())
        return left

    def lor(self):
        return self._binlevel(self.land, ('||',), 'logic')

    def land(self):
        return self._binlevel(self.bor, ('&&',), 'logic')

    def bor(self):
        return self._binlevel(self.bxor, ('|',))

    def bxor(self):
        return self._binlevel(self.band, ('^',))

    def band(self):
        return self._binlevel(self.eq, ('&',))

    def eq(self):
        return self._binlevel(self.rel, ('==', '!='))

    def rel(self):
        return self._binlevel(self.shift, ('<', '>', '<=', '>='))

    def shift(self):
        return self._binlevel(self.add, ('<<', '>>'))

    def add(self):
        return self._binlevel(self.mul, ('+', '-'))

    def mul(self):
        return self._binlevel(self.unary, ('*', '/', '%'))

    def unary(self):
        if self.cur() in ('-', '!', '~', '+'):
            op = self.take()[1]
            return ('unop', op, self.unary())
        return self.postfix()

    def postfix(self):
        e = self.primary()
        if self.cur() in ('++', '--'):
            op = self.take()[1]
            if e[0] != 'var':
                raise ValueError('bad postfix target')
            return ('postop', op, e[1])
        return e

    def primary(self):
        k, v = self.take()
        if k == 'NUM':
            return ('num', int(v))
        if k == 'ID':
            if self.cur() == '(':
                self.take()
                args = []
                if self.cur() != ')':
                    args.append(self.expr())
                    while self.cur() == ',':
                        self.take()
                        args.append(self.expr())
                self.eat(')')
                return ('call', v, args)
            return ('var', v)
        if v == '(':
            e = self.expr()
            self.eat(')')
            return e
        raise ValueError(f'unexpected {k} {v!r}')


def parse_program(src):
    return Parser(lex(extract_main_body(src))).program()


# ------------------------------------------------------------ symbolic exec

def bv(n):
    return z3.BitVecVal(n & MASK, 32)


def truthy(x):
    return x != bv(0)


def as_bv(boolexpr):
    return z3.If(boolexpr, bv(1), bv(0))


class Executor:
    """Walks the AST maintaining (env: name->BitVec32, pc: path condition).
    if/else forks pc for each branch and rejoins env via ite. A loop is
    unrolled up to `budget` times with env frozen (ite-guarded) once the
    guard goes false, so an assert reached only on iteration i is correctly
    gated by pc AND (guard held through iteration i)."""

    def __init__(self):
        self.nondet_calls = []  # [(BitVec, pc_at_call), ...] in call order
        self.violations = []    # [pc_at_assert AND (expr == 0), ...]
        self.residuals = []     # [pc_at_loop_exit AND (guard still true), ...]

    def new_nondet(self, pc):
        v = z3.BitVec(f'nd{len(self.nondet_calls)}', 32)
        self.nondet_calls.append((v, pc))
        return v

    def eval_expr(self, node, env, pc):
        k = node[0]
        if k == 'num':
            return bv(node[1])
        if k == 'var':
            return env[node[1]]
        if k == 'call':
            if node[1] != 'nondet_int':
                raise ValueError(f'unknown call {node[1]}')
            return self.new_nondet(pc)
        if k == 'unop':
            op, v = node[1], self.eval_expr(node[2], env, pc)
            return {'-': -v, '+': v, '!': as_bv(z3.Not(truthy(v))),
                    '~': ~v}[op]
        if k == 'postop':
            name = node[2]
            old = env[name]
            env[name] = old + (bv(1) if node[1] == '++' else bv(-1))
            return old
        if k == 'bin':
            return apply_bin(node[1], self.eval_expr(node[2], env, pc),
                              self.eval_expr(node[3], env, pc))
        if k == 'logic':
            a = truthy(self.eval_expr(node[2], env, pc))
            b = truthy(self.eval_expr(node[3], env, pc))
            return as_bv(z3.And(a, b) if node[1] == '&&' else z3.Or(a, b))
        if k == 'ternary':
            c = truthy(self.eval_expr(node[1], env, pc))
            return z3.If(c, self.eval_expr(node[2], env, pc),
                         self.eval_expr(node[3], env, pc))
        if k == 'assign':
            v = self.eval_expr(node[2], env, pc)
            env[node[1]] = v
            return v
        if k == 'cassign':
            v = apply_bin(node[1], env[node[2]], self.eval_expr(node[3], env, pc))
            env[node[2]] = v
            return v
        raise ValueError(f'bad expr {node}')

    def exec_stmts(self, stmts, env, pc, budget):
        """Returns (env, pc) — pc narrows after a loop that may not have
        finished within `budget`: anything sequenced after it is only
        reachable on paths where the loop actually terminated in time."""
        for s in stmts:
            env, pc = self.exec_stmt(s, env, pc, budget)
        return env, pc

    def exec_stmt(self, stmt, env, pc, budget):
        k = stmt[0]
        if k == 'block':
            return self.exec_stmts(stmt[1], env, pc, budget)
        if k == 'decl':
            env = dict(env)
            env[stmt[1]] = (self.eval_expr(stmt[2], env, pc)
                            if stmt[2] is not None else bv(0))
            return env, pc
        if k == 'expr':
            env = dict(env)
            self.eval_expr(stmt[1], env, pc)
            return env, pc
        if k == 'assert':
            v = self.eval_expr(stmt[1], dict(env), pc)
            self.violations.append(z3.And(pc, v == bv(0)))
            return env, pc
        if k in ('return', 'empty'):
            return env, pc
        if k == 'if':
            cond = truthy(self.eval_expr(stmt[1], dict(env), pc))
            then_env, _ = self.exec_stmt(stmt[2], dict(env), z3.And(pc, cond), budget)
            else_env, _ = (self.exec_stmt(stmt[3], dict(env), z3.And(pc, z3.Not(cond)), budget)
                          if stmt[3] is not None else (dict(env), pc))
            merged = {}
            for name in env:
                merged[name] = z3.If(cond, then_env.get(name, env[name]),
                                     else_env.get(name, env[name]))
            return merged, pc
        if k in ('for', 'while'):
            return self.unroll(stmt, env, pc, budget)
        raise ValueError(f'bad stmt {stmt}')

    def unroll(self, stmt, env, pc, budget):
        if stmt[0] == 'for':
            init, cond_e, upd_e, body = stmt[1], stmt[2], stmt[3], stmt[4]
            if init is not None:
                env, pc = self.exec_stmt(init, env, pc, budget)
        else:
            cond_e, upd_e, body = stmt[1], None, stmt[2]
        for _ in range(budget):
            c = (truthy(self.eval_expr(cond_e, dict(env), pc))
                 if cond_e is not None else z3.BoolVal(True))
            body_pc = z3.And(pc, c)
            body_env, _ = self.exec_stmt(body, dict(env), body_pc, budget)
            if upd_e is not None:
                self.eval_expr(upd_e, body_env, body_pc)
            merged = {}
            for name in env:
                merged[name] = z3.If(c, body_env.get(name, env[name]), env[name])
            env = merged
        final_c = (truthy(self.eval_expr(cond_e, dict(env), pc))
                  if cond_e is not None else z3.BoolVal(True))
        self.residuals.append(z3.And(pc, final_c))
        return env, z3.And(pc, z3.Not(final_c))


def apply_bin(op, a, b):
    if op == '+':
        return a + b
    if op == '-':
        return a - b
    if op == '*':
        return a * b
    if op == '/':
        return a / b
    if op == '%':
        return z3.SRem(a, b)
    if op == '&':
        return a & b
    if op == '|':
        return a | b
    if op == '^':
        return a ^ b
    if op == '<<':
        return a << b
    if op == '>>':
        return a >> b
    if op == '<':
        return as_bv(a < b)
    if op == '>':
        return as_bv(a > b)
    if op == '<=':
        return as_bv(a <= b)
    if op == '>=':
        return as_bv(a >= b)
    if op == '==':
        return as_bv(a == b)
    if op == '!=':
        return as_bv(a != b)
    raise ValueError(f'bad op {op}')


def run_bounded(stmts, budget):
    """Symbolically execute the whole program with every loop unrolled up
    to `budget` iterations. Returns (nondet_calls, violation_formula,
    residual_formula) — residual is UNSAT iff `budget` fully covers every
    loop in every reachable execution (a complete model, not just bounded)."""
    ex = Executor()
    ex.exec_stmts(stmts, {}, z3.BoolVal(True), budget)
    viol = z3.Or(*ex.violations) if ex.violations else z3.BoolVal(False)
    resid = z3.Or(*ex.residuals) if ex.residuals else z3.BoolVal(False)
    return ex.nondet_calls, viol, resid


def bound_schedule(wall_s):
    # Measured directly against bigloop.c: 256 unrolled iterations resolve
    # in ~1-2s with stable timing; 512 already swings 13-23s run to run
    # (z3's own search variance, not this budget) — 256 is the largest
    # bound worth trusting for a byte-identical repeat.
    n_max = 256 if wall_s >= 20 else 64 if wall_s >= 5 else 16
    sched, n = [], 0
    while True:
        sched.append(n)
        if n >= n_max:
            return sched
        n = 1 if n == 0 else n * 2


def extract_witness(nondet_calls, model):
    payload = []
    for var, pc in nondet_calls:
        if z3.is_true(model.eval(pc, model_completion=True)):
            payload.append(model.eval(var, model_completion=True).as_signed_long())
    return payload
