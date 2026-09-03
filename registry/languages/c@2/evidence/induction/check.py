"""The `induction` certificate judge of c (KERNEL.md §3): re-check a
universal certificate about a C program from scratch, where the
question lives.

A C-level certificate speaks about the machine the c interpreter
executes — the elaborated CFG of atomic nodes, one per frame — in its
own terms: `{"kind": "k-induction", "k": K}` says the machine is
K-inductive for its bad location; `{"kind": "bit-invariant", "bits":
[[atom, value], ...]}` and `{"kind": "clause-invariant", "clauses":
[[[atom, value], ...], ...]}` name bits of the machine's state by
atoms `["pc", i]` (bit i of the location register) and `["slot",
name, i]` (bit i of a scalar slot, named as the elaborator names it).
The judge is composed verbatim from three texts already in the base
or in the registry: the c interpreter's front end (the CFG is built
by exactly the code that executes it), the c--btor2 machine encoding
(the CFG as a bit-vector transition system), and the btor2 judges'
bit-blaster, SAT solver, and obligations — init, consecution, safety
for invariants; base and step for k-induction. No search guides the
answer; the budget is a constant; every failure path refuses the
upgrade. Its lineage names every text it is composed of: a proof
certified here rests on the c front end, that encoding, and that
checker — and the board says so.

Usage: check.py <program.c> <payload.json> ->
       {"ok": bool, "obligations": {...}}
"""

import json
import sys

# -- types --------------------------------------------------------------------
# A ctype is (width, signed). ILP32: long is int; plain char is signed.

T_BOOL = (1, False)
T_CHAR = (8, True)
T_UCHAR = (8, False)
T_SHORT = (16, True)
T_USHORT = (16, False)
T_INT = (32, True)
T_UINT = (32, False)
T_LL = (64, True)
T_ULL = (64, False)

NONDET = {
    "__VERIFIER_nondet_bool": T_BOOL,
    "__VERIFIER_nondet_char": T_CHAR,
    "__VERIFIER_nondet_uchar": T_UCHAR,
    "__VERIFIER_nondet_short": T_SHORT,
    "__VERIFIER_nondet_ushort": T_USHORT,
    "__VERIFIER_nondet_int": T_INT,
    "__VERIFIER_nondet_uint": T_UINT,
    "__VERIFIER_nondet_long": T_INT,
    "__VERIFIER_nondet_ulong": T_UINT,
    "__VERIFIER_nondet_longlong": T_LL,
    "__VERIFIER_nondet_ulonglong": T_ULL,
    "__VERIFIER_nondet_unsigned": T_UINT,
    "__VERIFIER_nondet_u32": T_UINT,
    "__VERIFIER_nondet_uint128": None,       # outside the fragment
    "__VERIFIER_nondet_int128": None,
}

HALT_CALLS = {"abort", "exit"}
ERROR_CALLS = {"__assert_fail"}

SIZEOF = {1: 1, 8: 1, 16: 2, 32: 4, 64: 8}


def conv(v, ct):
    """Convert an integer to ctype ct (two's complement wrap)."""
    w, s = ct
    m = v & ((1 << w) - 1)
    if s and m >> (w - 1):
        m -= 1 << w
    return m


def promote(ct):
    return ct if ct[0] >= 32 else T_INT


def usual(a, b):
    """Usual arithmetic conversions after promotion (ILP32)."""
    a, b = promote(a), promote(b)
    if a == b:
        return a
    (wa, sa), (wb, sb) = a, b
    if sa == sb:
        return a if wa >= wb else b
    (wu, _), (ws, _) = (a, b) if not sa else (b, a)
    if wu >= ws:
        return (wu, False)
    return (ws, True) if ws > wu else (ws, False)


class Frag(Exception):
    """Outside the fragment (or malformed): a loud refusal."""


# -- lexer --------------------------------------------------------------------

KEYWORDS = {
    "void", "char", "short", "int", "long", "signed", "unsigned", "_Bool",
    "const", "volatile", "extern", "static", "inline", "register",
    "if", "else", "while", "for", "do", "switch", "return", "break",
    "continue", "goto", "sizeof", "float", "double", "struct", "union",
    "enum", "typedef", "case", "default",
}
PUNCT = sorted(
    ["<<=", ">>=", "...", "<<", ">>", "<=", ">=", "==", "!=", "&&", "||",
     "++", "--", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "->",
     "+", "-", "*", "/", "%", "&", "|", "^", "~", "!", "<", ">", "=",
     "(", ")", "{", "}", "[", "]", ";", ",", ":", "?", "."],
    key=len, reverse=True)
ESCAPES = {"n": 10, "t": 9, "r": 13, "0": 0, "\\": 92, "'": 39, '"': 34,
           "a": 7, "b": 8, "f": 12, "v": 11}


def lex(src):
    toks, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j + 1
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise Frag("unterminated comment")
            i = j + 2
        elif c == "#":
            raise Frag("preprocessor directive — outside the fragment")
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            toks.append(("kw" if word in KEYWORDS else "id", word))
            i = j
        elif c.isdigit():
            j = i
            if src.startswith("0x", i) or src.startswith("0X", i):
                j = i + 2
                while j < n and src[j] in "0123456789abcdefABCDEF":
                    j += 1
                val, dec = int(src[i:j], 16), False
            else:
                while j < n and src[j].isdigit():
                    j += 1
                text = src[i:j]
                if j < n and src[j] in ".eE" and not src.startswith(
                        "0x", i):
                    raise Frag("floating constant — outside the fragment")
                if text.startswith("0") and len(text) > 1:
                    val, dec = int(text, 8), False
                else:
                    val, dec = int(text), True
            u = lcount = 0
            while j < n and src[j] in "uUlL":
                if src[j] in "uU":
                    u += 1
                else:
                    lcount += 1
                j += 1
            toks.append(("num", (val, u > 0, lcount, dec)))
            i = j
        elif c == "'":
            j = i + 1
            if j < n and src[j] == "\\":
                if src[j + 1] not in ESCAPES:
                    raise Frag(f"escape \\{src[j + 1]}")
                v, j = ESCAPES[src[j + 1]], j + 2
            else:
                v, j = ord(src[j]), j + 1
            if j >= n or src[j] != "'":
                raise Frag("bad char literal")
            toks.append(("num", (v, False, 0, True)))
            i = j + 1
        elif c == '"':
            j = i + 1
            while j < n and src[j] != '"':
                j += 2 if src[j] == "\\" else 1
            if j >= n:
                raise Frag("unterminated string")
            toks.append(("str", src[i + 1:j]))
            i = j + 1
        else:
            for p in PUNCT:
                if src.startswith(p, i):
                    toks.append(("p", p))
                    i += len(p)
                    break
            else:
                raise Frag(f"character {c!r}")
    toks.append(("eof", ""))
    return toks


# -- parser -------------------------------------------------------------------
# AST: expressions are tuples —
#   ('num', value, ctype) ('var', name) ('idx', name, e) ('call', name, args)
#   ('un', op, e) ('bin', op, a, b) ('land', a, b) ('lor', a, b)
#   ('cast', ctype, e) ('asgn', op, lval, e) ('inc', +1/-1, pre, lval)
# statements —
#   ('expr', e) ('decl', ctype, [(name, dims, init)]) ('if', c, s, s|None)
#   ('while', c, s) ('for', init|None, c|None, upd|None, s) ('block', [s])
#   ('return', e|None) ('break',) ('continue',) ('goto', label)
#   ('label', name, s) ('empty',)

