"""A hand-rolled compile-head: parses the restricted C subset used by
this domain's benchmarks (int decls, if/else, for/while with a
literal or nondet-but-guarded trip count, +=/-=, assert, nondet_int())
straight into z3 BitVec(32) formulas by bounded symbolic execution.

Scope, deliberately: nondet_int() is only supported in an unconditional
prefix (never inside a branch or loop body) so that the call order for
any concrete replay is exactly the static call order -- no path-
dependent call arity to resolve. Every benchmark program in this
domain satisfies that shape.

Loops are unrolled to a caller-supplied bound K. Each unroll site
contributes an "unwinding deficit" formula: satisfiable iff some
reachable state after K iterations still wants another one. Deficit
UNSAT is the proof that K was enough -- the same idea as CBMC's
--unwinding-assertions, self-hosted.
"""
import re

import z3

TOKEN_RE = re.compile(r"""
    \s*(?:
        (?P<num>\d+)
      | (?P<ident>[A-Za-z_][A-Za-z_0-9]*)
      | (?P<op>==|!=|<=|>=|&&|\|\||\+=|-=|\+\+|--|[-+*/%&|^!<>=(){};,?:])
    )""", re.VERBOSE)


def tokenize(src):
    toks = []
    i, n = 0, len(src)
    while i < n:
        if src[i].isspace():
            i += 1
            continue
        m = TOKEN_RE.match(src, i)
        if not m or m.end() == i:
            raise ValueError(f"cannot tokenize at {src[i:i + 20]!r}")
        i = m.end()
        if m.lastgroup == "num":
            toks.append(("num", int(m.group("num"))))
        elif m.lastgroup == "ident":
            toks.append(("ident", m.group("ident")))
        else:
            toks.append(("op", m.group("op")))
    return toks


def strip_comments_and_directives(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.DOTALL)
    src = re.sub(r"//[^\n]*", " ", src)
    src = "\n".join(line for line in src.splitlines()
                    if not line.strip().startswith("#"))
    return src


def extract_main_body(src):
    m = re.search(r"\bmain\s*\([^)]*\)\s*\{", src)
    if not m:
        raise ValueError("no main() found")
    depth, i = 1, m.end()
    start = i
    while depth:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    return src[start:i - 1]


