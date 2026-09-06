"""MUTANT (overflow is ignored: a value that leaves its type is clamped to the type instead of wrapping, so the invariant written overclaims)

c-ai: interval abstract interpretation at C that writes `ranges`
certificates — the first search of Era 6 whose evidence is an
invariant found by abstraction rather than by unrolling (KERNEL.md
§3).

Usage: solve.py <program.c> <mode> <observable> <bound> <wall_s>

The program is elaborated by c's own front end (embedded verbatim
below, so the node numbering is exactly the judge's: pc over C nodes,
HALT = L, ERR = L + 1) and an interval per scalar slot is computed at
every node by chaotic iteration: havoc reads are the full range of
their type; every operation is evaluated in the interpreter's own
types, and a result that leaves its type takes the exact image of the
wrap when that image is one interval and the whole type otherwise —
never a guess; branches refine by comparison against constants and
other slots, through casts and constant offsets only where the
conversion is the identity on the current interval; arrays are never
tracked (an element read is the whole element type). Loop heads —
the targets of the back edges of a depth-first search — widen with
the program's own constants (and their neighbours and negations) as
thresholds; then a few decreasing rounds narrow, each accepted only
after the recomputed transformer is verified to stay below it, so
what is written is a checked post-fixpoint. When the post-fixpoint
excludes ERR the answer is all("inf") carrying {"schema": "ranges",
"payload": {"kind": "range-invariant", "nodes": {...}}} — only slots
narrower than their type are listed — discharged by c's `ranges`
judge at the stop and never taken on faith here. When ERR stays
reachable in the abstraction, when the program is outside the
fragment, when the iteration budget is spent, or in `exists` mode
(this search finds no witnesses), the answer is an honest partial.
Never a bare claim, never a witness. The budget derives from the wall
argument, never from the clock.
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


import heapq

# -- intervals ------------------------------------------------------------------
# An interval is (lo, hi) over the mathematical integers, always inside
# the range of the ctype it is read at; an abstract value is (lo, hi, ct).

CMP = ("==", "!=", "<", ">", "<=", ">=")
NEG = {"==": "!=", "!=": "==", "<": ">=", ">=": "<", ">": "<=", "<=": ">"}
MIRROR = {"==": "==", "!=": "!=", "<": ">", ">": "<", "<=": ">=", ">=": "<="}


def bounds(ct):
    w, s = ct
    return (-(1 << (w - 1)), (1 << (w - 1)) - 1) if s else (0, (1 << w) - 1)


def fits(lo, hi, ct):
    tmin, tmax = bounds(ct)
    return tmin <= lo and hi <= tmax


def wrap(lo, hi, ct):
    """The image of [lo, hi] under conversion to ct: itself when it
    fits, the wrapped interval when the image stays one interval, the
    whole type otherwise."""
    tmin, tmax = bounds(ct)
    return (max(lo, tmin), min(hi, tmax))


def tdiv(a, b):
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def arith(op, a, b):
    """The binary operators on abstract values, mirroring _arith."""
    ta, tb = a[2], b[2]
    if op in CMP:
        ct = usual(ta, tb)
        x, y = wrap(a[0], a[1], ct), wrap(b[0], b[1], ct)
        if op == "<":
            r = (1, 1) if x[1] < y[0] else (0, 0) if x[0] >= y[1] else (0, 1)
        elif op == "<=":
            r = (1, 1) if x[1] <= y[0] else (0, 0) if x[0] > y[1] else (0, 1)
        elif op == ">":
            r = (1, 1) if x[0] > y[1] else (0, 0) if x[1] <= y[0] else (0, 1)
        elif op == ">=":
            r = (1, 1) if x[0] >= y[1] else (0, 0) if x[1] < y[0] else (0, 1)
        else:
            apart = x[1] < y[0] or y[1] < x[0]
            same = x[0] == x[1] == y[0] == y[1]
            r = (1, 1) if same else (0, 0) if apart else (0, 1)
            if op == "!=":
                r = (1 - r[1], 1 - r[0])
        return r + (T_INT,)
    if op in ("<<", ">>"):
        ct = promote(ta)
        w = ct[0]
        x = wrap(a[0], a[1], ct)
        c = wrap(b[0], b[1], promote(tb))
        if op == ">>":
            if c[0] == c[1] and 0 <= c[0] < w:
                return (x[0] >> c[0], x[1] >> c[0], ct)
            return (x[0] if x[0] < 0 else 0, x[1] if x[1] >= 0 else -1, ct)
        if c[0] == c[1] and not 0 <= c[0] < w:
            return (0, 0, ct)
        if 0 <= c[0] and c[1] < w and x[0] >= 0:
            return wrap(x[0] << c[0], x[1] << c[1], ct) + (ct,)
        return bounds(ct) + (ct,)
    ct = usual(ta, tb)
    w, s = ct
    x, y = wrap(a[0], a[1], ct), wrap(b[0], b[1], ct)
    if op == "+":
        return wrap(x[0] + y[0], x[1] + y[1], ct) + (ct,)
    if op == "-":
        return wrap(x[0] - y[1], x[1] - y[0], ct) + (ct,)
    if op == "*":
        ps = [x[0] * y[0], x[0] * y[1], x[1] * y[0], x[1] * y[1]]
        return wrap(min(ps), max(ps), ct) + (ct,)
    if op == "/":
        vals = []
        parts = []
        if y[0] <= -1:
            parts.append((y[0], min(y[1], -1)))
        if y[1] >= 1:
            parts.append((max(y[0], 1), y[1]))
        for ylo, yhi in parts:
            for p in (x[0], x[1]):
                for q in (ylo, yhi):
                    vals.append(tdiv(p, q))
        if y[0] <= 0 <= y[1]:                 # SMT-LIB division by zero
            if not s:
                vals.append((1 << w) - 1)
            else:
                vals.extend([-1] if x[0] >= 0 else [1] if x[1] < 0
                            else [-1, 1])
        return wrap(min(vals), max(vals), ct) + (ct,)
    if op == "%":
        lo, hi = min(x[0], 0), max(x[1], 0)
        if not y[0] <= 0 <= y[1]:
            m = max(abs(y[0]), abs(y[1]))
            lo, hi = max(lo, -(m - 1)), min(hi, m - 1)
        return (lo, hi, ct)
    if op in ("&", "|", "^"):
        if x[0] == x[1] and y[0] == y[1]:
            v = _arith(op, x[0], y[0], ct, ct)[0]
            return (v, v, ct)
        if 0 <= x[0] and x[1] <= 1 and 0 <= y[0] and y[1] <= 1:
            if op == "&":
                return (min(x[0], y[0]), min(x[1], y[1]), ct)
            if op == "|":
                return (max(x[0], y[0]), max(x[1], y[1]), ct)
            return (0, 1, ct)
        if x[0] >= 0 and y[0] >= 0:
            if op == "&":
                return (0, min(x[1], y[1]), ct)
            full = (1 << max(x[1], y[1]).bit_length()) - 1
            if op == "|":
                return (max(x[0], y[0]), full, ct)
            return (0, full, ct)
        if op == "&" and (x[0] >= 0 or y[0] >= 0):
            return (0, x[1] if x[0] >= 0 else y[1], ct)
        return bounds(ct) + (ct,)
    raise Frag(f"operator {op!r}")


def allowed(op, y, ct):
    """The values v of ct with v op y' for some y' in y: an interval,
    ('ne', v) for a singleton disequality, None for no constraint."""
    tmin, tmax = bounds(ct)
    if op == "<":
        return (tmin, y[1] - 1)
    if op == "<=":
        return (tmin, y[1])
    if op == ">":
        return (y[0] + 1, tmax)
    if op == ">=":
        return (y[0], tmax)
    if op == "==":
        return (y[0], y[1])
    return ("ne", y[0]) if y[0] == y[1] else None


def cut(cur, allow):
    """cur narrowed by allow; None when empty."""
    if allow is None:
        return cur
    lo, hi = cur
    if allow[0] == "ne":
        v = allow[1]
        if lo == hi == v:
            return None
        if lo == v:
            lo += 1
        if hi == v:
            hi -= 1
        return (lo, hi)
    lo, hi = max(lo, allow[0]), min(hi, allow[1])
    return (lo, hi) if lo <= hi else None


def shift_allow(allow, d):
    if allow is None:
        return None
    if allow[0] == "ne":
        return ("ne", allow[1] + d)
    return (allow[0] + d, allow[1] + d)


class Budget(Exception):
    """The iteration budget is spent."""


class AI:
    """Intervals over the elaborated CFG; codes as the judge's: node
    index, HALT = L, ERR = L + 1."""

    def __init__(self, elab, budget):
        self.prog, self.slots = elab.prog, elab.slots
        self.L = len(self.prog)
        self.HALT, self.ERR = self.L, self.L + 1
        self.entry = self.code(elab.entry)
        self.scalars = sorted(s for s, (ct, dims) in self.slots.items()
                              if dims is None)
        self.init = {}
        for s in self.scalars:
            v = elab.globals.get(s, 0)
            self.init[s] = (v, v)
        self.budget = budget
        self.steps = 0
        consts = set()
        for nd in self.prog:
            self.collect(nd[2] if nd[0] == "asgn" else nd[1]
                         if nd[0] == "br" else None, consts)
        th = set()
        for v in consts:
            for u in (v, -v):
                th.update((u - 1, u, u + 1))
        self.thresholds = sorted(th)
        self.heads = self.loop_heads()

    def code(self, loc):
        return self.HALT if loc == -1 else (self.ERR if loc == -2 else loc)

    def collect(self, e, out):
        if e is None:
            return
        if e[0] == "num":
            out.add(e[1])
        elif e[0] in ("un", "cast"):
            self.collect(e[2], out)
        elif e[0] == "bin":
            self.collect(e[2], out)
            self.collect(e[3], out)
        elif e[0] == "idx":
            for x in e[2]:
                self.collect(x, out)

    def edges(self, n):
        nd = self.prog[n]
        if nd[0] == "asgn":
            return [self.code(nd[3])]
        if nd[0] == "havoc":
            return [self.code(nd[4])]
        return [self.code(nd[2]), self.code(nd[3])]

    def loop_heads(self):
        """Targets of the back edges of an iterative depth-first
        search from the entry: every cycle crosses one."""
        heads, color, stack = set(), {}, []
        if self.entry < self.L:
            stack.append((self.entry, 0))
            color[self.entry] = 1
        while stack:
            n, i = stack[-1]
            succ = [s for s in self.edges(n) if s < self.L]
            if i < len(succ):
                stack[-1] = (n, i + 1)
                s = succ[i]
                c = color.get(s)
                if c == 1:
                    heads.add(s)
                elif c is None:
                    color[s] = 1
                    stack.append((s, 0))
            else:
                color[n] = 2
                stack.pop()
        return heads

    # -- abstract evaluation ----------------------------------------------------------
    def ev(self, e, st):
        k = e[0]
        if k == "num":
            return (e[1], e[1], e[2])
        if k == "var":
            lo, hi = st[e[1]]
            return (lo, hi, self.slots[e[1]][0])
        if k == "idx":
            ct = self.slots[e[1]][0]
            return bounds(ct) + (ct,)
        if k == "cast":
            lo, hi, _ = self.ev(e[2], st)
            return wrap(lo, hi, e[1]) + (e[1],)
        if k == "un":
            lo, hi, ct = self.ev(e[2], st)
            if e[1] == "!":
                r = (1, 1) if lo == hi == 0 else (0, 0) if (lo > 0 or hi < 0) \
                    else (0, 1)
                return r + (T_INT,)
            pt = promote(ct)
            lo, hi = wrap(lo, hi, pt)
            if e[1] == "-":
                lo, hi = wrap(-hi, -lo, pt)
            elif e[1] == "~":
                lo, hi = wrap(~hi, ~lo, pt)
            return (lo, hi, pt)
        if k == "bin":
            return arith(e[1], self.ev(e[2], st), self.ev(e[3], st))
        raise Frag(f"eval {k!r}")

    # -- refinement by a branch ---------------------------------------------------------
    def refine(self, e, want, st):
        """st narrowed to the states where e is nonzero (want) or zero
        (not want); None when none remain."""
        lo, hi, ct = self.ev(e, st)
        if want and lo == hi == 0:
            return None
        if not want and (lo > 0 or hi < 0):
            return None
        k = e[0]
        if k == "un" and e[1] == "!":
            return self.refine(e[2], not want, st)
        if k == "cast":
            ilo, ihi, _ = self.ev(e[2], st)
            return self.refine(e[2], want, st) if fits(ilo, ihi, e[1]) \
                else st
        if k == "var":
            return self.narrow(e, ct, ("ne", 0) if want else (0, 0), st)
        if k != "bin":
            return st
        op = e[1]
        if op in ("&", "|"):
            both = want if op == "&" else not want
            if both:
                s1 = self.refine(e[2], want, st)
                return None if s1 is None else self.refine(e[3], want, s1)
            a, b = self.ev(e[2], st), self.ev(e[3], st)
            if 0 <= a[0] and a[1] <= 1 and 0 <= b[0] and b[1] <= 1:
                return self.join_opt(self.refine(e[2], want, st),
                                     self.refine(e[3], want, st))
            return st
        if op in CMP:
            nop = op if want else NEG[op]
            a, b = self.ev(e[2], st), self.ev(e[3], st)
            uct = usual(a[2], b[2])
            x, y = wrap(a[0], a[1], uct), wrap(b[0], b[1], uct)
            s1 = self.narrow(e[2], uct, allowed(nop, y, uct), st)
            if s1 is None:
                return None
            return self.narrow(e[3], uct, allowed(MIRROR[nop], x, uct), s1)
        return st

    def narrow(self, e, ct, allow, st):
        """st narrowed so that conv(e, ct) lies in allow — pushed into
        a slot only where every conversion on the way is the identity
        on the current interval."""
        if allow is None:
            return st
        lo, hi, _ = self.ev(e, st)
        if not fits(lo, hi, ct):
            return st
        k = e[0]
        if k == "var":
            new = cut(st[e[1]], allow)
            if new is None:
                return None
            if new == st[e[1]]:
                return st
            st2 = dict(st)
            st2[e[1]] = new
            return st2
        if k == "cast":
            return self.narrow(e[2], e[1], allow, st)
        if k == "bin" and e[1] in ("+", "-"):
            a, b = self.ev(e[2], st), self.ev(e[3], st)
            uct = usual(a[2], b[2])
            x, y = wrap(a[0], a[1], uct), wrap(b[0], b[1], uct)
            raw = (x[0] + y[0], x[1] + y[1]) if e[1] == "+" \
                else (x[0] - y[1], x[1] - y[0])
            if not fits(raw[0], raw[1], uct):
                return st
            if y[0] == y[1]:
                d = -y[0] if e[1] == "+" else y[0]
                return self.narrow(e[2], uct, shift_allow(allow, d), st)
            if e[1] == "+" and x[0] == x[1]:
                return self.narrow(e[3], uct, shift_allow(allow, -x[0]), st)
        return st

    # -- the lattice ------------------------------------------------------------------
    def join(self, a, b):
        return {s: (min(a[s][0], b[s][0]), max(a[s][1], b[s][1]))
                for s in self.scalars}

    def join_opt(self, a, b):
        if a is None:
            return b
        if b is None:
            return a
        return self.join(a, b)

    def leq(self, a, b):
        return all(b[s][0] <= a[s][0] and a[s][1] <= b[s][1]
                   for s in self.scalars)

    def widen(self, old, new):
        out = {}
        th = self.thresholds
        for s in self.scalars:
            (olo, ohi), (nlo, nhi) = old[s], new[s]
            tmin, tmax = bounds(self.slots[s][0])
            if nlo < olo:
                cands = [t for t in th if tmin <= t <= nlo]
                nlo = cands[-1] if cands else tmin
            if nhi > ohi:
                cands = [t for t in th if nhi <= t <= tmax]
                nhi = cands[0] if cands else tmax
            out[s] = (nlo, nhi)
        return out

    # -- one node --------------------------------------------------------------------
    def succs(self, n, st):
        self.steps += 1
        if self.steps > self.budget:
            raise Budget()
        nd = self.prog[n]
        if nd[0] == "asgn":
            lv = nd[1]
            if lv[0] == "var":
                lo, hi, _ = self.ev(nd[2], st)
                st = dict(st)
                st[lv[1]] = wrap(lo, hi, self.slots[lv[1]][0])
            return [(self.code(nd[3]), st)]
        if nd[0] == "havoc":
            st = dict(st)
            st[nd[1][1]] = wrap(*bounds(nd[3]), self.slots[nd[1][1]][0])
            return [(self.code(nd[4]), st)]
        out = []
        for want, tgt in ((True, nd[2]), (False, nd[3])):
            r = self.refine(nd[1], want, st)
            if r is not None:
                out.append((self.code(tgt), r))
        return out

    # -- the fixpoint ------------------------------------------------------------------
    def ascend(self):
        state = {self.entry: dict(self.init)}
        work, queued = [self.entry], {self.entry}
        while work:
            n = heapq.heappop(work)
            queued.discard(n)
            if n >= self.L:
                continue
            for tgt, st in self.succs(n, state[n]):
                old = state.get(tgt)
                new = st if old is None else self.join(old, st)
                if old is not None and tgt in self.heads:
                    new = self.widen(old, new)
                if old is None or new != old:
                    state[tgt] = new
                    if tgt not in queued:
                        heapq.heappush(work, tgt)
                        queued.add(tgt)
        return state

    def apply(self, state):
        """The plain transformer, from scratch: the entry's initial
        state joined with every transfer out of a reached node."""
        out = {self.entry: dict(self.init)}
        for n in sorted(state):
            if n >= self.L:
                continue
            for tgt, st in self.succs(n, state[n]):
                out[tgt] = st if tgt not in out else self.join(out[tgt], st)
        return out

    def below(self, a, b):
        return all(n in b and self.leq(a[n], b[n]) for n in a)

    def run(self, rounds=6):
        state = self.ascend()
        for _ in range(rounds):
            cand = self.apply(state)
            if cand == state or not self.below(cand, state):
                break
            if not self.below(self.apply(cand), cand):
                break
            state = cand
        if not self.below(self.apply(state), state):
            raise Frag("internal: the fixpoint is not inductive")
        return state

    def certificate(self, state):
        nodes = {}
        for n in sorted(state):
            entry = {}
            for s in self.scalars:
                lo, hi = state[n][s]
                if (lo, hi) != bounds(self.slots[s][0]):
                    entry[s] = [lo, hi]
            nodes[str(n)] = entry
        return {"kind": "range-invariant", "nodes": nodes}


def partial(note, **more):
    prog = {"note": note}
    prog.update(more)
    return {"kind": "partial", "progress": prog}


def solve(src, mode, observable, bound, wall_s):
    if observable != "bad":
        return partial("c-ai only decides 'bad'")
    if mode != "forall":
        return partial("c-ai finds no witnesses: interval abstract "
                       "interpretation proves, never refutes")
    try:
        funcs, globals_ = Parser(lex(src)).unit()
        elab = Elab(funcs, globals_)
    except Frag as exc:
        return partial(f"refused: {exc}")
    except RecursionError:
        return partial("refused: nesting beyond the front end's depth")
    ai = AI(elab, max(1000, int(500 * wall_s)))
    try:
        state = ai.run()
    except Budget:
        return partial("iteration budget spent before a fixpoint",
                       nodes=ai.L, steps=ai.steps)
    except Frag as exc:
        return partial(str(exc), nodes=ai.L)
    if ai.ERR in state:
        return partial("ERR reachable in the interval abstraction",
                       nodes=ai.L, reached=len(state), steps=ai.steps)
    return {"kind": "all", "bound": "inf",
            "cert": {"schema": "ranges", "payload": ai.certificate(state)}}


def main():
    if len(sys.argv) < 6:
        print("usage: solve.py <program.c> <mode> <observable> <bound> "
              "<wall_s>", file=sys.stderr)
        return 2
    prog, mode, observable, bound, wall = sys.argv[1:6]
    with open(prog, encoding="utf-8", errors="strict") as fh:
        src = fh.read()
    print(json.dumps(solve(src, mode, observable, bound, float(wall)),
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