class Parser:
    def __init__(self, toks):
        self.toks, self.i = toks, 0

    def peek(self, k=0):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def eat(self, kind, val=None):
        t = self.next()
        if t[0] != kind or (val is not None and t[1] != val):
            raise Frag(f"expected {val or kind}, got {t[1]!r}")
        return t

    def at(self, kind, val=None):
        t = self.peek()
        return t[0] == kind and (val is None or t[1] == val)

    def at_p(self, p):
        return self.at("p", p)

    # types
    TYPEWORDS = {"void", "char", "short", "int", "long", "signed",
                 "unsigned", "_Bool", "const", "volatile", "float",
                 "double", "struct", "union", "enum"}

    def at_type(self):
        return self.at("kw") and self.peek()[1] in self.TYPEWORDS

    def parse_type(self):
        words = []
        while self.at("kw") and self.peek()[1] in self.TYPEWORDS:
            w = self.next()[1]
            if w in ("float", "double", "struct", "union", "enum"):
                raise Frag(f"{w} — outside the fragment")
            if w not in ("const", "volatile"):
                words.append(w)
        if not words:
            raise Frag("expected a type")
        if words == ["void"]:
            return None
        signed = "unsigned" not in words
        base = [w for w in words if w not in ("signed", "unsigned")]
        key = " ".join(base)
        m = {"": T_INT, "int": T_INT, "char": T_CHAR, "short": T_SHORT,
             "short int": T_SHORT, "long": T_INT, "long int": T_INT,
             "long long": T_LL, "long long int": T_LL, "_Bool": T_BOOL}
        if key not in m:
            raise Frag(f"type {' '.join(words)!r}")
        w, s = m[key]
        if key == "_Bool":
            return T_BOOL
        return (w, signed if key != "" else signed)

    def skip_attrs(self):
        while (self.at("id") and self.peek()[1].startswith("__attribute")) \
                or (self.at("id") and self.peek()[1] == "__extension__"):
            name = self.next()[1]
            if name == "__extension__":
                continue
            self.eat("p", "(")
            depth = 1
            while depth:
                t = self.next()
                if t == ("p", "("):
                    depth += 1
                elif t == ("p", ")"):
                    depth -= 1

    # translation unit ---------------------------------------------------------
    def unit(self):
        funcs, globals_ = {}, []       # globals_: (name, ctype, dims, init)
        while not self.at("eof"):
            is_extern = False
            while self.at("kw") and self.peek()[1] in ("extern", "static",
                                                       "inline", "register",
                                                       "typedef"):
                w = self.next()[1]
                if w == "typedef":
                    raise Frag("typedef — outside the fragment")
                is_extern = is_extern or w == "extern"
            ct = self.parse_type()
            self.skip_attrs()
            if self.at_p(";"):          # e.g. a bare 'struct'-less decl
                self.next()
                continue
            name = self.eat("id")[1]
            if self.at_p("("):
                # scan the balanced parameter list first: a prototype
                # (";" after) is skipped whole — its parameter types
                # (char *, ...) never enter the fragment — while a
                # definition ("{" after) rewinds and parses strictly.
                mark = self.i
                self.next()
                depth = 1
                while depth:
                    t = self.next()
                    if t == ("p", "("):
                        depth += 1
                    elif t == ("p", ")"):
                        depth -= 1
                    elif t[0] == "eof":
                        raise Frag("unbalanced parameter list")
                self.skip_attrs()
                if self.at_p(";"):      # prototype: names a builtin, gone
                    self.next()
                    continue
                self.i = mark
                params = self.params()
                self.skip_attrs()
                body = self.block()
                if not is_extern:
                    funcs[name] = (ct, params, body)
                continue
            # global variable declaration list
            while True:
                dims = self.dims()
                init = None
                if self.at_p("="):
                    self.next()
                    init = self.initializer()
                if not is_extern:
                    globals_.append((name, ct, dims, init))
                if self.at_p(","):
                    self.next()
                    name = self.eat("id")[1]
                    continue
                self.eat("p", ";")
                break
        return funcs, globals_

    def params(self):
        self.eat("p", "(")
        params = []
        if self.at_p(")"):
            self.next()
            return params
        if self.at("kw", "void") and self.peek(1) == ("p", ")"):
            self.next()
            self.next()
            return params
        while True:
            ct = self.parse_type()
            if ct is None:
                raise Frag("void parameter")
            if self.at_p("*"):
                raise Frag("pointer parameter — outside the fragment")
            pname = self.eat("id")[1] if self.at("id") else None
            if self.at_p("["):
                raise Frag("array parameter — outside the fragment")
            params.append((pname, ct))
            if self.at_p(","):
                self.next()
                continue
            self.eat("p", ")")
            return params

    def dims(self):
        dims = []
        while self.at_p("["):
            self.next()
            dims.append(self.expr())
            self.eat("p", "]")
        if len(dims) > 2:
            raise Frag("arrays beyond two dimensions")
        return dims

    def initializer(self):
        if self.at_p("{"):
            self.next()
            items = []
            while not self.at_p("}"):
                items.append(self.initializer())
                if self.at_p(","):
                    self.next()
            self.next()
            return ("ilist", items)
        return self.asgn_expr()

    # statements ---------------------------------------------------------------
    def block(self):
        self.eat("p", "{")
        stmts = []
        while not self.at_p("}"):
            stmts.append(self.stmt())
        self.next()
        return ("block", stmts)

    def stmt(self):
        if self.at_p("{"):
            return self.block()
        if self.at_p(";"):
            self.next()
            return ("empty",)
        if self.at("kw"):
            kw = self.peek()[1]
            if kw in ("do", "switch", "case", "default"):
                raise Frag(f"{kw} — outside the fragment")
            if kw == "if":
                self.next()
                self.eat("p", "(")
                c = self.expr()
                self.eat("p", ")")
                s = self.stmt()
                e = None
                if self.at("kw", "else"):
                    self.next()
                    e = self.stmt()
                return ("if", c, s, e)
            if kw == "while":
                self.next()
                self.eat("p", "(")
                c = self.expr()
                self.eat("p", ")")
                return ("while", c, self.stmt())
            if kw == "for":
                self.next()
                self.eat("p", "(")
                init = None
                if not self.at_p(";"):
                    init = (self.decl_stmt() if self.at_type()
                            else ("expr", self.expr()))
                    if init[0] == "decl":
                        pass           # decl_stmt ate the ';'
                    else:
                        self.eat("p", ";")
                else:
                    self.next()
                cond = None if self.at_p(";") else self.expr()
                self.eat("p", ";")
                upd = None if self.at_p(")") else ("expr", self.expr())
                self.eat("p", ")")
                return ("for", init, cond, upd, self.stmt())
            if kw == "return":
                self.next()
                e = None if self.at_p(";") else self.expr()
                self.eat("p", ";")
                return ("return", e)
            if kw == "break":
                self.next()
                self.eat("p", ";")
                return ("break",)
            if kw == "continue":
                self.next()
                self.eat("p", ";")
                return ("continue",)
            if kw == "goto":
                self.next()
                lbl = self.eat("id")[1]
                self.eat("p", ";")
                return ("goto", lbl)
            if self.at_type():
                return self.decl_stmt()
            raise Frag(f"statement keyword {kw!r}")
        if self.at("id") and self.peek(1) == ("p", ":"):
            name = self.next()[1]
            self.next()
            return ("label", name, self.stmt())
        e = self.expr()
        self.eat("p", ";")
        return ("expr", e)

    def decl_stmt(self):
        ct = self.parse_type()
        if ct is None:
            raise Frag("void variable")
        entries = []
        while True:
            if self.at_p("*"):
                raise Frag("pointer declaration — outside the fragment")
            name = self.eat("id")[1]
            dims = self.dims()
            init = None
            if self.at_p("="):
                self.next()
                init = self.initializer()
            entries.append((name, dims, init))
            if self.at_p(","):
                self.next()
                continue
            self.eat("p", ";")
            return ("decl", ct, entries)

    # expressions --------------------------------------------------------------
    def expr(self):
        e = self.asgn_expr()
        while self.at_p(","):
            self.next()
            e = ("comma", e, self.asgn_expr())
        return e

    ASGN_OPS = {"=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=",
                "<<=", ">>="}

    def asgn_expr(self):
        e = self.binary(0)
        if self.at("p") and self.peek()[1] in self.ASGN_OPS:
            op = self.next()[1]
            if e[0] not in ("var", "idx"):
                raise Frag("assignment to a non-lvalue")
            return ("asgn", op, e, self.asgn_expr())
        if self.at_p("?"):
            raise Frag("ternary — outside the fragment")
        return e

    LEVELS = [["||"], ["&&"], ["|"], ["^"], ["&"], ["==", "!="],
              ["<", ">", "<=", ">="], ["<<", ">>"], ["+", "-"],
              ["*", "/", "%"]]

    def binary(self, lvl):
        if lvl == len(self.LEVELS):
            return self.unary()
        e = self.binary(lvl + 1)
        while self.at("p") and self.peek()[1] in self.LEVELS[lvl]:
            op = self.next()[1]
            rhs = self.binary(lvl + 1)
            if op == "&&":
                e = ("land", e, rhs)
            elif op == "||":
                e = ("lor", e, rhs)
            else:
                e = ("bin", op, e, rhs)
        return e

    def unary(self):
        if self.at("p") and self.peek()[1] in ("!", "~", "-", "+"):
            op = self.next()[1]
            return ("un", op, self.unary())
        if self.at_p("++") or self.at_p("--"):
            op = self.next()[1]
            lv = self.unary()
            if lv[0] not in ("var", "idx"):
                raise Frag("++/-- on a non-lvalue")
            return ("inc", 1 if op == "++" else -1, True, lv)
        if self.at("kw", "sizeof"):
            self.next()
            if self.at_p("(") and self.toks[self.i + 1][0] == "kw" \
                    and self.toks[self.i + 1][1] in self.TYPEWORDS:
                self.next()
                ct = self.parse_type()
                self.eat("p", ")")
                return ("num", SIZEOF[ct[0]], T_UINT)
            e = self.unary()
            return ("szexpr", e)
        if self.at_p("(") and self.toks[self.i + 1][0] == "kw" \
                and self.toks[self.i + 1][1] in self.TYPEWORDS:
            self.next()
            ct = self.parse_type()
            self.eat("p", ")")
            if ct is None:
                e = self.unary()       # (void) f(...) — value dropped
                return ("cast", T_INT, e)
            return ("cast", ct, self.unary())
        if self.at_p("*") or self.at_p("&"):
            raise Frag("pointer operator — outside the fragment")
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while True:
            if self.at_p("("):
                if e[0] != "var":
                    raise Frag("call of a non-identifier")
                self.next()
                args = []
                if not self.at_p(")"):
                    while True:
                        if self.at("str"):
                            args.append(("str", self.next()[1]))
                        else:
                            args.append(self.asgn_expr())
                        if self.at_p(","):
                            self.next()
                            continue
                        break
                self.eat("p", ")")
                e = ("call", e[1], args)
            elif self.at_p("["):
                self.next()
                idx = self.expr()
                self.eat("p", "]")
                if e[0] == "var":
                    e = ("idx", e[1], [idx])
                elif e[0] == "idx" and len(e[2]) == 1:
                    e = ("idx", e[1], e[2] + [idx])
                else:
                    raise Frag("indexing a non-array")
            elif self.at_p("++") or self.at_p("--"):
                op = self.next()[1]
                if e[0] not in ("var", "idx"):
                    raise Frag("++/-- on a non-lvalue")
                e = ("inc", 1 if op == "++" else -1, False, e)
            else:
                return e

    def primary(self):
        t = self.peek()
        if t[0] == "num":
            val, uns, lcount, dec = self.next()[1]
            if lcount >= 2:
                ct = T_ULL if uns else T_LL
            elif uns:
                ct = T_UINT if val < (1 << 32) else T_ULL
            elif dec:
                ct = T_INT if val < (1 << 31) else T_LL
            else:                       # hex/octal/char: unsigned rungs too
                for ct in (T_INT, T_UINT, T_LL, T_ULL):
                    w, s = ct
                    if val < (1 << (w - (1 if s else 0))):
                        break
            return ("num", conv(val, ct), ct)
        if t[0] == "id":
            return ("var", self.next()[1])
        if t == ("p", "("):
            self.next()
            e = self.expr()
            self.eat("p", ")")
            return e
        raise Frag(f"expression, got {t[1]!r}")


# -- elaboration: inline calls, linearize to atomic nodes -----------------------
# Node kinds: ('asgn', lv, pure) ('havoc', lv, site, ctype)
#             ('br', pure, tlab, flab) ('jmp', lab) ('halt',) ('err',)
# where lv = ('var', slot) | ('idx', slot, [pure...]) and pure expressions
# are ASTs guaranteed free of calls, assignments, ++/--.