class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def at(self, kind, val=None):
        k, v = self.peek()
        return k == kind and (val is None or v == val)

    def eat(self, kind, val=None):
        k, v = self.peek()
        if k != kind or (val is not None and v != val):
            raise ValueError(f"expected {kind} {val!r}, got {k} {v!r}")
        self.i += 1
        return v

    # ---- statements ----

    def parse_block_stmts(self, stop_at_brace):
        stmts = []
        while not (stop_at_brace and self.at("op", "}")) and self.i < len(self.toks):
            stmts.append(self.parse_stmt())
        return stmts

    def parse_stmt_or_block(self):
        if self.at("op", "{"):
            self.eat("op", "{")
            body = self.parse_block_stmts(True)
            self.eat("op", "}")
            return body
        return [self.parse_stmt()]

    def parse_stmt(self):
        if self.at("op", "{"):
            self.eat("op", "{")
            body = self.parse_block_stmts(True)
            self.eat("op", "}")
            return ("block", body)
        if self.at("ident", "if"):
            return self.parse_if()
        if self.at("ident", "for"):
            return self.parse_for()
        if self.at("ident", "while"):
            return self.parse_while()
        if self.at("ident", "assert"):
            self.eat("ident", "assert")
            self.eat("op", "(")
            e = self.parse_expr()
            self.eat("op", ")")
            self.eat("op", ";")
            return ("assert", e)
        if self.at("ident", "return"):
            self.eat("ident", "return")
            if not self.at("op", ";"):
                self.parse_expr()
            self.eat("op", ";")
            return ("return",)
        if self.at("ident", "int"):
            self.eat("ident", "int")
            name = self.eat("ident")
            expr = None
            if self.at("op", "="):
                self.eat("op", "=")
                expr = self.parse_expr()
            self.eat("op", ";")
            return ("decl", name, expr)
        s = self.parse_simple()
        self.eat("op", ";")
        return s

    def parse_simple(self):
        """assign / compound-assign / inc / dec -- with no trailing ';'
        (used standalone and inside for(;;) clauses)."""
        name = self.eat("ident")
        if self.at("op", "++"):
            self.eat("op", "++")
            return ("inc", name)
        if self.at("op", "--"):
            self.eat("op", "--")
            return ("dec", name)
        if self.at("op", "+="):
            self.eat("op", "+=")
            return ("compound", name, "+=", self.parse_expr())
        if self.at("op", "-="):
            self.eat("op", "-=")
            return ("compound", name, "-=", self.parse_expr())
        self.eat("op", "=")
        return ("assign", name, self.parse_expr())

    def parse_if(self):
        self.eat("ident", "if")
        self.eat("op", "(")
        cond = self.parse_expr()
        self.eat("op", ")")
        then_s = self.parse_stmt_or_block()
        else_s = None
        if self.at("ident", "else"):
            self.eat("ident", "else")
            else_s = self.parse_stmt_or_block()
        return ("if", cond, then_s, else_s)

    def parse_for(self):
        self.eat("ident", "for")
        self.eat("op", "(")
        init = None
        if not self.at("op", ";"):
            if self.at("ident", "int"):
                self.eat("ident", "int")
                name = self.eat("ident")
                self.eat("op", "=")
                init = ("decl", name, self.parse_expr())
            else:
                init = self.parse_simple()
        self.eat("op", ";")
        cond = self.parse_expr()
        self.eat("op", ";")
        step = None if self.at("op", ")") else self.parse_simple()
        self.eat("op", ")")
        body = self.parse_stmt_or_block()
        return ("for", init, cond, step, body)

    def parse_while(self):
        self.eat("ident", "while")
        self.eat("op", "(")
        cond = self.parse_expr()
        self.eat("op", ")")
        body = self.parse_stmt_or_block()
        return ("while", cond, body)

    # ---- expressions (precedence climbing) ----

    def parse_expr(self):
        return self.parse_ternary()

    def parse_ternary(self):
        c = self.parse_or()
        if self.at("op", "?"):
            self.eat("op", "?")
            t = self.parse_expr()
            self.eat("op", ":")
            f = self.parse_ternary()
            return ("ternary", c, t, f)
        return c

    def _binop_level(self, ops, sub):
        e = sub()
        while self.peek()[0] == "op" and self.peek()[1] in ops:
            op = self.eat("op")
            e = ("binop", op, e, sub())
        return e

    def parse_or(self):
        return self._binop_level(("||",), self.parse_and)

    def parse_and(self):
        return self._binop_level(("&&",), self.parse_bor)

    def parse_bor(self):
        return self._binop_level(("|",), self.parse_bxor)

    def parse_bxor(self):
        return self._binop_level(("^",), self.parse_band)

    def parse_band(self):
        return self._binop_level(("&",), self.parse_eq)

    def parse_eq(self):
        return self._binop_level(("==", "!="), self.parse_rel)

    def parse_rel(self):
        return self._binop_level(("<", "<=", ">", ">="), self.parse_add)

    def parse_add(self):
        return self._binop_level(("+", "-"), self.parse_mul)

    def parse_mul(self):
        return self._binop_level(("*", "/", "%"), self.parse_unary)

    def parse_unary(self):
        if self.at("op", "-"):
            self.eat("op", "-")
            return ("unop", "-", self.parse_unary())
        if self.at("op", "!"):
            self.eat("op", "!")
            return ("unop", "!", self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        k, v = self.peek()
        if k == "num":
            self.eat("num")
            return ("num", v)
        if k == "op" and v == "(":
            self.eat("op", "(")
            e = self.parse_expr()
            self.eat("op", ")")
            return e
        if k == "ident":
            name = self.eat("ident")
            if self.at("op", "("):
                self.eat("op", "(")
                self.eat("op", ")")
                return ("call", name)
            return ("var", name)
        raise ValueError(f"unexpected token {k} {v!r}")


def parse_program(src):
    src = strip_comments_and_directives(src)
    body = extract_main_body(src)
    p = Parser(tokenize(body))
    return p.parse_block_stmts(False)


# ---------------------------------------------------------- symbolic exec

def to_bool(v):
    if isinstance(v, z3.BoolRef):
        return v
    return v != z3.BitVecVal(0, v.size())


def to_bv(v):
    if isinstance(v, z3.BoolRef):
        return z3.If(v, z3.BitVecVal(1, 32), z3.BitVecVal(0, 32))
    return v


def eval_expr(e, env, ctx):
    kind = e[0]
    if kind == "num":
        return z3.BitVecVal(e[1], 32)
    if kind == "var":
        return env[e[1]]
    if kind == "call":
        if e[1] != "nondet_int":
            raise ValueError(f"unsupported call {e[1]}()")
        idx = ctx["nd_count"]
        ctx["nd_count"] += 1
        var = z3.BitVec(f"nd_{idx}", 32)
        ctx["nondet_vars"].append(var)
        return var
    if kind == "unop":
        v = eval_expr(e[2], env, ctx)
        if e[1] == "-":
            return -to_bv(v)
        return z3.Not(to_bool(v))
    if kind == "binop":
        op = e[1]
        lv = eval_expr(e[2], env, ctx)
        rv = eval_expr(e[3], env, ctx)
        if op == "&&":
            return z3.And(to_bool(lv), to_bool(rv))
        if op == "||":
            return z3.Or(to_bool(lv), to_bool(rv))
        lb, rb = to_bv(lv), to_bv(rv)
        if op == "==":
            return lb == rb
        if op == "!=":
            return lb != rb
        if op == "<":
            return lb < rb
        if op == "<=":
            return lb <= rb
        if op == ">":
            return lb > rb
        if op == ">=":
            return lb >= rb
        if op == "+":
            return lb + rb
        if op == "-":
            return lb - rb
        if op == "*":
            return lb * rb
        if op == "/":
            return lb / rb
        if op == "%":
            return z3.SRem(lb, rb)
        if op == "&":
            return lb & rb
        if op == "|":
            return lb | rb
        if op == "^":
            return lb ^ rb
        raise ValueError(f"unsupported operator {op}")
    if kind == "ternary":
        cond = to_bool(eval_expr(e[1], env, ctx))
        tv = to_bv(eval_expr(e[2], env, ctx))
        fv = to_bv(eval_expr(e[3], env, ctx))
        return z3.If(cond, tv, fv)
    raise ValueError(f"unsupported expr {e!r}")


def _merge(cond, a, b):
    """a if cond else b, per-variable, over two env dicts."""
    names = set(a) | set(b)
    out = {}
    for name in names:
        av, bv = a.get(name), b.get(name)
        out[name] = av if av is bv else z3.If(cond, to_bv(av), to_bv(bv))
    return out


def exec_block(stmts, env, pc, ctx):
    for s in stmts:
        env = exec_stmt(s, env, pc, ctx)
    return env


def exec_stmt(stmt, env, pc, ctx):
    kind = stmt[0]
    if kind in ("decl", "assign"):
        _, name, expr = stmt
        new_env = dict(env)
        new_env[name] = to_bv(eval_expr(expr, env, ctx)) if expr is not None \
            else z3.BitVecVal(0, 32)
        return new_env
    if kind == "compound":
        _, name, op, expr = stmt
        rhs = to_bv(eval_expr(expr, env, ctx))
        cur = env[name]
        new_env = dict(env)
        new_env[name] = cur + rhs if op == "+=" else cur - rhs
        return new_env
    if kind in ("inc", "dec"):
        _, name = stmt
        cur = env[name]
        one = z3.BitVecVal(1, 32)
        new_env = dict(env)
        new_env[name] = cur + one if kind == "inc" else cur - one
        return new_env
    if kind == "assert":
        cond = to_bool(eval_expr(stmt[1], env, ctx))
        ctx["violations"].append(z3.And(pc, z3.Not(cond)))
        return env
    if kind == "if":
        _, cond_e, then_s, else_s = stmt
        cond = to_bool(eval_expr(cond_e, env, ctx))
        outer = set(env)
        env_then = exec_block(then_s, dict(env), z3.And(pc, cond), ctx)
        env_else = exec_block(else_s, dict(env), z3.And(pc, z3.Not(cond)), ctx) \
            if else_s is not None else dict(env)
        env_then = {k: v for k, v in env_then.items() if k in outer}
        env_else = {k: v for k, v in env_else.items() if k in outer}
        return _merge(cond, env_then, env_else)
    if kind == "block":
        outer = set(env)
        inner = exec_block(stmt[1], dict(env), pc, ctx)
        return {k: v for k, v in inner.items() if k in outer}
    if kind == "while":
        _, cond_e, body = stmt
        return exec_loop(cond_e, None, body, env, pc, ctx)
    if kind == "for":
        _, init_s, cond_e, step_s, body = stmt
        if init_s is not None:
            env = exec_stmt(init_s, env, pc, ctx)
        return exec_loop(cond_e, step_s, body, env, pc, ctx)
    if kind == "return":
        return env
    raise ValueError(f"unsupported stmt {stmt!r}")


def exec_loop(cond_e, step_s, body, env, pc, ctx):
    k = ctx["unroll_k"]
    outer = set(env)
    entered = pc
    cur = env
    for _ in range(k):
        guard = to_bool(eval_expr(cond_e, cur, ctx))
        step_cond = z3.And(entered, guard)
        body_env = exec_block(body, dict(cur), step_cond, ctx)
        body_env = {n: v for n, v in body_env.items() if n in outer}
        if step_s is not None:
            body_env = exec_stmt(step_s, body_env, step_cond, ctx)
        cur = _merge(step_cond, body_env, cur)
        entered = step_cond
    final_guard = to_bool(eval_expr(cond_e, cur, ctx))
    ctx["unwind_deficits"].append(z3.And(entered, final_guard))
    return cur


def build(src, k):
    """Returns (violation_formula, deficit_formula, nondet_vars) for an
    unroll bound of k."""
    ast = parse_program(src)
    ctx = {"violations": [], "unwind_deficits": [], "nd_count": 0,
           "nondet_vars": [], "unroll_k": k}
    exec_block(ast, {}, z3.BoolVal(True), ctx)
    violation = z3.Or(*ctx["violations"]) if ctx["violations"] else z3.BoolVal(False)
    deficit = z3.Or(*ctx["unwind_deficits"]) if ctx["unwind_deficits"] else z3.BoolVal(False)
    return violation, deficit, ctx["nondet_vars"]


def signed(bv_num):
    v = bv_num.as_long()
    return v - (1 << 32) if v >= (1 << 31) else v