class Elab:
    def __init__(self, funcs, globals_):
        self.funcs = funcs
        self.nodes = []
        self.slots = {}                 # slot -> (ctype, dims or None)
        self.globals = {}               # slot -> initial value(s)
        self.n_tmp = self.n_site = self.n_inline = 0
        self.stack = []                 # inline stack: function names
        # Straight-line constant tracking, for array dimensions given by
        # a local set once from a constant (the corpus's VLA idiom
        # `unsigned SIZE=1; int a[SIZE];`). Sound because it only ever
        # holds while elaborating straight-line code: any assignment
        # under a branch or loop (ctl > 0), and any havoc, poisons the
        # slot forever — and before the poisoning point, emission order
        # IS execution order.
        self.known = {}                 # slot -> constant value
        self.poison = set()
        self.ctl = 0
        self.label_seen = False
        genv = {}
        for name, ct, dims_ast, init in globals_:
            dims = [self.constfold(d, genv) for d in dims_ast]
            self.slots[name] = (ct, dims or None)
            if dims:
                size = dims[0] * (dims[1] if len(dims) > 1 else 1)
                vals = [0] * size
                if init is not None:
                    if init[0] != "ilist":
                        raise Frag("array initializer must be a list")
                    flat = []
                    for it in init[1]:
                        if it[0] == "ilist":
                            row = [self.constfold(x, genv) for x in it[1]]
                            row += [0] * ((dims[1] if len(dims) > 1 else
                                           len(row)) - len(row))
                            flat.extend(row)
                        else:
                            flat.append(self.constfold(it, genv))
                    for k, v in enumerate(flat[:size]):
                        vals[k] = conv(v, ct)
                self.globals[name] = vals
                genv[name] = vals
            else:
                v = conv(self.constfold(init, genv), ct) \
                    if init is not None else 0
                self.globals[name] = v
                genv[name] = v
                self.known[name] = v
        if "main" not in funcs:
            raise Frag("no main")
        scope = [{n: n for n in self.slots}]
        self.inline("main", [], scope)
        self.emit(("jmp", "%HALT"))
        self.resolve()

    # small helpers
    def emit(self, node):
        if node[0] == "asgn" and node[1][0] == "var":
            slot = node[1][1]
            v = self.try_const(node[2])
            if self.ctl == 0 and v is not None and slot not in self.poison:
                self.known[slot] = conv(v, self.slots[slot][0])
            else:
                self.poison.add(slot)
                self.known.pop(slot, None)
        elif node[0] == "havoc":
            self.poison.add(node[1][1])
            self.known.pop(node[1][1], None)
        self.nodes.append(node)
        return len(self.nodes) - 1

    def try_const(self, e):
        try:
            return self._cval(e)[0]
        except Frag:
            return None

    def _cval(self, e):
        k = e[0]
        if k == "num":
            return (e[1], e[2])
        if k == "cast":
            v, _ = self._cval(e[2])
            return (conv(v, e[1]), e[1])
        if k == "var":
            if e[1] in self.known and e[1] not in self.poison:
                return (self.known[e[1]], self.slots[e[1]][0])
            raise Frag("not a constant")
        if k == "un":
            v, ct = self._cval(e[2])
            if e[1] == "!":
                return (1 if v == 0 else 0, T_INT)
            pt = promote(ct)
            v = conv(v, pt)
            return (conv({"-": -v, "+": v, "~": ~v}[e[1]], pt), pt)
        if k == "bin":
            a, ta = self._cval(e[2])
            b, tb = self._cval(e[3])
            return _arith(e[1], a, b, ta, tb)
        raise Frag("not a constant")

    def fold_dim(self, d, scope):
        """An array dimension: a constant expression, allowed to see
        straight-line constant locals (the corpus's `SIZE=1; int a[SIZE]`
        idiom) only while emission order provably equals execution order
        — never under a branch or loop, never after a goto or label."""
        env = {}
        if self.ctl == 0 and not self.label_seen:
            for frame in scope:
                for name, slot in frame.items():
                    if slot in self.known and slot not in self.poison \
                            and self.slots.get(slot, (0, 1))[1] is None:
                        env[name] = self.known[slot]
        return self.constfold(d, env)

    def tmp(self, ct):
        self.n_tmp += 1
        slot = f"%t{self.n_tmp}"
        self.slots[slot] = (ct, None)
        return slot

    def constfold(self, e, genv):
        if e is None:
            raise Frag("missing constant expression")
        if e[0] == "num":
            return e[1]
        if e[0] == "un":
            v = self.constfold(e[2], genv)
            return {"-": -v, "+": v, "~": ~v, "!": int(v == 0)}[e[1]]
        if e[0] == "bin":
            a, b = self.constfold(e[2], genv), self.constfold(e[3], genv)
            return _arith(e[1], a, b, T_LL, T_LL)[0]
        if e[0] == "var" and e[1] in genv \
                and not isinstance(genv[e[1]], list):
            return genv[e[1]]
        raise Frag("not a constant expression")

    # name resolution
    def lookup(self, scope, name):
        for frame in reversed(scope):
            if name in frame:
                return frame[name]
        raise Frag(f"undeclared identifier {name!r}")

    def declare(self, scope, name, ct, dims):
        self.n_tmp += 1
        slot = f"{name}%{self.n_tmp}"
        scope[-1][name] = slot
        self.slots[slot] = (ct, dims or None)
        return slot

    # inlining -----------------------------------------------------------------
    def inline(self, fname, arg_pures, scope):
        """Inline a call to defined function fname (args already pure,
        in evaluation order). Returns (ret_slot or None)."""
        if fname in self.stack:
            raise Frag(f"recursion through {fname!r}")
        self.stack.append(fname)
        self.n_inline += 1
        ret_ct, params, body = self.funcs[fname]
        if len(params) != len(arg_pures):
            raise Frag(f"{fname}: argument count")
        fscope = [scope[0], {}]        # globals + fresh function scope
        for (pname, pct), pure in zip(params, arg_pures):
            slot = self.declare(fscope, pname or f"%arg{self.n_tmp}",
                                pct, None)
            self.emit(("asgn", ("var", slot), ("cast", pct, pure)))
        ret_slot = self.tmp(ret_ct) if ret_ct is not None else None
        exit_lab = f"%ret{self.n_inline}"
        ctx = {"ret": (ret_slot, ret_ct, exit_lab), "brk": None,
               "cont": None, "labels": {}, "prefix": f"%f{self.n_inline}."}
        self.stmt(body, fscope, ctx)
        self.emit(("labeldef", exit_lab))
        self.stack.pop()
        return ret_slot

    # statement lowering ---------------------------------------------------------
    def stmt(self, s, scope, ctx):
        kind = s[0]
        if kind == "block":
            scope.append({})
            for sub in s[1]:
                self.stmt(sub, scope, ctx)
            scope.pop()
        elif kind == "decl":
            ct, entries = s[1], s[2]
            for name, dims_ast, init in entries:
                dims = [self.fold_dim(d, scope) for d in dims_ast]
                slot = self.declare(scope, name, ct, dims)
                if init is not None:
                    if dims:
                        if init[0] != "ilist":
                            raise Frag("array initializer must be a list")
                        cols = dims[1] if len(dims) > 1 else None
                        flat = []
                        for it in init[1]:
                            if it[0] == "ilist":
                                if cols is None:
                                    raise Frag("nested initializer on a "
                                               "one-dimensional array")
                                row = [self.pure(x, scope, ctx)
                                       for x in it[1]]
                                row += [("num", 0, T_INT)] * (cols -
                                                              len(row))
                                flat.extend(row)
                            else:
                                flat.append(self.pure(it, scope, ctx))
                        for k, pv in enumerate(flat):
                            self.emit(("asgn",
                                       ("idx", slot, [("num", k, T_INT)]),
                                       pv))
                    else:
                        pv = self.pure(init, scope, ctx)
                        self.emit(("asgn", ("var", slot),
                                   ("cast", ct, pv)))
        elif kind == "expr":
            self.effect(s[1], scope, ctx)
        elif kind == "empty":
            pass
        elif kind == "if":
            c = self.pure(s[1], scope, ctx)
            self.n_inline += 1
            tl, fl, jl = (f"%if{self.n_inline}.t", f"%if{self.n_inline}.f",
                          f"%if{self.n_inline}.j")
            self.emit(("br", c, tl, fl))
            self.ctl += 1
            self.emit(("labeldef", tl))
            self.stmt(s[2], scope, ctx)
            self.emit(("jmp", jl))
            self.emit(("labeldef", fl))
            if s[3] is not None:
                self.stmt(s[3], scope, ctx)
            self.emit(("labeldef", jl))
            self.ctl -= 1
        elif kind == "while":
            self.n_inline += 1
            top, bl, xl = (f"%w{self.n_inline}.c", f"%w{self.n_inline}.b",
                           f"%w{self.n_inline}.x")
            self.ctl += 1
            self.emit(("labeldef", top))
            c = self.pure(s[1], scope, ctx)
            self.emit(("br", c, bl, xl))
            self.emit(("labeldef", bl))
            inner = dict(ctx, brk=xl, cont=top)
            self.stmt(s[2], scope, inner)
            self.emit(("jmp", top))
            self.emit(("labeldef", xl))
            self.ctl -= 1
        elif kind == "for":
            init, cond, upd, body = s[1], s[2], s[3], s[4]
            scope.append({})
            if init is not None:
                self.stmt(init, scope, ctx)
            self.n_inline += 1
            top, bl, cl, xl = (f"%f{self.n_inline}.c", f"%f{self.n_inline}.b",
                               f"%f{self.n_inline}.u", f"%f{self.n_inline}.x")
            self.ctl += 1
            self.emit(("labeldef", top))
            if cond is not None:
                c = self.pure(cond, scope, ctx)
                self.emit(("br", c, bl, xl))
            self.emit(("labeldef", bl))
            inner = dict(ctx, brk=xl, cont=cl)
            self.stmt(body, scope, inner)
            self.emit(("labeldef", cl))
            if upd is not None:
                self.stmt(upd, scope, ctx)
            self.emit(("jmp", top))
            self.emit(("labeldef", xl))
            self.ctl -= 1
            scope.pop()
        elif kind == "return":
            ret_slot, ret_ct, exit_lab = ctx["ret"]
            if s[1] is not None and ret_slot is not None:
                pv = self.pure(s[1], scope, ctx)
                self.emit(("asgn", ("var", ret_slot), ("cast", ret_ct, pv)))
            self.emit(("jmp", exit_lab))
        elif kind == "break":
            if ctx["brk"] is None:
                raise Frag("break outside a loop")
            self.emit(("jmp", ctx["brk"]))
        elif kind == "continue":
            if ctx["cont"] is None:
                raise Frag("continue outside a loop")
            self.emit(("jmp", ctx["cont"]))
        elif kind == "goto":
            self.label_seen = True
            self.emit(("jmp", ctx["prefix"] + s[1]))
        elif kind == "label":
            self.label_seen = True
            self.emit(("labeldef", ctx["prefix"] + s[1]))
            self.stmt(s[2], scope, ctx)
        else:
            raise Frag(f"statement {kind!r}")

    # expression lowering --------------------------------------------------------
    def effect(self, e, scope, ctx):
        """Lower an expression for effect (value dropped): the
        statement-level cheap forms of assignment and ++/--."""
        if e[0] == "asgn" and e[1] == "=":
            lv = self.lval(e[2], scope, ctx)
            pv = self.pure(e[3], scope, ctx)
            self.emit(("asgn", lv, ("cast", self.lv_type(lv), pv)))
        elif e[0] == "asgn":
            lv = self.lval(e[2], scope, ctx)
            pv = self.pure(e[3], scope, ctx)
            cur = self.lv_read(lv)
            self.emit(("asgn", lv, ("cast", self.lv_type(lv),
                                    ("bin", e[1][:-1], cur, pv))))
        elif e[0] == "inc":
            lv = self.lval(e[3], scope, ctx)
            cur = self.lv_read(lv)
            self.emit(("asgn", lv,
                       ("cast", self.lv_type(lv),
                        ("bin", "+", cur, ("num", e[1], T_INT)))))
        elif e[0] == "call":
            self.call(e, scope, ctx)
        elif e[0] == "comma":
            self.effect(e[1], scope, ctx)
            self.effect(e[2], scope, ctx)
        elif e[0] == "cast":
            self.effect(e[2], scope, ctx)
        else:
            self.pure(e, scope, ctx)    # effects inside, value dropped

    def lval(self, e, scope, ctx):
        if e[0] == "var":
            slot = self.lookup(scope, e[1])
            if self.slots[slot][1] is not None:
                raise Frag("array used as a value")
            return ("var", slot)
        slot = self.lookup(scope, e[1])
        ct, dims = self.slots[slot]
        if dims is None or len(dims) != len(e[2]):
            raise Frag(f"indexing mismatch on {e[1]!r}")
        idxs = [self.pure(x, scope, ctx) for x in e[2]]
        if len(dims) == 2:
            flat = ("bin", "+",
                    ("bin", "*", idxs[0], ("num", dims[1], T_INT)),
                    idxs[1])
            return ("idx", slot, [flat])
        return ("idx", slot, idxs)

    def lv_type(self, lv):
        return self.slots[lv[1]][0]

    def lv_read(self, lv):
        return lv if lv[0] == "var" else ("idx", lv[1], lv[2])

    def call(self, e, scope, ctx):
        """Lower a call; returns a pure expression for its value (or a
        zero for void builtins whose value is never used)."""
        name, args = e[1], e[2]
        if name in NONDET:
            ct = NONDET[name]
            if ct is None:
                raise Frag(f"{name} — outside the fragment")
            t = self.tmp(ct)
            self.n_site += 1
            self.emit(("havoc", ("var", t), f"h{self.n_site}", ct))
            return ("var", t)
        if name in self.funcs:
            pures = [self.pure(a, scope, ctx) for a in args
                     if a[0] != "str"]
            ret = self.inline(name, pures, scope)
            if ret is None:
                return ("num", 0, T_INT)
            return ("var", ret)
        if name in HALT_CALLS:
            for a in args:
                if a[0] != "str":
                    self.pure(a, scope, ctx)
            self.emit(("jmp", "%HALT"))
            return ("num", 0, T_INT)
        if name in ERROR_CALLS:
            self.emit(("jmp", "%ERR"))
            return ("num", 0, T_INT)
        raise Frag(f"call to unknown function {name!r}")

    def pure(self, e, scope, ctx):
        """Lower an expression to a side-effect-free tree, emitting
        nodes for the effects inside it, left to right."""
        k = e[0]
        if k == "num":
            return e
        if k == "str":
            raise Frag("string in an expression")
        if k == "szexpr":
            ct = self.typeof(self.pure(e[1], scope, ctx))
            return ("num", SIZEOF[ct[0]], T_UINT)
        if k == "var":
            slot = self.lookup(scope, e[1])
            if self.slots[slot][1] is not None:
                raise Frag("array used as a value")
            return ("var", slot)
        if k == "idx":
            return self.lval(e, scope, ctx)
        if k == "un":
            return ("un", e[1], self.pure(e[2], scope, ctx))
        if k == "cast":
            return ("cast", e[1], self.pure(e[2], scope, ctx))
        if k == "bin":
            a = self.pure(e[2], scope, ctx)
            b = self.pure(e[3], scope, ctx)
            return ("bin", e[1], a, b)
        if k in ("land", "lor"):
            a = self.pure(e[1], scope, ctx)
            if self.is_pure(e[2]):
                b = self.pure(e[2], scope, ctx)
                na = ("un", "!", ("un", "!", a))
                nb = ("un", "!", ("un", "!", b))
                op = "&" if k == "land" else "|"
                return ("bin", op, na, nb)
            self.n_inline += 1
            rl, jl = f"%sc{self.n_inline}.r", f"%sc{self.n_inline}.j"
            t = self.tmp(T_INT)
            if k == "land":
                self.emit(("asgn", ("var", t), ("num", 0, T_INT)))
                self.emit(("br", a, rl, jl))
            else:
                self.emit(("asgn", ("var", t), ("num", 1, T_INT)))
                self.emit(("br", a, jl, rl))
            self.ctl += 1
            self.emit(("labeldef", rl))
            b = self.pure(e[2], scope, ctx)
            self.emit(("asgn", ("var", t),
                       ("un", "!", ("un", "!", b))))
            self.emit(("labeldef", jl))
            self.ctl -= 1
            return ("var", t)
        if k == "asgn":
            lv = self.lval(e[2], scope, ctx)
            pv = self.pure(e[3], scope, ctx)
            ct = self.lv_type(lv)
            t = self.tmp(ct)
            if e[1] == "=":
                self.emit(("asgn", ("var", t), ("cast", ct, pv)))
            else:
                cur = self.lv_read(lv)
                self.emit(("asgn", ("var", t),
                           ("cast", ct, ("bin", e[1][:-1], cur, pv))))
            self.emit(("asgn", lv, ("var", t)))
            return ("var", t)
        if k == "inc":
            amount, pre, lve = e[1], e[2], e[3]
            lv = self.lval(lve, scope, ctx)
            ct = self.lv_type(lv)
            t = self.tmp(ct)
            cur = self.lv_read(lv)
            if pre:
                self.emit(("asgn", lv,
                           ("cast", ct, ("bin", "+", cur,
                                         ("num", amount, T_INT)))))
                self.emit(("asgn", ("var", t), self.lv_read(lv)))
            else:
                self.emit(("asgn", ("var", t), cur))
                self.emit(("asgn", lv,
                           ("cast", ct, ("bin", "+", self.lv_read(lv),
                                         ("num", amount, T_INT)))))
            return ("var", t)
        if k == "call":
            return self.call(e, scope, ctx)
        if k == "comma":
            self.effect(e[1], scope, ctx)
            return self.pure(e[2], scope, ctx)
        raise Frag(f"expression {k!r}")

    def is_pure(self, e):
        k = e[0]
        if k in ("num", "var", "str"):
            return True
        if k == "un":
            return self.is_pure(e[2])
        if k in ("cast", "szexpr"):
            return self.is_pure(e[2] if k == "cast" else e[1])
        if k == "bin":
            return self.is_pure(e[2]) and self.is_pure(e[3])
        if k in ("land", "lor"):
            return self.is_pure(e[1]) and self.is_pure(e[2])
        if k == "idx":
            return all(self.is_pure(x) for x in e[2])
        return False                   # asgn, inc, call, comma

    def typeof(self, pure):
        k = pure[0]
        if k == "num":
            return pure[2]
        if k == "var":
            return self.slots[pure[1]][0]
        if k == "idx":
            return self.slots[pure[1]][0]
        if k == "cast":
            return pure[1]
        if k == "un":
            if pure[1] == "!":
                return T_INT
            return promote(self.typeof(pure[2]))
        if k == "bin":
            op = pure[1]
            if op in ("==", "!=", "<", ">", "<=", ">=") or op in ("&&",
                                                                  "||"):
                return T_INT
            if op in ("<<", ">>"):
                return promote(self.typeof(pure[2]))
            return usual(self.typeof(pure[2]), self.typeof(pure[3]))
        raise Frag(f"typeof {k!r}")

    # label resolution -----------------------------------------------------------
    def resolve(self):
        labels, prog = {}, []
        for node in self.nodes:
            if node[0] == "labeldef":
                labels[node[1]] = len(prog)
            else:
                prog.append(node)
        labels["%HALT"] = -1
        labels["%ERR"] = -2
        remap = {}
        n_exec = 0
        for i, node in enumerate(prog):
            if node[0] != "jmp":
                remap[i] = n_exec
                n_exec += 1

        def resolve_to(i):
            """Fold jmp chains: the next *executable* node index, or -1
            (halt) / -2 (err). An all-jmp cycle is an empty infinite
            loop — bad can never fire on it, so it is halt-equivalent."""
            seen = set()
            while 0 <= i < len(prog) and prog[i][0] == "jmp":
                if i in seen:
                    return -1
                seen.add(i)
                i = labels[prog[i][1]]
            if i >= len(prog):
                return -1              # fell off the end: halt
            return i if i < 0 else remap[i]

        out = []
        for i, node in enumerate(prog):
            if node[0] == "jmp":
                continue
            nxt = resolve_to(i + 1)
            if node[0] == "br":
                out.append(("br", node[1], resolve_to(labels[node[2]]),
                            resolve_to(labels[node[3]])))
            else:                      # asgn, havoc: carry next
                out.append(node + (nxt,))
        self.prog = out
        self.entry = resolve_to(0)


def _arith(op, a, b, ta, tb):
    """The binary operators on already-pure values: returns
    (value, ctype). Comparison/logic return int 0/1."""
    if op in ("==", "!=", "<", ">", "<=", ">="):
        ct = usual(ta, tb)
        x, y = conv(a, ct), conv(b, ct)
        r = {"==": x == y, "!=": x != y, "<": x < y, ">": x > y,
             "<=": x <= y, ">=": x >= y}[op]
        return (1 if r else 0, T_INT)
    if op in ("<<", ">>"):
        ct = promote(ta)
        w, s = ct
        x = conv(a, ct)
        cnt = conv(b, promote(tb))
        if cnt < 0 or cnt >= w:
            if op == "<<" or not s or x >= 0:
                return (0, ct) if not (op == ">>" and s and x < 0) \
                    else (-1, ct)
            return (-1, ct)
        if op == "<<":
            return (conv(x << cnt, ct), ct)
        return (x >> cnt, ct)          # Python >> is arithmetic on ints
    ct = usual(ta, tb)
    w, s = ct
    x, y = conv(a, ct), conv(b, ct)
    if op == "+":
        return (conv(x + y, ct), ct)
    if op == "-":
        return (conv(x - y, ct), ct)
    if op == "*":
        return (conv(x * y, ct), ct)
    if op in ("/", "%"):
        if y == 0:                     # SMT-LIB total semantics
            if op == "%":
                return (x, ct)
            if not s:
                return (conv(-1, ct), ct)
            return ((-1 if x >= 0 else 1), ct)
        q = abs(x) // abs(y)
        if (x < 0) != (y < 0):
            q = -q
        if op == "/":
            return (conv(q, ct), ct)
        return (conv(x - q * y, ct), ct)
    ux, uy = x & ((1 << w) - 1), y & ((1 << w) - 1)
    if op == "&":
        return (conv(ux & uy, ct), ct)
    if op == "|":
        return (conv(ux | uy, ct), ct)
    if op == "^":
        return (conv(ux ^ uy, ct), ct)
    raise Frag(f"operator {op!r}")


# -- the emitter: the elaborated CFG as a bit-vector machine -------------------
# (appended by construction to the embedded c@1 front end above)
#
# One btor2 state per program counter and per slot; one btor2 input per
# havoc site (in site order, so the site->input-node map is a pure
# function of the program — lam.py reproduces it by re-running this
# builder). Each frame executes one CFG node, exactly the c@1
# discipline: next(slot) selects by pc, next(pc) follows the wiring,
# HALT and ERR are absorbing codes past the locations, and
# bad = (pc == ERR). Depth therefore carries exactly.

class Emit:
    def __init__(self, elab):
        self.elab = elab
        self.lines = []
        self.n = 0
        self.memo = {}
        prog = elab.prog
        self.L = len(prog)
        self.HALT, self.ERR = self.L, self.L + 1
        self.pc_w = max(1, (self.L + 1).bit_length())

        # inputs, in site order
        sites = {}
        for nd in prog:
            if nd[0] == "havoc":
                sites[nd[2]] = nd[3]
        self.site_input = {}
        for site in sorted(sites, key=lambda s: int(s[1:])):
            self.site_input[site] = self.new(
                "input", self.sort(sites[site][0]), site)

        # states: pc first, then every slot in elaboration order
        self.pc = self.new("state", self.sort(self.pc_w), "pc")
        self.new("init", self.sort(self.pc_w), self.pc,
                 self.const(self.code(elab.entry), self.pc_w))
        self.slot_state = {}
        self.slot_meta = {}
        for slot, (ct, dims) in elab.slots.items():
            if dims is not None:
                size = dims[0] * (dims[1] if len(dims) > 1 else 1)
                if size < 1:
                    raise Frag("zero-sized array")
                iw = max(1, (size - 1).bit_length())
                if iw > 30:
                    raise Frag("array too large for the pair")
                init = elab.globals.get(slot)
                if init is not None and any(init):
                    raise Frag("nonzero global array initializer — "
                               "outside the pair's fragment")
                st = self.new("state", self.asort(iw, ct[0]),
                              self.sym(slot))
                self.new("init", self.asort(iw, ct[0]), st,
                         self.const(0, ct[0]))
                self.slot_state[slot] = st
                self.slot_meta[slot] = ("arr", ct, size, iw)
            else:
                st = self.new("state", self.sort(ct[0]), self.sym(slot))
                self.new("init", self.sort(ct[0]), st,
                         self.const(elab.globals.get(slot, 0), ct[0]))
                self.slot_state[slot] = st
                self.slot_meta[slot] = ("sca", ct)

        # per-location effects
        self._writes = {}               # slot -> [(loc, value node)]
        pc_next = {}
        for i, nd in enumerate(prog):
            op = nd[0]
            if op == "asgn":
                lv, pure, nxt = nd[1], nd[2], nd[3]
                self.effect_store(i, lv, *self.compile(pure))
                pc_next[i] = self.const(self.code(nxt), self.pc_w)
            elif op == "havoc":
                lv, site, ct, nxt = nd[1], nd[2], nd[3], nd[4]
                self.effect_store(i, lv, self.site_input[site], ct)
                pc_next[i] = self.const(self.code(nxt), self.pc_w)
            elif op == "br":
                v, ct = self.compile(nd[1])
                nz = self.node(("nz", v), "neq", self.sort(1), v,
                               self.const(0, ct[0]))
                pc_next[i] = self.node(
                    ("pcbr", i), "ite", self.sort(self.pc_w), nz,
                    self.const(self.code(nd[2]), self.pc_w),
                    self.const(self.code(nd[3]), self.pc_w))
            else:
                raise Frag(f"node {op!r}")
        # next(pc): select by location, absorbing otherwise
        chain = self.pc
        for i in reversed(range(self.L)):
            chain = self.node(("pcsel", i), "ite", self.sort(self.pc_w),
                              self.eqpc(i), pc_next[i], chain)
        self.new("next", self.sort(self.pc_w), self.pc, chain)
        # next(slot): select by writing location
        for slot, wlist in self._writes.items():
            meta = self.slot_meta[slot]
            st = self.slot_state[slot]
            srt = self.asort(meta[3], meta[1][0]) if meta[0] == "arr" \
                else self.sort(meta[1][0])
            chain = st
            for loc, val in reversed(wlist):
                chain = self.node(("wsel", slot, loc), "ite", srt,
                                  self.eqpc(loc), val, chain)
            self.new("next", srt, st, chain)
        for slot, meta in self.slot_meta.items():
            if slot not in self._writes:
                srt = self.asort(meta[3], meta[1][0]) if meta[0] == "arr" \
                    else self.sort(meta[1][0])
                self.new("next", srt, self.slot_state[slot],
                         self.slot_state[slot])
        bad = self.node(("bad",), "eq", self.sort(1), self.pc,
                        self.const(self.ERR, self.pc_w))
        self.new("bad", bad)

    # -- plumbing ---------------------------------------------------------------
    def sym(self, slot):
        return "".join(ch if ch.isalnum() or ch == "_" else "_"
                       for ch in slot)

    def code(self, loc):
        return self.HALT if loc == -1 else (self.ERR if loc == -2
                                            else loc)

    def new(self, *parts):
        self.n += 1
        self.lines.append(f"{self.n} " +
                          " ".join(str(p) for p in parts))
        return self.n

    def node(self, key, *parts):
        got = self.memo.get(key)
        if got is None:
            got = self.memo[key] = self.new(*parts)
        return got

    def sort(self, w):
        return self.node(("sort", w), "sort", "bitvec", w)

    def asort(self, iw, ew):
        si, se = self.sort(iw), self.sort(ew)
        return self.node(("asort", iw, ew), "sort", "array", si, se)

    def const(self, v, w):
        v &= (1 << w) - 1
        return self.node(("c", v, w), "constd", self.sort(w), v)

    def eqpc(self, i):
        return self.node(("eqpc", i), "eq", self.sort(1), self.pc,
                         self.const(i, self.pc_w))

    def cast_to(self, vid, tf, tt):
        wf, sf = tf
        wt, st = tt
        if wf == wt:
            return vid
        if wt < wf:
            return self.node(("sl", vid, wt), "slice", self.sort(wt),
                             vid, wt - 1, 0)
        op = "sext" if sf else "uext"
        return self.node((op, vid, wt), op, self.sort(wt), vid, wt - wf)

    # -- stores -------------------------------------------------------------------
    def effect_store(self, loc, lv, vid, vt):
        slot = lv[1]
        meta = self.slot_meta[slot]
        if lv[0] == "var":
            val = self.cast_to(vid, vt, meta[1])
            self.add_write(slot, loc, val)
            return
        _, ct, size, iw = meta
        ok, low = self.index(lv[2][0], size, iw)
        val = self.cast_to(vid, vt, ct)
        arr = self.slot_state[slot]
        wr = self.node(("wr", loc), "write", self.asort(iw, ct[0]),
                       arr, low, val)
        guarded = self.node(("gwr", loc), "ite", self.asort(iw, ct[0]),
                            ok, wr, arr)
        self.add_write(slot, loc, guarded)

    def add_write(self, slot, loc, val):
        self._writes.setdefault(slot, []).append((loc, val))

    def index(self, pure, size, iw):
        """Bounds-guarded array index: ok (bv1) and the low iw bits.
        Mirrors the interpreter's `0 <= i < size` on the index's own
        evaluated value."""
        iv, ict = self.compile(pure)
        pt = promote(ict)
        iv = self.cast_to(iv, ict, pt)
        w, s = pt
        ok = self.node(("ult", iv, size, w), "ult", self.sort(1), iv,
                       self.const(size, w))
        if s:
            nonneg = self.node(("sge0", iv), "sgte", self.sort(1), iv,
                               self.const(0, w))
            ok = self.node(("and", ok, nonneg), "and", self.sort(1),
                           ok, nonneg)
        low = self.node(("sl", iv, iw), "slice", self.sort(iw), iv,
                        iw - 1, 0) if iw < w else iv
        return ok, low

    # -- expressions ----------------------------------------------------------------
    def compile(self, e):
        key = ("e", repr(e))
        got = self.memo.get(key)
        if got is not None:
            return got
        r = self._compile(e)
        self.memo[key] = r
        return r

    def _compile(self, e):
        k = e[0]
        if k == "num":
            return (self.const(e[1], e[2][0]), e[2])
        if k == "var":
            return (self.slot_state[e[1]], self.slot_meta[e[1]][1])
        if k == "idx":
            slot = e[1]
            _, ct, size, iw = self.slot_meta[slot]
            ok, low = self.index(e[2][0], size, iw)
            rd = self.node(("rd", slot, low), "read", self.sort(ct[0]),
                           self.slot_state[slot], low)
            v = self.node(("grd", ok, rd), "ite", self.sort(ct[0]), ok,
                          rd, self.const(0, ct[0]))
            return (v, ct)
        if k == "cast":
            v, tf = self.compile(e[2])
            return (self.cast_to(v, tf, e[1]), e[1])
        if k == "un":
            v, ct = self.compile(e[2])
            if e[1] == "!":
                z = self.node(("z", v, ct[0]), "eq", self.sort(1), v,
                              self.const(0, ct[0]))
                return (self.node(("u32", z), "uext", self.sort(32), z,
                                  31), T_INT)
            pt = promote(ct)
            v = self.cast_to(v, ct, pt)
            if e[1] == "+":
                return (v, pt)
            op = "neg" if e[1] == "-" else "not"
            return (self.node((op, v), op, self.sort(pt[0]), v), pt)
        if k == "bin":
            return self.binop(e[1], e[2], e[3])
        raise Frag(f"compile {k!r}")

    CMP = {"==": ("eq", "eq"), "!=": ("neq", "neq"),
           "<": ("slt", "ult"), ">": ("sgt", "ugt"),
           "<=": ("slte", "ulte"), ">=": ("sgte", "ugte")}
    ARITH = {"+": "add", "-": "sub", "*": "mul",
             "&": "and", "|": "or", "^": "xor"}

    def binop(self, op, ea, eb):
        a, ta = self.compile(ea)
        b, tb = self.compile(eb)
        if op in self.CMP:
            ct = usual(ta, tb)
            a = self.cast_to(a, ta, ct)
            b = self.cast_to(b, tb, ct)
            bop = self.CMP[op][0 if ct[1] else 1]
            c = self.node((bop, a, b), bop, self.sort(1), a, b)
            return (self.node(("u32", c), "uext", self.sort(32), c, 31),
                    T_INT)
        if op in ("<<", ">>"):
            ct = promote(ta)
            w, s = ct
            x = self.cast_to(a, ta, ct)
            pt = promote(tb)
            cnt = self.cast_to(b, tb, pt)
            if pt[0] <= w:
                # widen the count to the operand width: a negative
                # signed count sign-extends to a huge unsigned amount,
                # which btor2's shifts saturate — exactly the
                # interpreter's out-of-range rule
                cnt = self.cast_to(cnt, pt, (w, pt[1]))
                bop = "sll" if op == "<<" else ("sra" if s else "srl")
                return (self.node((bop, x, cnt), bop, self.sort(w), x,
                                  cnt), ct)
            # count wider than the operand: decide in the count's width
            ok = self.node(("ult", cnt, w, pt[0]), "ult", self.sort(1),
                           cnt, self.const(w, pt[0]))
            low = self.node(("sl", cnt, w), "slice", self.sort(w), cnt,
                            w - 1, 0)
            bop = "sll" if op == "<<" else ("sra" if s else "srl")
            shifted = self.node((bop, x, low), bop, self.sort(w), x, low)
            if op == "<<" or not s:
                sat = self.const(0, w)
            else:
                sat = self.node(("sra31", x), "sra", self.sort(w), x,
                                self.const(w - 1, w))
            return (self.node(("shg", op, x, cnt), "ite", self.sort(w),
                              ok, shifted, sat), ct)
        ct = usual(ta, tb)
        a = self.cast_to(a, ta, ct)
        b = self.cast_to(b, tb, ct)
        if op in self.ARITH:
            bop = self.ARITH[op]
        elif op == "/":
            bop = "sdiv" if ct[1] else "udiv"
        elif op == "%":
            bop = "srem" if ct[1] else "urem"
        else:
            raise Frag(f"operator {op!r}")
        return (self.node((bop, a, b), bop, self.sort(ct[0]), a, b), ct)


def build(src_text):
    funcs, globals_ = Parser(lex(src_text)).unit()
    elab = Elab(funcs, globals_)
    em = Emit(elab)
    return em



MASK = {}


def mask(w):
    m = MASK.get(w)
    if m is None:
        m = MASK[w] = (1 << w) - 1
    return m


class Model:
    def __init__(self):
        self.width = {}      # node id -> bit width
        self.node = {}       # node id -> (op, args) args = raw ints
        self.order = []      # node ids, ascending
        self.inputs = []     # input node ids
        self.states = []     # state node ids
        self.init = {}       # state id -> value node ref
        self.next = {}       # state id -> value node ref
        self.bads = []       # node refs
        self.constraints = []  # node refs


def parse(path):
    sorts = {}
    m = Model()
    with open(path) as fh:
        for raw in fh:
            line = raw.split(';', 1)[0].strip()
            if not line:
                continue
            t = line.split()
            nid, op = int(t[0]), t[1]
            if op == 'sort':
                if t[2] != 'bitvec':
                    raise ValueError('unsupported sort: ' + t[2])
                sorts[int(t[0])] = int(t[3])
                continue
            if op == 'init':
                m.init[int(t[3])] = int(t[4])
                continue
            if op == 'next':
                m.next[int(t[3])] = int(t[4])
                continue
            if op in ('bad', 'constraint'):
                (m.bads if op == 'bad' else m.constraints).append(int(t[2]))
                continue
            if op in ('output', 'fair', 'justice'):
                continue
            w = sorts[int(t[2])]
            m.width[nid] = w
            if op == 'input':
                m.inputs.append(nid)
                m.node[nid] = ('input', ())
            elif op == 'state':
                m.states.append(nid)
                m.node[nid] = ('state', ())
            elif op in ('const', 'constd', 'consth', 'zero', 'one', 'ones'):
                if op == 'zero':
                    v = 0
                elif op == 'one':
                    v = 1
                elif op == 'ones':
                    v = mask(w)
                elif op == 'const':
                    v = int(t[3], 2)
                elif op == 'constd':
                    v = int(t[3]) & mask(w)
                else:
                    v = int(t[3], 16)
                m.node[nid] = ('const', (v & mask(w),))
            else:
                args = []
                for a in t[3:]:          # a trailing symbol ends the args
                    try:
                        args.append(int(a))
                    except ValueError:
                        break
                m.node[nid] = (op, tuple(args))
            m.order.append(nid)
    return m


def _signed(v, w):
    return v - (1 << w) if v >> (w - 1) else v


def eval_frame(m, regs, frame_inputs, cache):
    """Evaluate every node for one frame. regs: state id -> value (may
    be lazily filled at frame 0 from init). Returns node id -> value."""
    vals = cache

    def ref(r):
        v = vals[abs(r)]
        return (~v & mask(m.width[abs(r)])) if r < 0 else v

    for nid in m.order:
        op, a = m.node[nid]
        w = m.width[nid]
        if op == 'const':
            vals[nid] = a[0]
        elif op == 'input':
            vals[nid] = int(frame_inputs.get(str(nid), 0)) & mask(w)
        elif op == 'state':
            if nid in regs:
                vals[nid] = regs[nid]
            else:
                # uninitialized (frame 0) or next-less: read the stimulus
                vals[nid] = int(frame_inputs.get(str(nid), 0)) & mask(w)
                regs[nid] = vals[nid]
        elif op == 'ite':
            vals[nid] = ref(a[1]) if ref(a[0]) else ref(a[2])
        elif op == 'slice':
            vals[nid] = (ref(a[0]) >> a[2]) & mask(w)
        elif op == 'uext':
            vals[nid] = ref(a[0])
        elif op == 'sext':
            sw = m.width[abs(a[0])]
            vals[nid] = _signed(ref(a[0]), sw) & mask(w)
        elif op == 'concat':
            vals[nid] = (ref(a[0]) << m.width[abs(a[1])]) | ref(a[1])
        elif op == 'not':
            vals[nid] = ~ref(a[0]) & mask(w)
        elif op == 'neg':
            vals[nid] = -ref(a[0]) & mask(w)
        elif op == 'inc':
            vals[nid] = (ref(a[0]) + 1) & mask(w)
        elif op == 'dec':
            vals[nid] = (ref(a[0]) - 1) & mask(w)
        elif op == 'redand':
            aw = m.width[abs(a[0])]
            vals[nid] = 1 if ref(a[0]) == mask(aw) else 0
        elif op == 'redor':
            vals[nid] = 1 if ref(a[0]) else 0
        elif op == 'redxor':
            vals[nid] = bin(ref(a[0])).count('1') & 1
        elif op == 'and':
            vals[nid] = ref(a[0]) & ref(a[1])
        elif op == 'or':
            vals[nid] = ref(a[0]) | ref(a[1])
        elif op == 'xor':
            vals[nid] = ref(a[0]) ^ ref(a[1])
        elif op == 'nand':
            vals[nid] = ~(ref(a[0]) & ref(a[1])) & mask(w)
        elif op == 'nor':
            vals[nid] = ~(ref(a[0]) | ref(a[1])) & mask(w)
        elif op == 'xnor':
            vals[nid] = ~(ref(a[0]) ^ ref(a[1])) & mask(w)
        elif op == 'implies':
            vals[nid] = (1 ^ ref(a[0])) | ref(a[1])
        elif op == 'iff':
            vals[nid] = 1 ^ ref(a[0]) ^ ref(a[1])
        elif op == 'eq':
            vals[nid] = 1 if ref(a[0]) == ref(a[1]) else 0
        elif op == 'neq':
            vals[nid] = 1 if ref(a[0]) != ref(a[1]) else 0
        elif op == 'ult':
            vals[nid] = 1 if ref(a[0]) < ref(a[1]) else 0
        elif op == 'ulte':
            vals[nid] = 1 if ref(a[0]) <= ref(a[1]) else 0
        elif op == 'ugt':
            vals[nid] = 1 if ref(a[0]) > ref(a[1]) else 0
        elif op == 'ugte':
            vals[nid] = 1 if ref(a[0]) >= ref(a[1]) else 0
        elif op in ('slt', 'slte', 'sgt', 'sgte'):
            aw = m.width[abs(a[0])]
            x, y = _signed(ref(a[0]), aw), _signed(ref(a[1]), aw)
            vals[nid] = 1 if ((op == 'slt' and x < y)
                              or (op == 'slte' and x <= y)
                              or (op == 'sgt' and x > y)
                              or (op == 'sgte' and x >= y)) else 0
        elif op == 'add':
            vals[nid] = (ref(a[0]) + ref(a[1])) & mask(w)
        elif op == 'sub':
            vals[nid] = (ref(a[0]) - ref(a[1])) & mask(w)
        elif op == 'mul':
            vals[nid] = (ref(a[0]) * ref(a[1])) & mask(w)
        elif op == 'udiv':
            d = ref(a[1])
            vals[nid] = (ref(a[0]) // d) & mask(w) if d else mask(w)
        elif op == 'urem':
            d = ref(a[1])
            vals[nid] = (ref(a[0]) % d) & mask(w) if d else ref(a[0])
        elif op in ('sdiv', 'srem', 'smod'):
            sa = _signed(ref(a[0]), w)
            sb = _signed(ref(a[1]), w)
            if op == 'sdiv':
                if sb == 0:
                    vals[nid] = 1 if sa < 0 else mask(w)
                else:
                    q = abs(sa) // abs(sb)
                    vals[nid] = (q if (sa < 0) == (sb < 0) else -q) \
                        & mask(w)
            elif op == 'srem':                 # sign follows dividend
                if sb == 0:
                    vals[nid] = sa & mask(w)
                else:
                    r = abs(sa) % abs(sb)
                    vals[nid] = (-r if sa < 0 else r) & mask(w)
            else:                              # smod: sign follows divisor
                if sb == 0:
                    vals[nid] = sa & mask(w)
                else:
                    u = abs(sa) % abs(sb)
                    if u == 0:
                        vals[nid] = 0
                    elif sa >= 0 and sb >= 0:
                        vals[nid] = u
                    elif sa < 0 and sb >= 0:
                        vals[nid] = (-u + sb) & mask(w)
                    elif sa >= 0 and sb < 0:
                        vals[nid] = (u + sb) & mask(w)
                    else:
                        vals[nid] = (-u) & mask(w)
        elif op == 'sll':
            sh = ref(a[1])
            vals[nid] = (ref(a[0]) << sh) & mask(w) if sh < w else 0
        elif op == 'srl':
            sh = ref(a[1])
            vals[nid] = ref(a[0]) >> sh if sh < w else 0
        elif op == 'sra':
            sh = ref(a[1])
            sv = _signed(ref(a[0]), w)
            vals[nid] = (sv >> sh) & mask(w) if sh < w else \
                (mask(w) if sv < 0 else 0)
        else:
            raise ValueError('unsupported op: ' + op)
    return vals, ref


def run(m, steps):
    """Run the model under a stimulus; return (bad_fired_depth | None,
    frames run). Constraints must hold at every frame up to the bad."""
    regs = {}
    for sid in m.states:
        if sid in m.init:
            pass                         # evaluated lazily at frame 0
    constrained = True
    for t, frame in enumerate(steps):
        vals = {}
        # frame 0: pre-fill initialized states (init refs evaluate in a
        # first pass restricted to nodes the init value depends on —
        # ids ascend, so a plain full pass with states-read-from-regs
        # works when we seed initialized states first)
        if t == 0:
            pending = {sid: r for sid, r in m.init.items()}
            # init values are constants or combinational over inputs;
            # evaluate them with a mini pass that treats *other*
            # uninitialized states as stimulus
            tmp_vals, tmp_ref = eval_frame(m, dict(), frame, {})
            for sid, r in pending.items():
                regs[sid] = tmp_ref(r) & mask(m.width[sid])
        vals, ref = eval_frame(m, regs, frame, {})
        if constrained:
            for c in m.constraints:
                if not ref(c):
                    constrained = False
                    break
        if constrained:
            for b in m.bads:
                if ref(b):
                    return t, t + 1
        nxt = {}
        for sid in m.states:
            if sid in m.next:
                nxt[sid] = ref(m.next[sid]) & mask(m.width[sid])
        regs = nxt
    return None, len(steps)

# -- AIG ----------------------------------------------------------------------
# Literal encoding: node n -> literals 2n (positive) and 2n+1 (negated).
# Node 0 is the constant FALSE, so literal 0 = false, 1 = true.


class AIG:
    def __init__(self):
        self.nodes = [None]          # node 0: constant; None marks a leaf
        self.hash = {}

    def var(self):
        self.nodes.append(None)
        return 2 * (len(self.nodes) - 1)

    def AND(self, a, b):
        if a > b:
            a, b = b, a
        if a == 0:
            return 0
        if a == 1:
            return b
        if a == b:
            return a
        if a ^ b == 1:
            return 0
        key = (a, b)
        lit = self.hash.get(key)
        if lit is None:
            self.nodes.append(key)
            lit = self.hash[key] = 2 * (len(self.nodes) - 1)
        return lit

    def OR(self, a, b):
        return self.AND(a ^ 1, b ^ 1) ^ 1

    def XOR(self, a, b):
        return self.OR(self.AND(a, b ^ 1), self.AND(a ^ 1, b))

    def MUX(self, c, t, e):
        return self.OR(self.AND(c, t), self.AND(c ^ 1, e))


# -- words (LSB-first literal vectors) ----------------------------------------

def wconst(v, w):
    return [(v >> i) & 1 for i in range(w)]


def wnot(g, a):
    return [x ^ 1 for x in a]


def wadd(g, a, b, cin=0):
    out, c = [], cin
    for x, y in zip(a, b):
        s = g.XOR(g.XOR(x, y), c)
        c = g.OR(g.AND(x, y), g.AND(c, g.XOR(x, y)))
        out.append(s)
    return out, c


def wsub(g, a, b):
    out, _ = wadd(g, a, wnot(g, b), 1)
    return out


def wneg(g, a):
    out, _ = wadd(g, wnot(g, a), wconst(0, len(a)), 1)
    return out


def weq(g, a, b):
    ne = 0
    for x, y in zip(a, b):
        ne = g.OR(ne, g.XOR(x, y))
    return ne ^ 1


def wult(g, a, b):
    lt = 0
    for x, y in zip(a, b):                 # LSB to MSB
        same = g.XOR(x, y) ^ 1
        lt = g.OR(g.AND(x ^ 1, y), g.AND(same, lt))
    return lt


def wslt(g, a, b):
    fa = a[:-1] + [a[-1] ^ 1]
    fb = b[:-1] + [b[-1] ^ 1]
    return wult(g, fa, fb)


def wmux(g, c, t, e):
    return [g.MUX(c, x, y) for x, y in zip(t, e)]


def wmul(g, a, b):
    w = len(a)
    acc = wconst(0, w)
    for i, bi in enumerate(b):
        if bi == 0:
            continue
        part = [0] * i + a[:w - i]
        if bi != 1:
            part = [g.AND(bi, x) for x in part]
        acc, _ = wadd(g, acc, part)
    return acc


def wudiv(g, a, b):
    """Restoring division; by construction b=0 yields q=ones, r=a."""
    w = len(a)
    bx = b + [0]                                     # width w+1
    rem = wconst(0, w + 1)
    q = [0] * w
    for i in range(w - 1, -1, -1):
        rem = [a[i]] + rem[:w]
        ge = wult(g, rem, bx) ^ 1
        rem = wmux(g, ge, wsub(g, rem, bx), rem)
        q[i] = ge
    return q, rem[:w]


def wshift(g, a, b, kind):
    """Barrel shifter; amounts >= width give 0 (or sign for sra)."""
    w = len(a)
    fill = a[-1] if kind == 'sra' else 0
    out = list(a)
    for s in range(w.bit_length()):
        if s >= len(b):
            break
        sh = 1 << s
        if kind == 'sll':
            shifted = [0] * min(sh, w) + out[:max(w - sh, 0)]
        else:
            shifted = out[min(sh, w):] + [fill] * min(sh, w)
        out = wmux(g, b[s], shifted, out)
    big = 0                                          # amount >= w?
    for j in range(len(b)):
        if (1 << j) >= w:
            big = g.OR(big, b[j])
    return [g.MUX(big, fill, x) for x in out]


# -- blasting a model over frames ---------------------------------------------

class Blaster:
    """Demand-driven blasting: a word is built for (node, frame) when a
    cone needs it, via an explicit work stack (no recursion limits).
    States resolve to their init expression at frame 0 (fresh variables
    when uninitialized) and to the previous frame's next elsewhere."""

    def __init__(self, model):
        self.m = model
        self.g = AIG()
        self.words = {}              # (node id, frame) -> literal vector

    def _deps(self, key):
        nid, t = key
        op, a = self.m.node[nid]
        if op in ('const', 'input'):
            return []
        if op == 'state':
            if t == 0:
                r = self.m.init.get(nid)
            else:
                r = self.m.next.get(nid)
            return [] if r is None else [(abs(r), t if t == 0 else t - 1)]
        if op == 'slice':
            return [(abs(a[0]), t)]
        if op in ('uext', 'sext'):
            return [(abs(a[0]), t)]
        return [(abs(r), t) for r in a]

    def _lookup(self, r, t):
        w = self.words[(abs(r), t)]
        return wnot(self.g, w) if r < 0 else w

    def _compute(self, key):
        m, g = self.m, self.g
        nid, t = key
        op, a = m.node[nid]
        w = m.width[nid]

        def ref(r, at=None):
            return self._lookup(r, t if at is None else at)

        if op == 'const':
            return wconst(a[0], w)
        if op == 'input':
            return [g.var() for _ in range(w)]
        if op == 'state':
            r = m.init.get(nid) if t == 0 else m.next.get(nid)
            if r is None:
                return [g.var() for _ in range(w)]
            return ref(r, t if t == 0 else t - 1)
        if op == 'ite':
            return wmux(g, ref(a[0])[0], ref(a[1]), ref(a[2]))
        if op == 'slice':
            return ref(a[0])[a[2]:a[1] + 1]
        if op == 'uext':
            return ref(a[0]) + [0] * a[1]
        if op == 'sext':
            x = ref(a[0])
            return x + [x[-1]] * a[1]
        if op == 'concat':
            return ref(a[1]) + ref(a[0])
        if op == 'not':
            return wnot(g, ref(a[0]))
        if op == 'neg':
            return wneg(g, ref(a[0]))
        if op == 'inc':
            out, _ = wadd(g, ref(a[0]), wconst(1, w))
            return out
        if op == 'dec':
            return wsub(g, ref(a[0]), wconst(1, w))
        if op in ('redand', 'redor', 'redxor'):
            x = ref(a[0])
            acc = x[0]
            for bit in x[1:]:
                acc = (g.AND(acc, bit) if op == 'redand'
                       else g.OR(acc, bit) if op == 'redor'
                       else g.XOR(acc, bit))
            return [acc]
        if op in ('and', 'or', 'xor', 'nand', 'nor', 'xnor'):
            x, y = ref(a[0]), ref(a[1])
            f = {'and': g.AND, 'or': g.OR, 'xor': g.XOR,
                 'nand': lambda p, q: g.AND(p, q) ^ 1,
                 'nor': lambda p, q: g.OR(p, q) ^ 1,
                 'xnor': lambda p, q: g.XOR(p, q) ^ 1}[op]
            return [f(p, q) for p, q in zip(x, y)]
        if op == 'implies':
            return [g.OR(ref(a[0])[0] ^ 1, ref(a[1])[0])]
        if op == 'iff':
            return [g.XOR(ref(a[0])[0], ref(a[1])[0]) ^ 1]
        if op == 'eq':
            return [weq(g, ref(a[0]), ref(a[1]))]
        if op == 'neq':
            return [weq(g, ref(a[0]), ref(a[1])) ^ 1]
        if op in ('ult', 'ulte', 'ugt', 'ugte'):
            x, y = ref(a[0]), ref(a[1])
            lit = (wult(g, x, y) if op == 'ult'
                   else wult(g, y, x) ^ 1 if op == 'ulte'
                   else wult(g, y, x) if op == 'ugt'
                   else wult(g, x, y) ^ 1)
            return [lit]
        if op in ('slt', 'slte', 'sgt', 'sgte'):
            x, y = ref(a[0]), ref(a[1])
            lit = (wslt(g, x, y) if op == 'slt'
                   else wslt(g, y, x) ^ 1 if op == 'slte'
                   else wslt(g, y, x) if op == 'sgt'
                   else wslt(g, x, y) ^ 1)
            return [lit]
        if op == 'add':
            out, _ = wadd(g, ref(a[0]), ref(a[1]))
            return out
        if op == 'sub':
            return wsub(g, ref(a[0]), ref(a[1]))
        if op == 'mul':
            return wmul(g, ref(a[0]), ref(a[1]))
        if op == 'udiv':
            q, _ = wudiv(g, ref(a[0]), ref(a[1]))
            return q
        if op == 'urem':
            b_ = ref(a[1])
            _, r = wudiv(g, ref(a[0]), b_)
            z = 0
            for bit in b_:
                z = g.OR(z, bit)
            return wmux(g, z, r, ref(a[0]))
        if op in ('sll', 'srl', 'sra'):
            return wshift(g, ref(a[0]), ref(a[1]), op)
        if op in ('sdiv', 'srem', 'smod'):
            x, y = ref(a[0]), ref(a[1])
            ax = wmux(g, x[-1], wneg(g, x), x)
            ay = wmux(g, y[-1], wneg(g, y), y)
            q, r = wudiv(g, ax, ay)
            if op == 'sdiv':
                diff = g.XOR(x[-1], y[-1])
                return wmux(g, diff, wneg(g, q), q)
            if op == 'srem':
                return wmux(g, x[-1], wneg(g, r), r)
            nz = 0
            for bit in r:
                nz = g.OR(nz, bit)
            nu = wneg(g, r)
            r10, _ = wadd(g, nu, y)
            r01, _ = wadd(g, r, y)
            pos = wmux(g, x[-1], r10, r)
            negb = wmux(g, x[-1], nu, r01)
            res = wmux(g, y[-1], negb, pos)
            return wmux(g, nz, res, r)
        raise ValueError('unsupported op: ' + op)

    def word(self, nid, t):
        key = (nid, t)
        if key in self.words:
            return self.words[key]
        stack = [key]
        fuel = 400 * (len(self.m.order) + 1) * (t + 2)
        while stack:
            fuel -= 1
            if fuel < 0:
                raise ValueError('circular definition while blasting')
            k = stack[-1]
            if k in self.words:
                stack.pop()
                continue
            missing = [d for d in self._deps(k) if d not in self.words]
            if missing:
                stack.extend(missing)
                continue
            self.words[k] = self._compute(k)
            stack.pop()
        return self.words[key]

    def _prop(self, refs, t):
        lit, neutral, comb = None, None, None
        return refs

    def bad(self, t):
        lit = 0
        for b in self.m.bads:
            x = self.word(abs(b), t)[0] ^ (1 if b < 0 else 0)
            lit = self.g.OR(lit, x)
        return lit

    def constraint(self, t):
        lit = 1
        for c in self.m.constraints:
            x = self.word(abs(c), t)[0] ^ (1 if c < 0 else 0)
            lit = self.g.AND(lit, x)
        return lit


# -- CDCL ---------------------------------------------------------------------

import heapq

UNSAT, SAT, UNKNOWN = 0, 1, 2


class Solver:
    """MiniSat-style CDCL: two-watched literals, 1UIP learning, VSIDS
    with a lazy heap, geometric restarts, phase saving. Deterministic:
    ties break on variable index, budgets count conflicts, not time."""

    def __init__(self):
        self.clauses = []
        self.watches = []            # watches[l]: clauses to visit when l asserts
        self.assign = []             # -1 unset / 0 false / 1 true
        self.level = []
        self.reason = []
        self.phase = []
        self.act = []
        self.heap = []               # lazy (-activity, var)
        self.trail = []
        self.lim = []                # decision level -> trail mark
        self.qhead = 0
        self.inc = 1.0
        self.conflicts = 0
        self.ok = True

    def new_var(self):
        v = len(self.assign)
        self.assign.append(-1)
        self.level.append(0)
        self.reason.append(-1)
        self.phase.append(0)
        self.act.append(0.0)
        self.watches.append([])
        self.watches.append([])
        heapq.heappush(self.heap, (0.0, v))
        return v

    def value(self, lit):
        a = self.assign[lit >> 1]
        return a if a < 0 else a ^ (lit & 1)

    def add_clause(self, lits):
        if not self.ok:
            return False
        out = sorted(set(lits))
        for lit in out:
            if lit ^ 1 in set(out):
                return True                       # tautology
        out = [l for l in out if self.value(l) != 0 or self.level[l >> 1] > 0]
        if any(self.value(l) == 1 and self.level[l >> 1] == 0 for l in out):
            return True                           # satisfied at root
        if not out:
            self.ok = False
            return False
        if len(out) == 1:
            if not self._enqueue(out[0], -1):
                self.ok = False
            return self.ok
        ci = len(self.clauses)
        self.clauses.append(out)
        self.watches[out[0] ^ 1].append(ci)
        self.watches[out[1] ^ 1].append(ci)
        return True

    def _enqueue(self, lit, reason):
        v = lit >> 1
        want = (lit & 1) ^ 1
        if self.assign[v] != -1:
            return self.assign[v] == want
        self.assign[v] = want
        self.level[v] = len(self.lim)
        self.reason[v] = reason
        self.trail.append(lit)
        return True

    def _propagate(self):
        while self.qhead < len(self.trail):
            p = self.trail[self.qhead]
            self.qhead += 1
            fl = p ^ 1
            ws = self.watches[p]
            i = j = 0
            n = len(ws)
            while i < n:
                ci = ws[i]
                i += 1
                cl = self.clauses[ci]
                if cl[0] == fl:
                    cl[0], cl[1] = cl[1], cl[0]
                first = cl[0]
                if self.value(first) == 1:
                    ws[j] = ci
                    j += 1
                    continue
                for k in range(2, len(cl)):
                    if self.value(cl[k]) != 0:
                        cl[1] = cl[k]
                        cl[k] = fl
                        self.watches[cl[1] ^ 1].append(ci)
                        break
                else:
                    ws[j] = ci
                    j += 1
                    if self.value(first) == 0:
                        while i < n:              # keep the rest watched
                            ws[j] = ws[i]
                            j += 1
                            i += 1
                        del ws[j:]
                        return ci
                    self._enqueue(first, ci)
            del ws[j:]
        return -1

    def _bump(self, v):
        self.act[v] += self.inc
        if self.act[v] > 1e100:
            for u in range(len(self.act)):
                self.act[u] *= 1e-100
            self.inc *= 1e-100
        heapq.heappush(self.heap, (-self.act[v], v))

    def _analyze(self, ci):
        learnt = [0]
        seen = set()
        counter = 0
        p = -1
        idx = len(self.trail)
        cur = len(self.lim)
        while True:
            for q in self.clauses[ci]:
                if q == p:
                    continue
                v = q >> 1
                if v not in seen and self.level[v] > 0:
                    seen.add(v)
                    self._bump(v)
                    if self.level[v] >= cur:
                        counter += 1
                    else:
                        learnt.append(q)
            while True:
                idx -= 1
                p = self.trail[idx]
                if (p >> 1) in seen:
                    break
            counter -= 1
            if counter == 0:
                break
            ci = self.reason[p >> 1]
        learnt[0] = p ^ 1
        if len(learnt) == 1:
            return learnt, 0
        mi = max(range(1, len(learnt)),
                 key=lambda i: self.level[learnt[i] >> 1])
        learnt[1], learnt[mi] = learnt[mi], learnt[1]
        return learnt, self.level[learnt[1] >> 1]

    def _backtrack(self, lvl):
        if len(self.lim) <= lvl:
            return
        mark = self.lim[lvl]
        for lit in self.trail[mark:]:
            v = lit >> 1
            self.phase[v] = self.assign[v]
            self.assign[v] = -1
            self.reason[v] = -1
            heapq.heappush(self.heap, (-self.act[v], v))
        del self.trail[mark:]
        del self.lim[lvl:]
        self.qhead = len(self.trail)

    def _decide(self):
        while self.heap:
            negact, v = heapq.heappop(self.heap)
            if self.assign[v] == -1 and -negact == self.act[v]:
                self.lim.append(len(self.trail))
                self._enqueue(2 * v + (self.phase[v] ^ 1), -1)
                return True
        for v in range(len(self.assign)):         # heap starved: sweep
            if self.assign[v] == -1:
                self.lim.append(len(self.trail))
                self._enqueue(2 * v + (self.phase[v] ^ 1), -1)
                return True
        return False

    def solve(self, assumptions, budget):
        """(status, model | None); UNKNOWN when the conflict budget is
        spent. Sound: UNSAT/SAT are never emitted on a guess."""
        if not self.ok:
            return UNSAT, None
        self._backtrack(0)
        base = self.conflicts
        restart_at, step = 512, 512
        while True:
            ci = self._propagate()
            if ci != -1:
                self.conflicts += 1
                if self.conflicts - base > budget:
                    self._backtrack(0)
                    return UNKNOWN, None
                if len(self.lim) <= len(assumptions):
                    self._backtrack(0)
                    return UNSAT, None
                learnt, bt = self._analyze(ci)
                self._backtrack(max(bt, len(assumptions)))
                if len(learnt) >= 2:
                    nci = len(self.clauses)
                    self.clauses.append(learnt)
                    self.watches[learnt[0] ^ 1].append(nci)
                    self.watches[learnt[1] ^ 1].append(nci)
                    self._enqueue(learnt[0], nci)
                else:
                    self._enqueue(learnt[0], -1)
                self.inc /= 0.95
                if self.conflicts - base > restart_at:
                    step = min(step * 2, 16384)
                    restart_at = self.conflicts - base + step
                    self._backtrack(len(assumptions))
            else:
                if len(self.lim) < len(assumptions):
                    a = assumptions[len(self.lim)]
                    if self.value(a) == 0:
                        self._backtrack(0)
                        return UNSAT, None
                    self.lim.append(len(self.trail))
                    self._enqueue(a, -1)
                    continue
                if not self._decide():
                    model = list(self.assign)
                    self._backtrack(0)
                    return SAT, model


# -- Tseitin ------------------------------------------------------------------

class CNF:
    """Incremental Tseitin encoding of AIG cones into one Solver."""

    def __init__(self, aig):
        self.g = aig
        self.sat = Solver()
        self.varof = {}

    def lit(self, aig_lit):
        if aig_lit < 2:
            raise ValueError('constant literal reached the CNF')
        stack = [aig_lit >> 1]
        while stack:
            n = stack[-1]
            if n in self.varof:
                stack.pop()
                continue
            gate = self.g.nodes[n]
            if gate is None:
                self.varof[n] = self.sat.new_var()
                stack.pop()
                continue
            a, b = gate
            need = [x >> 1 for x in (a, b)
                    if x > 1 and (x >> 1) not in self.varof]
            if need:
                stack.extend(need)
                continue
            stack.pop()
            x = self.varof[n] = self.sat.new_var()
            la = self._enc(a)
            lb = self._enc(b)
            self.sat.add_clause([2 * x + 1, la])
            self.sat.add_clause([2 * x + 1, lb])
            self.sat.add_clause([2 * x, la ^ 1, lb ^ 1])
        return self._enc(aig_lit)

    def _enc(self, aig_lit):
        return 2 * self.varof[aig_lit >> 1] | (aig_lit & 1)


def model_bits(cnf, model, word):
    """Integer value of an AIG word under a SAT model (missing bits: 0)."""
    v = 0
    for i, lit in enumerate(word):
        if lit == 1:
            v |= 1 << i
        elif lit > 1:
            var = cnf.varof.get(lit >> 1)
            if var is not None and model[var] == ((lit & 1) ^ 1):
                v |= 1 << i
    return v


# -- the BMC loop -------------------------------------------------------------

def free_at(m, t):
    """Node ids whose value at frame t is chosen freely (inputs, plus
    uninitialized states at frame 0 and next-less states elsewhere)."""
    out = list(m.inputs)
    for sid in m.states:
        if (t == 0 and sid not in m.init) or (t > 0 and sid not in m.next):
            out.append(sid)
    return sorted(out)


def bmc(m, mode, bound, budget, inf_cap=300, node_cap=4_000_000,
        clause_cap=None):
    """Run BMC to `bound` ('inf' allowed). Returns one of
      ('witness', steps, depth) — inputs extracted and self-replayed
      ('all', K)                — no bad at any depth <= K (proven)
      ('partial', K, note)      — budget/size out after proving K."""
    bl = Blaster(m)
    cnf = CNF(bl.g)
    proven = -1
    k = 0
    vacuous_from = None          # constraints constant-false at some frame
    while bound == 'inf' or k <= int(bound):
        if bound == 'inf' and k > inf_cap:
            return ('partial', proven, 'inf depth cap')
        if vacuous_from is not None:
            return ('all', 'inf')
        if len(bl.g.nodes) > node_cap:
            return ('partial', proven, 'AIG node cap')
        if clause_cap is not None and len(cnf.sat.clauses) > clause_cap:
            return ('partial', proven, 'CNF size cap')
        asm = []
        dead = False
        for t in range(k + 1):
            c = bl.constraint(t)
            if c == 0:
                vacuous_from = t
                dead = True
                break
            if c != 1:
                asm.append(cnf.lit(c))
        if not dead:
            b = bl.bad(k)
            if b == 0:
                proven = k
                k += 1
                continue
            if b != 1:
                asm.append(cnf.lit(b))
            status, model = cnf.sat.solve(asm, budget - cnf.sat.conflicts)
            if status == UNKNOWN:
                return ('partial', proven, 'conflict budget spent')
            if status == SAT:
                steps = []
                for t in range(k + 1):
                    frame = {}
                    for nid in free_at(m, t):
                        val = model_bits(cnf, model, bl.word(nid, t))
                        if val:
                            frame[str(nid)] = val
                    steps.append(frame)
                fired, _ = run(m, steps)
                if fired != k:
                    return ('partial', proven,
                            'internal: model did not replay at depth %d' % k)
                return ('witness', steps, k)
            proven = k
            if cnf.sat.conflicts >= budget:
                return ('partial', proven, 'conflict budget spent')
        else:
            # constraints impossible at frame `vacuous_from`: no valid
            # trace reaches it, so every deeper depth is vacuously safe
            if proven >= vacuous_from - 1:
                return ('all', 'inf')
            return ('partial', proven, 'constraints impossible yet unproven')
        k += 1
    return ('all', int(bound))


def strip_init(m):
    """The same machine from an arbitrary state: init dropped, so
    frame 0 states blast to fresh variables."""
    m2 = Model()
    m2.width, m2.node, m2.order = m.width, m.node, m.order
    m2.inputs, m2.states = m.inputs, m.states
    m2.init = {}
    m2.next = m.next
    m2.bads, m2.constraints = m.bads, m.constraints
    return m2


def _diff(bl, sid, i, v, t):
    """AIG literal: bit (sid, i) at frame t differs from v."""
    lit = bl.word(sid, t)[i]
    return lit ^ 1 if v == 1 else lit


def _query(cnf, aig_lits, budget):
    """Solve the conjunction of AIG literals. Constants resolve here:
    any 0 is UNSAT, 1s drop out."""
    asm = []
    for x in aig_lits:
        if x == 0:
            return UNSAT, None
        if x == 1:
            continue
        asm.append(cnf.lit(x))
    return cnf.sat.solve(asm, budget)


# -- bit-invariant ------------------------------------------------------------

def candidates_from_init(m):
    """Every bit of a next-carrying state whose frame-0 literal
    constant-folds; the fold value is the candidate constant."""
    bl0 = Blaster(m)
    out = []
    for sid in m.states:
        if sid not in m.next:
            continue
        for i, lit in enumerate(bl0.word(sid, 0)):
            if lit in (0, 1):
                out.append((sid, i, lit))
    return out


def synthesize_bits(m, budget):
    """Find an inductive, safe bit-invariant (possibly empty).
    Returns (bits, note): the sorted certificate list, or None."""
    cand = candidates_from_init(m)
    m2 = strip_init(m)
    bl = Blaster(m2)
    cnf = CNF(bl.g)
    while True:
        keep, ordiff = [], 0
        for (sid, i, v) in cand:
            d = _diff(bl, sid, i, v, 1)
            if d == 1:
                continue                       # provably breaks: drop
            keep.append((sid, i, v))
            ordiff = bl.g.OR(ordiff, d)        # 0-diffs vanish in OR
        cand = keep
        if not cand or ordiff == 0:
            break                              # inductive (maybe empty)
        hold = [_diff(bl, sid, i, v, 0) ^ 1 for (sid, i, v) in cand]
        status, model = _query(cnf, hold + [bl.constraint(0), ordiff],
                               budget)
        if status == UNKNOWN:
            return None, "synthesis budget spent"
        if status == UNSAT:
            break                              # inductive
        gone = set((sid, i, v) for (sid, i, v) in cand
                   if model_bits(cnf, model,
                                   [bl.word(sid, 1)[i]]) != v)
        if not gone:
            return None, "refinement made no progress"
        cand = [c for c in cand if c not in gone]
    hold = [_diff(bl, sid, i, v, 0) ^ 1 for (sid, i, v) in cand]
    status, _ = _query(cnf, hold + [bl.constraint(0), bl.bad(0)], budget)
    if status == UNSAT:
        return sorted(cand), ""
    return None, ("inductive bits do not exclude bad"
                  if status == SAT else "safety budget spent")


# -- k-induction --------------------------------------------------------------

def kind_step(bl, cnf, k, budget):
    """The step obligation over an init-free blaster: no-bad frames
    0..k-1 and constraints 0..k cannot end in bad at frame k."""
    lits = [bl.bad(t) ^ 1 for t in range(k)]
    lits += [bl.constraint(t) for t in range(k + 1)]
    lits.append(bl.bad(k))
    status, _ = _query(cnf, lits, budget)
    return status


# -- discharge ----------------------------------------------------------------

def _discharge_bits(m, bits, budget):
    seen = set()
    checked = []
    for entry in bits:
        if not isinstance(entry, list) or len(entry) != 3:
            return None
        sid, i, v = entry
        if (not isinstance(sid, int) or not isinstance(i, int)
                or v not in (0, 1) or sid not in m.next
                or not 0 <= i < m.width.get(sid, 0)
                or (sid, i) in seen):
            return None
        seen.add((sid, i))
        checked.append((sid, i, v))
    # init: no initial state may violate the invariant
    bl0 = Blaster(m)
    cnf0 = CNF(bl0.g)
    viol0 = 0
    for (sid, i, v) in checked:
        viol0 = bl0.g.OR(viol0, _diff(bl0, sid, i, v, 0))
    status, _ = _query(cnf0, [viol0], budget)
    if status != UNSAT:
        return None
    # consecution and safety, from an arbitrary invariant state
    bl = Blaster(strip_init(m))
    cnf = CNF(bl.g)
    hold = [_diff(bl, sid, i, v, 0) ^ 1 for (sid, i, v) in checked]
    viol1 = 0
    for (sid, i, v) in checked:
        viol1 = bl.g.OR(viol1, _diff(bl, sid, i, v, 1))
    status, _ = _query(cnf, hold + [bl.constraint(0), viol1], budget)
    if status != UNSAT:
        return None
    status, _ = _query(cnf, hold + [bl.constraint(0), bl.bad(0)], budget)
    if status != UNSAT:
        return None
    return {"init": "unsat", "consecution": "unsat", "safety": "unsat",
            "bits": len(checked)}


def _discharge_kind(m, k, budget):
    if not isinstance(k, int) or not 1 <= k <= 64:
        return None
    base = bmc(m, "forall", k - 1, budget)
    if base[0] != 'all':
        return None
    bl = Blaster(strip_init(m))
    cnf = CNF(bl.g)
    if kind_step(bl, cnf, k, budget) != UNSAT:
        return None
    return {"base": "all(%d)" % (k - 1), "step": "unsat", "k": k}


def discharge(m, cert, budget):
    """Re-check a certificate. Returns the obligations dict on a
    validated discharge, None on any failure."""
    if not isinstance(cert, dict):
        return None
    kind = cert.get("kind")
    if kind == "bit-invariant" and isinstance(cert.get("bits"), list):
        return _discharge_bits(m, cert["bits"], budget)
    if kind == "k-induction":
        return _discharge_kind(m, cert.get("k"), budget)
    return None

# -- the solving pipeline -----------------------------------------------------


def discharge_clauses(m, clauses, budget, clause_cap=5000):
    """Re-check a clause-invariant: validate shape, then init,
    consecution, safety — one-step queries with the machine's
    constraints assumed. Returns the obligations dict or None."""
    if not isinstance(clauses, list) or len(clauses) > clause_cap:
        return None
    checked = []
    for cl in clauses:
        if not isinstance(cl, list) or not cl:
            return None
        entry = []
        for e in cl:
            if not isinstance(e, list) or len(e) != 3:
                return None
            sid, i, v = e
            if (not isinstance(sid, int) or not isinstance(i, int)
                    or v not in (0, 1) or sid not in m.next
                    or not 0 <= i < m.width.get(sid, 0)):
                return None
            entry.append((sid, i, v))
        checked.append(entry)

    def bitlit(bl, sid, i, v, t):
        lit = bl.word(sid, t)[i]
        return lit if v == 1 else lit ^ 1

    def neginv(bl, t):
        out = 0
        for cl in checked:
            cube = 1
            for (sid, i, v) in cl:
                cube = bl.g.AND(cube, bitlit(bl, sid, i, 1 - v, t))
            out = bl.g.OR(out, cube)
        return out

    def query(cnf, aig_lits):
        asm = []
        for x in aig_lits:
            if x == 0:
                return UNSAT
            if x == 1:
                continue
            asm.append(cnf.lit(x))
        st, _ = cnf.sat.solve(asm, budget)
        return st

    # init: no constrained initial state escapes the invariant
    bl0 = Blaster(m)
    cnf0 = CNF(bl0.g)
    if query(cnf0, [bl0.constraint(0), neginv(bl0, 0)]) != UNSAT:
        return None
    # consecution and safety from an arbitrary invariant state
    bl = Blaster(strip_init(m))
    cnf = CNF(bl.g)
    hold = []
    for cl in checked:
        lit = 0
        for (sid, i, v) in cl:
            lit = bl.g.OR(lit, bitlit(bl, sid, i, v, 0))
        hold.append(lit)
    if query(cnf, hold + [bl.constraint(0), neginv(bl, 1)]) != UNSAT:
        return None
    if query(cnf, hold + [bl.constraint(0), bl.bad(0)]) != UNSAT:
        return None
    return {"init": "unsat", "consecution": "unsat", "safety": "unsat",
            "clauses": len(checked)}


# =============================================================================
# The C judge: atoms over the elaborated machine, obligations on its
# bit-vector encoding. Everything above is composed verbatim from the
# c interpreter's front end, the c--btor2 machine encoding, and the
# btor2 judges; the lineage of this judge names all three.
# =============================================================================

def _atom_state(em, atom):
    """An atom names a bit of the machine: ["pc", i] or ["slot", name,
    i]; returns (btor2 state id, bit) or None."""
    if not isinstance(atom, list) or not atom:
        return None
    if atom[0] == "pc" and len(atom) == 2 and isinstance(atom[1], int):
        return em.pc, atom[1]
    if (atom[0] == "slot" and len(atom) == 3 and isinstance(atom[1], str)
            and isinstance(atom[2], int)):
        sid = em.slot_state.get(atom[1])
        if sid is None or em.slot_meta[atom[1]][0] != "sca":
            return None
        return sid, atom[2]
    return None


def _map_bits(em, entries):
    out = []
    for e in entries:
        if not isinstance(e, list) or len(e) != 2 or e[1] not in (0, 1):
            return None
        st = _atom_state(em, e[0])
        if st is None:
            return None
        out.append([st[0], st[1], e[1]])
    return out


def judge(src, payload, budget=300000):
    """Discharge a C-level induction certificate: build the machine
    from the program's elaborated CFG, map the certificate's atoms to
    its state bits, and run the obligations. None on any failure."""
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    try:
        em = build(src)
    except (Frag, RecursionError):
        return None
    with open("machine.btor2", "w", encoding="utf-8") as fh:
        fh.write("\n".join(em.lines) + "\n")
    m = parse("machine.btor2")
    if kind == "k-induction":
        return _discharge_kind(m, payload.get("k"), budget)
    if kind == "bit-invariant":
        bits = payload.get("bits")
        if not isinstance(bits, list):
            return None
        mapped = _map_bits(em, bits)
        if mapped is None:
            return None
        return _discharge_bits(m, mapped, budget)
    if kind == "clause-invariant":
        clauses = payload.get("clauses")
        if not isinstance(clauses, list):
            return None
        mapped = []
        for cl in clauses:
            if not isinstance(cl, list):
                return None
            mc = _map_bits(em, cl)
            if mc is None:
                return None
            mapped.append(mc)
        return discharge_clauses(m, mapped, budget)
    return None


def main():
    if len(sys.argv) != 3:
        print("usage: check.py <program.c> <payload.json>", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as fh:
        src = fh.read()
    with open(sys.argv[2], encoding="utf-8") as fh:
        payload = json.load(fh)
    obligations = judge(src, payload)
    if obligations is None:
        print(json.dumps({"ok": False}, sort_keys=True))
    else:
        print(json.dumps({"ok": True, "obligations": obligations},
                         sort_keys=True))
    return 0


if __name__ == "__main__":
    import threading
    sys.setrecursionlimit(200000)
    threading.stack_size(512 << 20)
    _rc = []
    _t = threading.Thread(target=lambda: _rc.append(main()))
    _t.start()
    _t.join()
    sys.exit(_rc[0] if _rc else 1)
