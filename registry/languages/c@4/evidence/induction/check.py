"""The `induction` certificate judge of c, revision 4 — the RISC-V-road
judge of revision 3, now over the bounded checker's array engine, so
that C programs with arrays are judged too (KERNEL.md §3, §6).

The machine is built as in revision 3 — the c front end, the
branch-before-fence variant of the c--riscv generator, the riscv
assembler and the riscv--btor2 instruction semantics, pc over C
nodes (codes: node index, HALT = L, ERR = L + 1), scalar memory
registerized word by word — and every C array becomes a btor2 array
state of its own. An element is reached only through the one address
shape the generator emits, base + (index << log2 size), with the
region's base a constant and, among the conjuncts of the path
condition at the access, the bounds guard for that very index — so an
element access outside that shape or outside its guard is refused,
never guessed at, and a scalar word can never be aliased by a
symbolic address. The obligations — init, consecution, safety for
invariants over pc and slot atoms; base and step for k-induction —
run on the bit-blaster with the eager array reduction, every array
lemma assumed as the valid fact it is. No search guides the answer;
the budget is a constant; every failure path refuses the upgrade.

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



LOAD_OP = {(1, False): "lbu", (8, True): "lb", (8, False): "lbu",
           (16, True): "lh", (16, False): "lhu",
           (32, True): "lw", (32, False): "lwu",
           (64, True): "ld", (64, False): "ld"}
STORE_OP = {1: "sb", 8: "sb", 16: "sh", 32: "sw", 64: "sd"}
DATA_DIR = {1: ".byte", 8: ".byte", 16: ".half", 32: ".word", 64: ".dword"}
LOG2 = {1: 0, 2: 1, 4: 2, 8: 3}


def _in_range(tf, tt):
    """Is every value of ctype tf already a value of ctype tt — so the
    canonical 64-bit pattern needs no re-canonicalization?"""
    (wf, sf), (wt, st) = tf, tt
    if sf == st:
        return wt >= wf
    if not sf and st:
        return wt > wf
    return False


class Gen:
    def __init__(self, elab):
        self.elab = elab
        self.prog, self.entry = elab.prog, elab.entry
        self.text = []
        self.data = []
        self.nlab = 0
        self.cell = {}                  # slot -> (label, ct, dims-or-None)
        self.sites = {}                 # site name -> integer
        self.layout()
        self.emit_nodes()

    # -- plumbing ---------------------------------------------------------------
    def sym(self, slot):
        return "S_" + "".join(ch if ch.isalnum() or ch == "_" else "_"
                              for ch in slot)

    def label(self):
        self.nlab += 1
        return f"L{self.nlab}"

    def loc(self, i):
        return "HALT" if i == -1 else ("ERR" if i == -2 else f"N{i}")

    def e(self, line):
        self.text.append("    " + line)

    def canon(self, tf, tt):
        """Re-canonicalize a0 from ctype tf to ctype tt (conv)."""
        if _in_range(tf, tt):
            return
        wt, st = tt
        if wt == 64:
            return
        if st:
            if wt == 32:
                self.e("sext.w a0, a0")
            else:
                self.e(f"slli a0, a0, {64 - wt}")
                self.e(f"srai a0, a0, {64 - wt}")
        elif wt == 1:
            self.e("andi a0, a0, 1")
        elif wt == 8:
            self.e("andi a0, a0, 255")
        else:
            self.e(f"slli a0, a0, {64 - wt}")
            self.e(f"srli a0, a0, {64 - wt}")

    def push(self):
        self.e("addi sp, sp, -8")
        self.e("sd a0, 0(sp)")

    def pop_a1(self):
        self.e("ld a1, 0(sp)")
        self.e("addi sp, sp, 8")

    # -- data ---------------------------------------------------------------------
    def layout(self):
        self.data.append("    .data")
        for slot, (ct, dims) in self.elab.slots.items():
            lab = self.sym(slot)
            size = SIZEOF[ct[0]]
            self.data.append(f"    .align {LOG2[size]}")
            if dims is not None:
                n = dims[0] * (dims[1] if len(dims) > 1 else 1)
                if n < 1:
                    raise Frag("zero-sized array")
                init = self.elab.globals.get(slot)
                if init is None or not any(init):
                    self.data.append(f"{lab}: .zero {n * size}")
                else:
                    vals = ", ".join(str(conv(v, ct) & ((1 << ct[0]) - 1))
                                     for v in init)
                    self.data.append(f"{lab}: {DATA_DIR[ct[0]]} {vals}")
                self.cell[slot] = (lab, ct, n)
            else:
                v = conv(self.elab.globals.get(slot, 0), ct)
                self.data.append(f"{lab}: {DATA_DIR[ct[0]]} "
                                 f"{v & ((1 << ct[0]) - 1)}")
                self.cell[slot] = (lab, ct, None)

    # -- nodes --------------------------------------------------------------------
    def emit_nodes(self):
        self.text.append("    .text")
        self.text.append("_start:")
        self.e(f"j {self.loc(self.entry)}")
        for i, nd in enumerate(self.prog):
            self.text.append(f"N{i}:")
            op = nd[0]
            if op == "asgn":
                ct = self.compile(nd[2])
                self.store(nd[1], ct)
                self.e("fence")
                self.e(f"j {self.loc(nd[3])}")
            elif op == "havoc":
                site = nd[2]
                k = int(site[1:])
                self.sites[site] = k
                self.e(f"li a1, {k}")
                self.e("li a7, 1")
                self.e("ecall")
                self.store(nd[1], (64, True))
                self.e("fence")
                self.e(f"j {self.loc(nd[4])}")
            elif op == "br":
                # the branch is decided before the fence, so no register
                # carries meaning across a frame boundary: every frame
                # begins at a node label with nothing but pc and memory
                self.compile(nd[1])
                take = self.label()
                self.e(f"bnez a0, {take}")
                self.e("fence")
                self.e(f"j {self.loc(nd[3])}")
                self.text.append(f"{take}:")
                self.e("fence")
                self.e(f"j {self.loc(nd[2])}")
            else:
                raise Frag(f"node {op!r}")
        self.text.append("HALT:")
        self.e("li a7, 93")
        self.e("ecall")
        self.text.append("ERR:")
        self.e("ebreak")

    # -- stores -------------------------------------------------------------------
    def store(self, lv, vt):
        lab, ct, n = self.cell[lv[1]]
        self.canon(vt, ct)
        sop = STORE_OP[ct[0]]
        if lv[0] == "var":
            self.e(f"la a1, {lab}")
            self.e(f"{sop} a0, 0(a1)")
            return
        self.push()
        self.index(lv[2][0])
        skip = self.label()
        self.e(f"li a1, {n}")
        self.e(f"bgeu a0, a1, {skip}")
        sh = LOG2[SIZEOF[ct[0]]]
        if sh:
            self.e(f"slli a0, a0, {sh}")
        self.e(f"la a1, {lab}")
        self.e("add a1, a1, a0")
        self.e("ld a0, 0(sp)")
        self.e(f"{sop} a0, 0(a1)")
        self.text.append(f"{skip}:")
        self.e("addi sp, sp, 8")

    def index(self, pure):
        """The index in a0, canonical at its promoted type: a negative
        index is a huge unsigned value, so one unsigned compare against
        the size is the interpreter's `0 <= i < size`."""
        ict = self.compile(pure)
        self.canon(ict, promote(ict))

    # -- expressions ----------------------------------------------------------------
    def compile(self, e):
        """Leave the canonical value of e in a0; return its ctype."""
        k = e[0]
        if k == "num":
            self.e(f"li a0, {conv(e[1], e[2])}")
            return e[2]
        if k == "var":
            lab, ct, _ = self.cell[e[1]]
            self.e(f"la a0, {lab}")
            self.e(f"{LOAD_OP[ct]} a0, 0(a0)")
            return ct
        if k == "idx":
            lab, ct, n = self.cell[e[1]]
            self.index(e[2][0])
            ok, done = self.label(), self.label()
            self.e(f"li a1, {n}")
            self.e(f"bltu a0, a1, {ok}")
            self.e("li a0, 0")
            self.e(f"j {done}")
            self.text.append(f"{ok}:")
            sh = LOG2[SIZEOF[ct[0]]]
            if sh:
                self.e(f"slli a0, a0, {sh}")
            self.e(f"la a1, {lab}")
            self.e("add a0, a0, a1")
            self.e(f"{LOAD_OP[ct]} a0, 0(a0)")
            self.text.append(f"{done}:")
            return ct
        if k == "cast":
            tf = self.compile(e[2])
            self.canon(tf, e[1])
            return e[1]
        if k == "un":
            ct = self.compile(e[2])
            if e[1] == "!":
                self.e("seqz a0, a0")
                return T_INT
            pt = promote(ct)
            self.canon(ct, pt)
            if e[1] == "+":
                return pt
            if e[1] == "-":
                self.e("negw a0, a0" if pt[0] == 32 else "neg a0, a0")
            else:
                self.e("not a0, a0")
            self.canon((64, True), pt)
            return pt
        if k == "bin":
            return self.binop(e[1], e[2], e[3])
        raise Frag(f"compile {k!r}")

    def operands(self, ea, eb, ca, cb):
        """Left operand canonical at ca into a1, right at cb into a0."""
        ta = self.compile(ea)
        self.canon(ta, ca)
        self.push()
        tb = self.compile(eb)
        self.canon(tb, cb)
        self.pop_a1()

    def binop(self, op, ea, eb):
        ta, tb = self.elab.typeof(ea), self.elab.typeof(eb)
        if op in ("==", "!=", "<", ">", "<=", ">="):
            ct = usual(ta, tb)
            self.operands(ea, eb, ct, ct)
            lt = "slt" if ct[1] else "sltu"
            if op == "==":
                self.e("xor a0, a1, a0")
                self.e("seqz a0, a0")
            elif op == "!=":
                self.e("xor a0, a1, a0")
                self.e("snez a0, a0")
            elif op == "<":
                self.e(f"{lt} a0, a1, a0")
            elif op == ">":
                self.e(f"{lt} a0, a0, a1")
            elif op == "<=":
                self.e(f"{lt} a0, a0, a1")
                self.e("xori a0, a0, 1")
            else:
                self.e(f"{lt} a0, a1, a0")
                self.e("xori a0, a0, 1")
            return T_INT
        if op in ("<<", ">>"):
            ct, pt = promote(ta), promote(tb)
            w, s = ct
            self.operands(ea, eb, ct, pt)
            sat, done = self.label(), self.label()
            self.e(f"sltiu a2, a0, {w}")
            self.e(f"beqz a2, {sat}")
            if w == 64:
                self.e(("sll" if op == "<<" else ("sra" if s else "srl"))
                       + " a0, a1, a0")
            else:
                self.e(("sllw" if op == "<<" else ("sraw" if s else "srlw"))
                       + " a0, a1, a0")
                self.canon((64, True), ct)
            self.e(f"j {done}")
            self.text.append(f"{sat}:")
            if op == "<<" or not s:
                self.e("li a0, 0")
            else:
                self.e("srai a0, a1, 63")
            self.text.append(f"{done}:")
            return ct
        ct = usual(ta, tb)
        w, s = ct
        self.operands(ea, eb, ct, ct)
        if op in ("+", "-", "*", "&", "|", "^"):
            base = {"+": "add", "-": "sub", "*": "mul",
                    "&": "and", "|": "or", "^": "xor"}[op]
            if w == 32 and op in ("+", "-", "*"):
                self.e(f"{base}w a0, a1, a0")
                self.canon((64, True), ct)
            else:
                self.e(f"{base} a0, a1, a0")
            return ct
        if op == "/":
            if not s:
                self.e(("divu" if w == 64 else "divuw") + " a0, a1, a0")
                self.canon((64, True), ct)
                return ct
            div, done = self.label(), self.label()
            self.e(f"bnez a0, {div}")
            self.e("slt a0, a1, zero")
            self.e("slli a0, a0, 1")
            self.e("addi a0, a0, -1")
            self.e(f"j {done}")
            self.text.append(f"{div}:")
            self.e(("div" if w == 64 else "divw") + " a0, a1, a0")
            self.text.append(f"{done}:")
            return ct
        if op == "%":
            if s:
                self.e(("rem" if w == 64 else "remw") + " a0, a1, a0")
            else:
                self.e(("remu" if w == 64 else "remuw") + " a0, a1, a0")
                self.canon((64, True), ct)
            return ct
        raise Frag(f"operator {op!r}")



M64 = (1 << 64) - 1
M32 = (1 << 32) - 1
DATA_BASE = 0x10000
FUEL = 1_000_000

ABI = {"zero": 0, "ra": 1, "sp": 2, "gp": 3, "tp": 4,
       "t0": 5, "t1": 6, "t2": 7, "s0": 8, "fp": 8, "s1": 9,
       "a0": 10, "a1": 11, "a2": 12, "a3": 13, "a4": 14, "a5": 15,
       "a6": 16, "a7": 17, "s2": 18, "s3": 19, "s4": 20, "s5": 21,
       "s6": 22, "s7": 23, "s8": 24, "s9": 25, "s10": 26, "s11": 27,
       "t3": 28, "t4": 29, "t5": 30, "t6": 31}


class Refuse(Exception):
    """Outside the language (or malformed): a loud refusal."""


def s64(v):
    v &= M64
    return v - (1 << 64) if v >> 63 else v


def s32(v):
    v &= M32
    return v - (1 << 32) if v >> 31 else v


def sext(v, w):
    v &= (1 << w) - 1
    return (v - (1 << w)) & M64 if v >> (w - 1) else v


def reg(tok):
    t = tok.strip()
    if t in ABI:
        return ABI[t]
    if t[:1] == "x" and t[1:].isdigit() and 0 <= int(t[1:]) < 32:
        return int(t[1:])
    raise Refuse(f"not a register: {tok!r}")


def imm(tok, labels=None):
    t = tok.strip()
    neg = t.startswith("-")
    if neg or t.startswith("+"):
        t = t[1:]
    if t.lower().startswith("0x"):
        v = int(t[2:], 16)
    elif t.isdigit():
        v = int(t)
    elif labels is not None and t in labels:
        v = labels[t]
    else:
        raise Refuse(f"not an immediate: {tok!r}")
    return -v if neg else v


def memop(tok):
    """`off(reg)` -> (offset, register)."""
    t = tok.strip()
    if not t.endswith(")") or "(" not in t:
        raise Refuse(f"not a memory operand: {tok!r}")
    off, base = t[:-1].split("(", 1)
    return (imm(off) if off.strip() else 0), reg(base)


def split_ops(text):
    """Split operands at top-level commas."""
    out, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


# -- assembly -----------------------------------------------------------------

class Program:
    def __init__(self):
        self.text = []          # [(op, operands-list, line-no)]
        self.labels = {}        # label -> text index or data address
        self.data = {}          # address -> byte
        self.entry = 0


def _string_bytes(lit):
    lit = lit.strip()
    if len(lit) < 2 or lit[0] != '"' or lit[-1] != '"':
        raise Refuse("string literal expected")
    out, i, body = [], 0, lit[1:-1]
    esc = {"n": 10, "t": 9, "r": 13, "0": 0, "\\": 92, '"': 34}
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body) and body[i + 1] in esc:
            out.append(esc[body[i + 1]])
            i += 2
        else:
            out.append(ord(ch) & 0xff)
            i += 1
    return out + [0]


def assemble(src):
    p = Program()
    section = "text"
    daddr = DATA_BASE
    pending = []                     # labels awaiting their data address
    for ln, raw in enumerate(src.split("\n"), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        while ":" in line:
            head, rest = line.split(":", 1)
            head = head.strip()
            if not head or " " in head or "\t" in head:
                break
            if head in p.labels:
                raise Refuse(f"line {ln}: duplicate label {head!r}")
            if section == "text":
                p.labels[head] = len(p.text)
            else:
                p.labels[head] = daddr
            line = rest.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        op = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""
        if op.startswith("."):
            if op == ".text":
                section = "text"
            elif op == ".data":
                section = "data"
            elif op in (".globl", ".global", ".section", ".type", ".size",
                        ".option", ".attribute", ".file", ".ident"):
                pass
            elif op in (".byte", ".half", ".short", ".word", ".dword",
                        ".quad"):
                width = {".byte": 1, ".half": 2, ".short": 2, ".word": 4,
                         ".dword": 8, ".quad": 8}[op]
                if section != "data":
                    raise Refuse(f"line {ln}: data directive in .text")
                for tok in split_ops(rest):
                    v = imm(tok) & ((1 << (8 * width)) - 1)
                    for k in range(width):
                        p.data[daddr + k] = (v >> (8 * k)) & 0xff
                    daddr += width
            elif op in (".zero", ".space"):
                n = imm(rest)
                if n < 0:
                    raise Refuse(f"line {ln}: negative size")
                daddr += n
            elif op in (".align", ".balign"):
                n = imm(rest)
                a = (1 << n) if op == ".align" else n
                if a > 0:
                    daddr = (daddr + a - 1) // a * a
            elif op in (".string", ".asciz"):
                for b in _string_bytes(rest):
                    p.data[daddr] = b
                    daddr += 1
            else:
                raise Refuse(f"line {ln}: unsupported directive {op}")
            continue
        if section != "text":
            raise Refuse(f"line {ln}: instruction in .data")
        p.text.append((op, split_ops(rest), ln))
    for name in ("_start", "main"):
        if name in p.labels and p.labels[name] < len(p.text):
            p.entry = p.labels[name]
            break
    return p



LOADS = {"lb": (1, True), "lh": (2, True), "lw": (4, True), "ld": (8, False),
         "lbu": (1, False), "lhu": (2, False), "lwu": (4, False)}
STORES = {"sb": 1, "sh": 2, "sw": 4, "sd": 8}
JUMPS = {"j", "jal", "call"}
COMPUTED = {"jr", "ret", "jalr"}
BRANCH2 = {"beq", "bne", "blt", "bge", "bltu", "bgeu", "bgt", "ble",
           "bgtu", "bleu"}
BRANCH1 = {"beqz", "bnez", "blez", "bgez", "bltz", "bgtz"}


def _successors(text, i):
    """Static successors inside a frame: none past a fence, an ebreak,
    or an ecall (whose meaning is decided symbolically: halt exits,
    an input read continues)."""
    op, ops, _ = text[i]
    if op in ("fence", "ebreak"):
        return []
    if op == "ecall":
        return [i + 1]
    if op in JUMPS:
        return ["L:" + (ops[1] if op == "jal" and len(ops) == 2
                        else ops[0])]
    if op in COMPUTED:
        raise Frag(f"line {text[i][2]}: computed jump {op} — outside "
                   "the pair's fragment")
    if op in BRANCH2:
        return ["L:" + ops[2], i + 1]
    if op in BRANCH1:
        return ["L:" + ops[1], i + 1]
    return [i + 1]


class B:
    """A btor2 emitter with hash-consing and constant folding; every
    node carries its width."""

    def __init__(self):
        self.lines = []
        self.n = 0
        self.memo = {}
        self.w = {}
        self.cv = {}                     # nid -> constant value
        self.parts = {}                  # nid -> the line's parts

    def new(self, w, *parts):
        self.n += 1
        self.lines.append(f"{self.n} " + " ".join(str(p) for p in parts))
        self.w[self.n] = w
        self.parts[self.n] = parts
        return self.n

    def node(self, key, w, *parts):
        got = self.memo.get(key)
        if got is None:
            got = self.memo[key] = self.new(w, *parts)
        return got

    def sort(self, w):
        return self.node(("sort", w), None, "sort", "bitvec", w)

    def asort(self):
        return self.node(("asort",), None, "sort", "array", self.sort(64),
                         self.sort(64))

    def const(self, v, w):
        v &= (1 << w) - 1
        nid = self.node(("c", v, w), w, "constd", self.sort(w), v)
        self.cv[nid] = v
        return nid

    def isc(self, nid):
        return nid in self.cv

    def val(self, nid):
        return self.cv[nid]

    def sval(self, nid):
        w, v = self.w[nid], self.cv[nid]
        return v - (1 << w) if v >> (w - 1) else v

    # -- operations ---------------------------------------------------------------
    def op1(self, op, a):
        w = self.w[a]
        if self.isc(a):
            v = self.val(a)
            if op == "not":
                return self.const(~v, w)
            if op == "neg":
                return self.const(-v, w)
        return self.node((op, a), w, op, self.sort(w), a)

    def op2(self, op, a, b, w=None):
        wa = self.w[a]
        w = wa if w is None else w
        if self.isc(a) and self.isc(b):
            x, y = self.val(a), self.val(b)
            sx, sy = self.sval(a), self.sval(b)
            m = (1 << wa) - 1
            f = {"add": lambda: x + y, "sub": lambda: x - y,
                 "and": lambda: x & y, "or": lambda: x | y,
                 "xor": lambda: x ^ y, "mul": lambda: x * y,
                 "sll": lambda: (x << y) if y < wa else 0,
                 "srl": lambda: (x >> y) if y < wa else 0,
                 "sra": lambda: (sx >> y) if y < wa else (m if sx < 0
                                                            else 0),
                 "eq": lambda: int(x == y), "neq": lambda: int(x != y),
                 "ult": lambda: int(x < y), "ulte": lambda: int(x <= y),
                 "ugt": lambda: int(x > y), "ugte": lambda: int(x >= y),
                 "slt": lambda: int(sx < sy), "slte": lambda: int(sx <= sy),
                 "sgt": lambda: int(sx > sy), "sgte": lambda: int(sx >= sy),
                 "concat": lambda: (x << self.w[b]) | y}.get(op)
            if f is not None:
                return self.const(f(), w)
        return self.node((op, a, b), w, op, self.sort(w), a, b)

    def add(self, a, b):
        if self.isc(b) and self.val(b) == 0:
            return a
        if self.isc(a) and self.val(a) == 0:
            return b
        return self.op2("add", a, b)

    def sub(self, a, b):
        return self.op2("sub", a, b)

    def and_(self, a, b):
        return self.op2("and", a, b)

    def or_(self, a, b):
        return self.op2("or", a, b)

    def xor(self, a, b):
        return self.op2("xor", a, b)

    def not_(self, a):
        return self.op1("not", a)

    def cmp(self, op, a, b):
        return self.op2(op, a, b, 1)

    def concat(self, a, b):
        return self.op2("concat", a, b, self.w[a] + self.w[b])

    def slice(self, a, hi, lo):
        w = hi - lo + 1
        if lo == 0 and w == self.w[a]:
            return a
        if self.isc(a):
            return self.const(self.val(a) >> lo, w)
        return self.node(("slice", a, hi, lo), w, "slice", self.sort(w), a,
                         hi, lo)

    def uext(self, a, w):
        wa = self.w[a]
        if wa == w:
            return a
        if self.isc(a):
            return self.const(self.val(a), w)
        return self.node(("uext", a, w), w, "uext", self.sort(w), a, w - wa)

    def sext(self, a, w):
        wa = self.w[a]
        if wa == w:
            return a
        if self.isc(a):
            return self.const(self.sval(a), w)
        return self.node(("sext", a, w), w, "sext", self.sort(w), a, w - wa)

    def ite(self, c, a, b):
        if a == b:
            return a
        if self.isc(c):
            return a if self.val(c) else b
        w = self.w[a]
        return self.node(("ite", c, a, b), w, "ite",
                         self.asort() if w is None else self.sort(w), c, a, b)

    def band(self, a, b):
        """Boolean and on bv1 with folding."""
        if self.isc(a):
            return b if self.val(a) else a
        if self.isc(b):
            return a if self.val(b) else b
        return self.and_(a, b)

    def bor(self, a, b):
        if self.isc(a):
            return a if self.val(a) else b
        if self.isc(b):
            return b if self.val(b) else a
        return self.or_(a, b)

    def bnot(self, a):
        return self.not_(a)

    def read(self, arr, idx):
        return self.node(("read", arr, idx), 64, "read", self.sort(64), arr,
                         idx)

    def write(self, arr, idx, v):
        return self.node(("write", arr, idx, v), None, "write", self.asort(),
                         arr, idx, v)


class Translator:
    def __init__(self, prog):
        self.p = prog
        self.b = B()
        b = self.b
        text = prog.text
        self.text = text
        if not text:
            raise Frag("empty text")
        # frame entry points: the entry and every instruction after a fence
        starts = [prog.entry]
        for i, (op, _, ln) in enumerate(text):
            if op == "fence":
                if i + 1 >= len(text):
                    raise Frag(f"line {ln}: fence at the end of the text")
                if i + 1 not in starts:
                    starts.append(i + 1)
        self.starts = starts
        self.block_of = {s: k for k, s in enumerate(starts)}
        n = len(starts)
        self.HALT, self.ERR = n, n + 1
        self.pcw = max(1, (n + 1).bit_length())
        self.pc = b.new(self.pcw, "state", b.sort(self.pcw), "pc")
        b.new(None, "init", b.sort(self.pcw), self.pc,
              b.const(self.block_of[prog.entry], self.pcw))
        # registers: only those ever written become states
        written = set()
        for op, ops, _ in text:
            rd = self._written(op, ops)
            if rd:
                written.add(rd)
        self.reg_state = {}
        self.reg0 = [b.const(0, 64)] * 32
        self.reg0[2] = b.const(0x7ffffff0, 64)
        for r in sorted(written):
            if r == 0:
                continue
            st = b.new(64, "state", b.sort(64), f"x{r}")
            b.new(None, "init", b.sort(64), st,
                  b.const(0x7ffffff0 if r == 2 else 0, 64))
            self.reg_state[r] = st
            self.reg0[r] = st
        # memory: one word-addressed array, the data section as its init
        self.mem = b.new(None, "state", b.asort(), "mem")
        init = self._data_init()
        b.new(None, "init", b.asort(), self.mem, init)
        # inputs, one per havoc site, discovered while translating
        self.site_input = {}
        # translate every block
        self.blocks = []
        for s in starts:
            self.blocks.append(self.block(s))
        self.finish()

    # -- helpers --------------------------------------------------------------------
    @staticmethod
    def _written(op, ops):
        if op == "ecall":
            return 10                                     # an input read
        if op in ("sb", "sh", "sw", "sd", "fence", "ebreak", "nop") \
                or op in BRANCH1 or op in BRANCH2:
            return None
        if op == "j":
            return None
        if op in ("jal", "call"):
            return reg(ops[0]) if (op == "jal" and len(ops) == 2) else 1
        if op in COMPUTED:
            raise Frag(f"computed jump {op} — outside the pair's fragment")
        return reg(ops[0])

    def _data_init(self):
        b = self.b
        words = {}
        for addr, byte in self.p.data.items():
            if byte:
                words[addr >> 3] = words.get(addr >> 3, 0) | (
                    byte << (8 * (addr & 7)))
        if not words:
            return b.const(0, 64)
        # a second array state, zero everywhere, carries the write chain
        zero = b.new(None, "state", b.asort(), "mem0")
        b.new(None, "init", b.asort(), zero, b.const(0, 64))
        b.new(None, "next", b.asort(), zero, zero)
        arr = zero
        for w in sorted(words):
            arr = b.write(arr, b.const(w, 64), b.const(words[w], 64))
        return arr

    def site(self, k):
        if k not in self.site_input:
            self.site_input[k] = self.b.new(64, "input", self.b.sort(64),
                                            f"site{k}")
        return self.site_input[k]

    # -- memory -----------------------------------------------------------------
    def load(self, mem, addr, width):
        b = self.b
        if b.isc(addr):
            a = b.val(addr)
            w0, off = a >> 3, a & 7
            if off + width <= 8:
                word = b.read(mem, b.const(w0, 64))
                return b.slice(word, off * 8 + width * 8 - 1, off * 8)
            pair = b.concat(b.read(mem, b.const((w0 + 1) & M64, 64)),
                            b.read(mem, b.const(w0, 64)))
            return b.slice(pair, off * 8 + width * 8 - 1, off * 8)
        w0 = b.op2("srl", addr, b.const(3, 64))
        w1 = b.add(w0, b.const(1, 64))
        pair = b.concat(b.read(mem, w1), b.read(mem, w0))
        sh = b.uext(b.op2("sll", b.and_(addr, b.const(7, 64)),
                          b.const(3, 64)), 128)
        return b.slice(b.op2("srl", pair, sh), width * 8 - 1, 0)

    def store(self, mem, addr, width, val):
        b = self.b
        v = b.slice(val, width * 8 - 1, 0)
        if b.isc(addr):
            a = b.val(addr)
            w0, off = a >> 3, a & 7
            if off + width <= 8:
                i0 = b.const(w0, 64)
                word = b.read(mem, i0)
                parts = []
                if (off + width) * 8 < 64:
                    parts.append(b.slice(word, 63, (off + width) * 8))
                parts.append(v)
                if off > 0:
                    parts.append(b.slice(word, off * 8 - 1, 0))
                new = parts[0]
                for part in parts[1:]:
                    new = b.concat(new, part)
                return b.write(mem, i0, new)
            i0, i1 = b.const(w0, 64), b.const((w0 + 1) & M64, 64)
            pair = b.concat(b.read(mem, i1), b.read(mem, i0))
            parts = [b.slice(pair, 127, (off + width) * 8), v]
            if off > 0:
                parts.append(b.slice(pair, off * 8 - 1, 0))
            new = parts[0]
            for part in parts[1:]:
                new = b.concat(new, part)
            mem = b.write(mem, i0, b.slice(new, 63, 0))
            return b.write(mem, i1, b.slice(new, 127, 64))
        w0 = b.op2("srl", addr, b.const(3, 64))
        w1 = b.add(w0, b.const(1, 64))
        pair = b.concat(b.read(mem, w1), b.read(mem, w0))
        sh = b.uext(b.op2("sll", b.and_(addr, b.const(7, 64)),
                          b.const(3, 64)), 128)
        mask = b.op2("sll", b.const((1 << (8 * width)) - 1, 128), sh)
        vext = b.op2("sll", b.uext(v, 128), sh)
        new = b.or_(b.and_(pair, b.not_(mask)), vext)
        mem = b.write(mem, w0, b.slice(new, 63, 0))
        return b.write(mem, w1, b.slice(new, 127, 64))

    # -- one block -------------------------------------------------------------------
    def block(self, start):
        """Symbolically execute the frame starting at `start`: a DAG of
        instructions (a cycle without a fence is refused), merged at
        joins by ite over the path conditions, which are pairwise
        disjoint by construction. Returns the exits."""
        b, text = self.b, self.text
        # reachability, cycle check, topological order
        order, state = [], {}
        stack = [(start, 0)]
        succ = {}

        def resolve(s):
            if isinstance(s, str):
                lab = s[2:]
                if lab not in self.p.labels or \
                        self.p.labels[lab] >= len(text):
                    raise Frag(f"unknown or non-text label {lab!r}")
                return self.p.labels[lab]
            if s >= len(text):
                raise Frag("control falls off the end of the text")
            return s

        def dfs(i):
            state[i] = 1
            succ[i] = [resolve(s) for s in _successors(text, i)]
            for s in succ[i]:
                if state.get(s) == 1:
                    raise Frag(f"line {text[s][2]}: a loop without a "
                               "fence — a frame that never ends")
                if s not in state:
                    dfs(s)
            state[i] = 2
            order.append(i)
        dfs(start)
        order.reverse()
        incoming = {start: [(b.const(1, 1), (list(self.reg0), self.mem))]}
        exits = []                       # (cond, kind, next, regs, mem)
        for i in order:
            inc = incoming.pop(i, [])
            if not inc:
                continue
            cond = inc[0][0]
            regs, mem = inc[0][1]
            for c, (rs, m) in inc[1:]:
                cond = b.bor(cond, c)
                regs = [b.ite(c, x, y) for x, y in zip(rs, regs)]
                mem = b.ite(c, m, mem)
            op, ops, ln = text[i]
            regs = list(regs)

            def go(target, c, rs, m):
                incoming.setdefault(target, []).append((c, (rs, m)))

            try:
                kind = self.step(op, ops, i, regs, mem)
            except (IndexError, ValueError, KeyError) as exc:
                raise Frag(f"line {ln}: malformed {op}: {exc}")
            if kind is None:
                mem = self._mem_effect(op, ops, regs, mem)
                go(succ[i][0], cond, regs, mem)
            elif kind == "fence":
                exits.append((cond, "fence", i + 1, regs, mem))
            elif kind == "bad":
                exits.append((cond, "bad", None, regs, mem))
            elif kind == "halt":
                exits.append((cond, "halt", None, regs, mem))
            else:                        # a branch condition (bv1 node)
                c = kind
                go(succ[i][0], b.band(cond, c), regs, mem)
                go(i + 1, b.band(cond, b.bnot(c)), regs, mem)
        return exits

    def _mem_effect(self, op, ops, regs, mem):
        if op in ("sb", "sh", "sw", "sd"):
            width = {"sb": 1, "sh": 2, "sw": 4, "sd": 8}[op]
            off, rs = memop(ops[1])
            addr = self.b.add(regs[rs], self.b.const(off, 64))
            return self.store(mem, addr, width, regs[reg(ops[0])])
        return mem

    def step(self, op, ops, i, regs, mem):
        """Register effects of one instruction on `regs` (in place),
        loads reading the path's memory term `mem`; returns None,
        'fence', 'bad', 'halt', or a branch condition."""
        b = self.b
        c64 = lambda v: b.const(v, 64)
        R = regs

        def setr(rd, v):
            if rd:
                R[rd] = v

        def s32x(v):                      # sign-extend the low 32 bits
            return b.sext(b.slice(v, 31, 0), 64)

        def lo32(v):
            return b.slice(v, 31, 0)

        def cmpu(o, x, y):
            return b.uext(b.cmp(o, x, y), 64)

        if op == "nop":
            return None
        if op == "li":
            setr(reg(ops[0]), c64(imm(ops[1])))
            return None
        if op == "la":
            lab = ops[1].strip()
            if lab not in self.p.labels:
                raise Frag(f"unknown label {lab!r}")
            setr(reg(ops[0]), c64(self.p.labels[lab]))
            return None
        if op == "mv":
            setr(reg(ops[0]), R[reg(ops[1])])
            return None
        if op == "not":
            setr(reg(ops[0]), b.not_(R[reg(ops[1])]))
            return None
        if op == "neg":
            setr(reg(ops[0]), b.sub(c64(0), R[reg(ops[1])]))
            return None
        if op == "negw":
            setr(reg(ops[0]), s32x(b.sub(c64(0), R[reg(ops[1])])))
            return None
        if op == "sext.w":
            setr(reg(ops[0]), s32x(R[reg(ops[1])]))
            return None
        if op == "seqz":
            setr(reg(ops[0]), cmpu("eq", R[reg(ops[1])], c64(0)))
            return None
        if op == "snez":
            setr(reg(ops[0]), cmpu("neq", R[reg(ops[1])], c64(0)))
            return None
        if op == "sltz":
            setr(reg(ops[0]), cmpu("slt", R[reg(ops[1])], c64(0)))
            return None
        if op == "sgtz":
            setr(reg(ops[0]), cmpu("sgt", R[reg(ops[1])], c64(0)))
            return None
        if op in BRANCH1:
            v = R[reg(ops[0])]
            o = {"beqz": "eq", "bnez": "neq", "blez": "slte", "bgez": "sgte",
                 "bltz": "slt", "bgtz": "sgt"}[op]
            return b.cmp(o, v, c64(0))
        if op in BRANCH2:
            x, y = R[reg(ops[0])], R[reg(ops[1])]
            o = {"beq": "eq", "bne": "neq", "blt": "slt", "bge": "sgte",
                 "bltu": "ult", "bgeu": "ugte", "bgt": "sgt", "ble": "slte",
                 "bgtu": "ugt", "bleu": "ulte"}[op]
            return b.cmp(o, x, y)
        if op == "j":
            return None
        if op == "call":
            setr(1, c64(4 * (i + 1)))
            return None
        if op == "jal":
            if len(ops) == 1:
                setr(1, c64(4 * (i + 1)))
            else:
                setr(reg(ops[0]), c64(4 * (i + 1)))
            return None
        if op == "lui":
            setr(reg(ops[0]), c64(sext(imm(ops[1]) << 12, 32)))
            return None
        if op == "auipc":
            setr(reg(ops[0]), c64(4 * i + (imm(ops[1]) << 12)))
            return None
        if op in LOADS:
            width, signed = LOADS[op]
            off, rs = memop(ops[1])
            addr = b.add(R[rs], c64(off))
            v = self.load(mem, addr, width)
            setr(reg(ops[0]), b.sext(v, 64) if signed else b.uext(v, 64))
            return None
        if op in STORES:
            return None                  # memory effect applied by the caller
        if op in ("addi", "slti", "sltiu", "xori", "ori", "andi", "slli",
                  "srli", "srai", "addiw", "slliw", "srliw", "sraiw"):
            rd, a, iv = reg(ops[0]), R[reg(ops[1])], imm(ops[2])
            if op == "addi":
                v = b.add(a, c64(iv))
            elif op == "slti":
                v = cmpu("slt", a, c64(iv))
            elif op == "sltiu":
                v = cmpu("ult", a, c64(iv))
            elif op == "xori":
                v = b.xor(a, c64(iv))
            elif op == "ori":
                v = b.or_(a, c64(iv))
            elif op == "andi":
                v = b.and_(a, c64(iv))
            elif op == "slli":
                v = b.op2("sll", a, c64(iv & 63))
            elif op == "srli":
                v = b.op2("srl", a, c64(iv & 63))
            elif op == "srai":
                v = b.op2("sra", a, c64(iv & 63))
            elif op == "addiw":
                v = s32x(b.add(a, c64(iv)))
            elif op == "slliw":
                v = b.sext(b.op2("sll", lo32(a), b.const(iv & 31, 32)), 64)
            elif op == "srliw":
                v = b.sext(b.op2("srl", lo32(a), b.const(iv & 31, 32)), 64)
            else:
                v = b.sext(b.op2("sra", lo32(a), b.const(iv & 31, 32)), 64)
            setr(rd, v)
            return None
        if op in ("add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra",
                  "or", "and", "addw", "subw", "sllw", "srlw", "sraw",
                  "mul", "mulh", "mulhsu", "mulhu", "div", "divu", "rem",
                  "remu", "mulw", "divw", "divuw", "remw", "remuw"):
            rd, a, y = reg(ops[0]), R[reg(ops[1])], R[reg(ops[2])]
            amt = b.and_(y, c64(63))
            amt5 = b.slice(y, 4, 0)
            if op == "add":
                v = b.add(a, y)
            elif op == "sub":
                v = b.sub(a, y)
            elif op == "sll":
                v = b.op2("sll", a, amt)
            elif op == "slt":
                v = cmpu("slt", a, y)
            elif op == "sltu":
                v = cmpu("ult", a, y)
            elif op == "xor":
                v = b.xor(a, y)
            elif op == "srl":
                v = b.op2("srl", a, amt)
            elif op == "sra":
                v = b.op2("sra", a, amt)
            elif op == "or":
                v = b.or_(a, y)
            elif op == "and":
                v = b.and_(a, y)
            elif op == "addw":
                v = s32x(b.add(a, y))
            elif op == "subw":
                v = s32x(b.sub(a, y))
            elif op == "sllw":
                v = b.sext(b.op2("sll", lo32(a), b.uext(amt5, 32)), 64)
            elif op == "srlw":
                v = b.sext(b.op2("srl", lo32(a), b.uext(amt5, 32)), 64)
            elif op == "sraw":
                v = b.sext(b.op2("sra", lo32(a), b.uext(amt5, 32)), 64)
            elif op == "mul":
                v = b.op2("mul", a, y)
            elif op in ("mulh", "mulhsu", "mulhu"):
                xa = b.sext(a, 128) if op != "mulhu" else b.uext(a, 128)
                xb = b.sext(y, 128) if op == "mulh" else b.uext(y, 128)
                v = b.slice(b.op2("mul", xa, xb), 127, 64)
            elif op == "div":
                v = b.ite(b.cmp("eq", y, c64(0)), c64(M64),
                          b.op2("sdiv", a, y))
            elif op == "divu":
                v = b.op2("udiv", a, y)
            elif op == "rem":
                v = b.op2("srem", a, y)
            elif op == "remu":
                v = b.op2("urem", a, y)
            elif op == "mulw":
                v = s32x(b.op2("mul", a, y))
            elif op == "divw":
                x32, y32 = lo32(a), lo32(y)
                v = b.ite(b.cmp("eq", y32, b.const(0, 32)), c64(M64),
                          b.sext(b.op2("sdiv", x32, y32), 64))
            elif op == "divuw":
                v = b.sext(b.op2("udiv", lo32(a), lo32(y)), 64)
            elif op == "remw":
                v = b.sext(b.op2("srem", lo32(a), lo32(y)), 64)
            else:
                v = b.sext(b.op2("urem", lo32(a), lo32(y)), 64)
            setr(rd, v)
            return None
        if op == "fence":
            return "fence"
        if op == "ebreak":
            return "bad"
        if op == "ecall":
            code = R[17]
            if not b.isc(code):
                raise Frag("ecall with a symbolic a7")
            cv = b.val(code)
            if cv == 93:
                return "halt"
            if cv == 1:
                site = R[11]
                if not b.isc(site):
                    raise Frag("input read at a symbolic site")
                setr(10, self.site(b.val(site)))
                return None
            raise Frag(f"ecall with a7={cv}")
        raise Frag(f"unknown instruction {op!r}")

    # -- the machine ------------------------------------------------------------------
    def finish(self):
        b = self.b
        pcw = self.pcw
        eqpc = {k: b.cmp("eq", self.pc, b.const(k, pcw))
                for k in range(len(self.starts))}
        next_pc, next_reg, next_mem = self.pc, dict(self.reg_state), self.mem
        for r in next_reg:
            next_reg[r] = self.reg_state[r]
        bads = [b.cmp("eq", self.pc, b.const(self.ERR, pcw))]
        for k, exits in reversed(list(enumerate(self.blocks))):
            if not exits:
                raise Frag("a frame with no exit")
            # per-block next values: ite-chains over the exits
            pc_k = b.const(self.HALT, pcw)
            regs_k = {r: self.reg_state[r] for r in self.reg_state}
            mem_k = self.mem
            bad_k = b.const(0, 1)
            for cond, kind, nxt, regs, mem in reversed(exits):
                if kind == "fence":
                    if nxt not in self.block_of:
                        raise Frag("fence with no following block")
                    target = b.const(self.block_of[nxt], pcw)
                elif kind == "bad":
                    target = b.const(self.ERR, pcw)
                    bad_k = b.bor(bad_k, cond)
                else:
                    target = b.const(self.HALT, pcw)
                pc_k = b.ite(cond, target, pc_k)
                for r in regs_k:
                    regs_k[r] = b.ite(cond, regs[r], regs_k[r])
                mem_k = b.ite(cond, mem, mem_k)
            next_pc = b.ite(eqpc[k], pc_k, next_pc)
            for r in next_reg:
                next_reg[r] = b.ite(eqpc[k], regs_k[r], next_reg[r])
            next_mem = b.ite(eqpc[k], mem_k, next_mem)
            bads.append(b.band(eqpc[k], bad_k))
        b.new(None, "next", b.sort(pcw), self.pc, next_pc)
        for r in sorted(next_reg):
            b.new(None, "next", b.sort(64), self.reg_state[r], next_reg[r])
        b.new(None, "next", b.asort(), self.mem, next_mem)
        bad = bads[0]
        for x in bads[1:]:
            bad = b.bor(bad, x)
        b.new(None, "bad", bad)




# =============================================================================
# The judge's machine: the elaborated CFG, compiled to RV64 with one
# fence per node, as a bit-vector transition system whose pc is the
# C node (codes: node index, HALT = L, ERR = L + 1) and whose memory
# is registerized word by word for every constant address, while a C
# array is a btor2 array state of its own, reached only through the
# one address shape the generator emits for an element, under a path
# condition that carries the bounds guard for that index.
# =============================================================================

class Machine(Translator):
    def __init__(self, prog, elab, gen):
        self.p = prog
        self.b = B()
        b = self.b
        self.text = prog.text
        self.L = len(elab.prog)
        self.HALT, self.ERR = self.L, self.L + 1
        self.pcw = max(1, (self.L + 1).bit_length())
        self.pc = b.new(self.pcw, "state", b.sort(self.pcw), "pc")
        b.new(None, "init", b.sort(self.pcw), self.pc,
              b.const(self.code_of(elab.entry), self.pcw))
        self.starts, self.block_code = [], {}
        for i in range(self.L):
            self.starts.append(self.label_index(f"N{i}"))
            self.block_code[self.starts[-1]] = i
        for name, code in (("HALT", self.HALT), ("ERR", self.ERR)):
            self.starts.append(self.label_index(name))
            self.block_code[self.starts[-1]] = code
        self.block_of = {s: k for k, s in enumerate(self.starts)}
        written = set()
        for op, ops, _ in self.text:
            rd = self._written(op, ops)
            if rd:
                written.add(rd)
        self.reg_state = {}
        self.reg0 = [b.const(0, 64)] * 32
        self.reg0[2] = b.const(0x7ffffff0, 64)
        for r in sorted(written):
            if r in (0, 2):
                continue
            st = b.new(64, "state", b.sort(64), f"x{r}")
            b.new(None, "init", b.sort(64), st, b.const(0, 64))
            self.reg_state[r] = st
            self.reg0[r] = st
        self.word_state = {}
        self.site_input = {}
        # cells: scalars by address; arrays as regions with their own
        # btor2 array state (index width as c--btor2 chooses it)
        self.cells = {}
        self.regions = {}                # base address -> region
        self.region_state = {}           # base address -> array state
        for slot, (lab, ct, n) in gen.cell.items():
            addr = prog.labels[lab]
            self.cells[slot] = (addr, ct, n)
            if n is not None:
                size = SIZEOF[ct[0]]
                iw = max(1, (n - 1).bit_length())
                if iw > 30:
                    raise Frag("array too large for the judge")
                init = elab.globals.get(slot)
                if init is not None and any(init):
                    raise Frag("nonzero global array initializer — "
                               "outside the judge's fragment")
                asort = b.node(("asort", iw, ct[0]), None, "sort", "array",
                               b.sort(iw), b.sort(ct[0]))
                st = b.new(None, "state", asort, gen.sym(slot))
                b.new(None, "init", asort, st, b.const(0, ct[0]))
                self.regions[addr] = (slot, ct, n, size, iw, asort)
                self.region_state[addr] = st
        self.blocks = [self.block(s) for s in self.starts]
        self.finish()

    def code_of(self, loc):
        return self.HALT if loc == -1 else (self.ERR if loc == -2 else loc)

    def label_index(self, name):
        if name not in self.p.labels or self.p.labels[name] >= len(self.text):
            raise Frag(f"no text label {name!r}")
        return self.p.labels[name]

    # -- scalar words ----------------------------------------------------------------
    def word(self, w):
        st = self.word_state.get(w)
        if st is None:
            v = 0
            for k in range(8):
                v |= self.p.data.get(w * 8 + k, 0) << (8 * k)
            st = self.b.new(64, "state", self.b.sort(64), f"m{w}")
            self.b.new(None, "init", self.b.sort(64), st,
                       self.b.const(v, 64))
            self.word_state[w] = st
        return st

    def _word_term(self, mem, w):
        return mem[w] if w in mem else self.word(w)

    # -- array elements ----------------------------------------------------------------
    def _element(self, addr, conjs, width):
        """Take a symbolic address apart: add(sll(idx, sh), base) or
        add(base, sll(idx, sh)) with `base` the address of an array
        region, `sh` its element shift, `width` its element size,
        and ult(idx, n) — or not(ugte(idx, n)) — among the conjuncts
        of the path condition. Returns (region base, low index)."""
        b = self.b
        parts = b.parts.get(addr)
        if not parts or parts[0] != "add":
            raise Frag("a symbolic address outside the element shape")
        x, y = parts[2], parts[3]
        if b.isc(x):
            x, y = y, x
        if not b.isc(y):
            raise Frag("a symbolic address without a constant base")
        base = b.val(y)
        region = self.regions.get(base)
        if region is None:
            raise Frag("a symbolic address whose base is not an array")
        slot, ct, n, size, iw, asort = region
        sh = LOG2[size]
        px = b.parts.get(x)
        if sh == 0:
            idx = x
        else:
            if (not px or px[0] != "sll" or not b.isc(px[3])
                    or b.val(px[3]) != sh):
                raise Frag("a symbolic address without the element shift")
            idx = px[2]
        if width != size:
            raise Frag("an element access of the wrong width")
        guard = b.cmp("ult", idx, b.const(n, 64))
        guard2 = b.bnot(b.cmp("ugte", idx, b.const(n, 64)))
        if guard not in conjs and guard2 not in conjs:
            raise Frag("an element access not under its bounds guard")
        return base, b.slice(idx, iw - 1, 0)

    def _region_of(self, a):
        """The array region a constant address falls in, if any: a
        constant-index element is still an element."""
        for base, region in self.regions.items():
            slot, ct, n, size, iw, asort = region
            if base <= a < base + n * size:
                if (a - base) % size:
                    raise Frag("a constant address inside an array, "
                               "misaligned to its elements")
                return base, (a - base) // size, size, iw
        return None

    def load(self, mem, addr, width):
        b = self.b
        if b.isc(addr):
            a = b.val(addr)
            hit = self._region_of(a)
            if hit is not None:
                base, i, size, iw = hit
                if width != size:
                    raise Frag("an element access of the wrong width")
                arr = mem[base] if base in mem else self.region_state[base]
                ew = self.regions[base][1][0]
                return b.node(("read", arr, b.const(i, iw)), ew, "read",
                              b.sort(ew), arr, b.const(i, iw))
            w0, off = a >> 3, a & 7
            if off + width <= 8:
                return b.slice(self._word_term(mem, w0),
                               off * 8 + width * 8 - 1, off * 8)
            pair = b.concat(self._word_term(mem, w0 + 1),
                            self._word_term(mem, w0))
            return b.slice(pair, off * 8 + width * 8 - 1, off * 8)
        base, low = self._element(addr, self._conjs, width)
        arr = mem[base] if base in mem else self.region_state[base]
        ew = self.regions[base][1][0]
        return b.node(("read", arr, low), ew, "read", b.sort(ew), arr, low)

    def store(self, mem, addr, width, val):
        b = self.b
        mem = dict(mem)
        if b.isc(addr):
            a = b.val(addr)
            hit = self._region_of(a)
            if hit is not None:
                base, i, size, iw = hit
                if width != size:
                    raise Frag("an element access of the wrong width")
                arr = mem[base] if base in mem else self.region_state[base]
                ew, asort = self.regions[base][1][0], self.regions[base][5]
                v = b.slice(val, ew - 1, 0)
                low = b.const(i, iw)
                mem[base] = b.node(("write", arr, low, v), None, "write",
                                   asort, arr, low, v)
                return mem
            v = b.slice(val, width * 8 - 1, 0)
            w0, off = a >> 3, a & 7
            if off + width <= 8:
                word = self._word_term(mem, w0)
                parts = []
                if (off + width) * 8 < 64:
                    parts.append(b.slice(word, 63, (off + width) * 8))
                parts.append(v)
                if off > 0:
                    parts.append(b.slice(word, off * 8 - 1, 0))
                new = parts[0]
                for part in parts[1:]:
                    new = b.concat(new, part)
                mem[w0] = new
                return mem
            pair = b.concat(self._word_term(mem, w0 + 1),
                            self._word_term(mem, w0))
            parts = [b.slice(pair, 127, (off + width) * 8), v]
            if off > 0:
                parts.append(b.slice(pair, off * 8 - 1, 0))
            new = parts[0]
            for part in parts[1:]:
                new = b.concat(new, part)
            mem[w0] = b.slice(new, 63, 0)
            mem[w0 + 1] = b.slice(new, 127, 64)
            return mem
        base, low = self._element(addr, self._conjs, width)
        arr = mem[base] if base in mem else self.region_state[base]
        ew, asort = self.regions[base][1][0], self.regions[base][5]
        v = b.slice(val, ew - 1, 0)
        mem[base] = b.node(("write", arr, low, v), None, "write", asort,
                           arr, low, v)
        return mem

    def merge_mem(self, c, m1, m2):
        out = {}
        for k in set(m1) | set(m2):
            if k in self.regions:
                a1 = m1[k] if k in m1 else self.region_state[k]
                a2 = m2[k] if k in m2 else self.region_state[k]
                out[k] = a1 if a1 == a2 else self.b.node(
                    ("aite", c, a1, a2), None, "ite", self.regions[k][5],
                    c, a1, a2)
            else:
                out[k] = self.b.ite(c, self._word_term(m1, k),
                                    self._word_term(m2, k))
        return out

    # -- one block ---------------------------------------------------------------------
    def block(self, start):
        """The block walk with memory as a map and, beside every path
        condition, the set of conjuncts it is made of — so an element
        access can show its bounds guard."""
        b, text = self.b, self.text
        order, state, succ = [], {}, {}

        def resolve(s):
            if isinstance(s, str):
                lab = s[2:]
                if lab not in self.p.labels or \
                        self.p.labels[lab] >= len(text):
                    raise Frag(f"unknown or non-text label {lab!r}")
                return self.p.labels[lab]
            if s >= len(text):
                raise Frag("control falls off the end of the text")
            return s

        def dfs(i):
            state[i] = 1
            succ[i] = [resolve(s) for s in _successors(text, i)]
            for s in succ[i]:
                if state.get(s) == 1:
                    raise Frag(f"line {text[s][2]}: a loop without a "
                               "fence — a frame that never ends")
                if s not in state:
                    dfs(s)
            state[i] = 2
            order.append(i)
        dfs(start)
        order.reverse()
        incoming = {start: [(b.const(1, 1), frozenset(),
                             (list(self.reg0), {}))]}
        exits = []
        for i in order:
            inc = incoming.pop(i, [])
            if not inc:
                continue
            cond, conjs = inc[0][0], inc[0][1]
            regs, mem = inc[0][2]
            for c, cj, (rs, m) in inc[1:]:
                cond = b.bor(cond, c)
                conjs = conjs & cj
                regs = [b.ite(c, x, y) for x, y in zip(rs, regs)]
                mem = self.merge_mem(c, m, mem)
            op, ops, ln = text[i]
            regs = list(regs)

            def go(target, c, cj, rs, m):
                incoming.setdefault(target, []).append((c, cj, (rs, m)))

            self._conjs = conjs
            try:
                kind = self.step(op, ops, i, regs, mem)
            except (IndexError, ValueError, KeyError) as exc:
                raise Frag(f"line {ln}: malformed {op}: {exc}")
            if kind is None:
                mem = self._mem_effect(op, ops, regs, mem)
                go(succ[i][0], cond, conjs, regs, mem)
            elif kind == "fence":
                exits.append((cond, "fence", i + 1, regs, mem))
            elif kind == "bad":
                exits.append((cond, "bad", None, regs, mem))
            elif kind == "halt":
                exits.append((cond, "halt", None, regs, mem))
            else:
                c = kind
                go(succ[i][0], b.band(cond, c), conjs | {c}, regs, mem)
                nc = b.bnot(c)
                go(i + 1, b.band(cond, nc), conjs | {nc}, regs, mem)
        return exits

    def next_code(self, i):
        if i >= len(self.text):
            raise Frag("fence at the end of the text")
        op, ops, ln = self.text[i]
        if op != "j" or len(ops) != 1:
            raise Frag(f"line {ln}: a frame must begin with a jump to a "
                       "node label")
        idx = self.label_index(ops[0].strip())
        if idx not in self.block_code:
            raise Frag(f"line {ln}: jump to a non-node label")
        return self.block_code[idx]

    def finish(self):
        b = self.b
        pcw = self.pcw
        words = sorted(self.word_state)
        bases = sorted(self.region_state)
        eqpc = {k: b.cmp("eq", self.pc, b.const(self.block_code[s], pcw))
                for k, s in enumerate(self.starts)}
        next_pc = self.pc
        next_reg = dict(self.reg_state)
        next_word = {w: self.word_state[w] for w in words}
        next_arr = {a: self.region_state[a] for a in bases}
        bads = []
        for k, exits in reversed(list(enumerate(self.blocks))):
            if not exits:
                raise Frag("a frame with no exit")
            pc_k = b.const(self.HALT, pcw)
            regs_k = dict(self.reg_state)
            words_k = {w: self.word_state[w] for w in words}
            arrs_k = {a: self.region_state[a] for a in bases}
            bad_k = b.const(0, 1)
            for cond, kind, nxt, regs, mem in reversed(exits):
                if kind == "fence":
                    target = b.const(self.next_code(nxt), pcw)
                elif kind == "bad":
                    target = b.const(self.ERR, pcw)
                    bad_k = b.bor(bad_k, cond)
                else:
                    target = b.const(self.HALT, pcw)
                pc_k = b.ite(cond, target, pc_k)
                for r in regs_k:
                    regs_k[r] = b.ite(cond, regs[r], regs_k[r])
                for w in words:
                    words_k[w] = b.ite(cond, self._word_term(mem, w),
                                       words_k[w])
                for a in bases:
                    cur = mem[a] if a in mem else self.region_state[a]
                    if cur != arrs_k[a]:
                        arrs_k[a] = b.node(("aite", cond, cur, arrs_k[a]),
                                           None, "ite", self.regions[a][5],
                                           cond, cur, arrs_k[a])
            next_pc = b.ite(eqpc[k], pc_k, next_pc)
            for r in next_reg:
                next_reg[r] = b.ite(eqpc[k], regs_k[r], next_reg[r])
            for w in words:
                next_word[w] = b.ite(eqpc[k], words_k[w], next_word[w])
            for a in bases:
                if arrs_k[a] != next_arr[a]:
                    next_arr[a] = b.node(
                        ("aite", eqpc[k], arrs_k[a], next_arr[a]), None,
                        "ite", self.regions[a][5], eqpc[k], arrs_k[a],
                        next_arr[a])
            bads.append(b.band(eqpc[k], bad_k))
        b.new(None, "next", b.sort(pcw), self.pc, next_pc)
        for r in sorted(next_reg):
            b.new(None, "next", b.sort(64), self.reg_state[r], next_reg[r])
        for w in words:
            b.new(None, "next", b.sort(64), self.word_state[w],
                  next_word[w])
        for a in bases:
            b.new(None, "next", self.regions[a][5], self.region_state[a],
                  next_arr[a])
        bad = bads[0]
        for x in bads[1:]:
            bad = b.bor(bad, x)
        b.new(None, "bad", bad)

    def atom(self, atom):
        """An atom names a state bit: ["pc", i] or ["slot", name, i]."""
        if not isinstance(atom, list) or not atom:
            return None
        if atom[0] == "pc" and len(atom) == 2 and isinstance(atom[1], int):
            return (self.pc, atom[1]) if 0 <= atom[1] < self.pcw else None
        if (atom[0] == "slot" and len(atom) == 3 and isinstance(atom[1], str)
                and isinstance(atom[2], int)):
            cell = self.cells.get(atom[1])
            if cell is None or cell[2] is not None:
                return None
            addr, ct, _ = cell
            if not 0 <= atom[2] < ct[0]:
                return None
            w, off = addr >> 3, addr & 7
            if off * 8 + ct[0] > 64:
                return None
            return self.word(w), off * 8 + atom[2]
        return None


def build(src_text):
    funcs, globals_ = Parser(lex(src_text)).unit()
    elab = Elab(funcs, globals_)
    gen = Gen(elab)
    text = "\n".join(gen.data) + "\n" + "\n".join(gen.text) + "\n"
    prog = assemble(text)
    return Machine(prog, elab, gen)

MASK = {}


def mask(w):
    m = MASK.get(w)
    if m is None:
        m = MASK[w] = (1 << w) - 1
    return m


def vkey(v):
    if isinstance(v, tuple):
        return (1, vkey(v[1]), tuple((i, vkey(x)) for i, x in v[2]))
    return (0, v)


def acanon(default, items, iw):
    """The canonical sparse array (see btor2@3): default-valued entries
    drop, the default covers the largest domain share, ties to the
    least value — so extensional equality is tuple equality."""
    items = {i: v for i, v in items.items() if v != default}
    dom = 1 << iw
    n = len(items)
    counts = {}
    for v in items.values():
        counts[v] = counts.get(v, 0) + 1
    best, cands = dom - n, [default]
    for v in sorted(counts, key=vkey):
        c = counts[v]
        if c > best:
            best, cands = c, [v]
        elif c == best:
            cands.append(v)
    nd = min(cands, key=vkey)
    if nd != default:
        full = {i: items.get(i, default) for i in range(dom)}
        items = {i: v for i, v in full.items() if v != nd}
        default = nd
    return ('a', default, tuple(sorted(items.items())))


def aget(arr, i):
    for k, v in arr[2]:
        if k == i:
            return v
    return arr[1]


def coerce(sort, raw):
    if isinstance(sort, tuple):
        _, isort, esort = sort
        if isinstance(isort, tuple):
            raise ValueError('array index sort must be bitvec')
        if isinstance(raw, dict):
            d = coerce(esort, raw.get('default', 0))
            items = {int(k) & mask(isort): coerce(esort, v)
                     for k, v in (raw.get('set') or {}).items()}
            return acanon(d, items, isort)
        return acanon(coerce(esort, raw), {}, isort)
    return int(raw) & mask(sort)


class Model:
    def __init__(self):
        self.width = {}      # node id -> bit width | ('a', idx, elem)
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
                if t[2] == 'bitvec':
                    sorts[int(t[0])] = int(t[3])
                elif t[2] == 'array':
                    if isinstance(sorts[int(t[4])], tuple):
                        raise ValueError('nested arrays: outside this '
                                         "solver's fragment")
                    sorts[int(t[0])] = ('a', sorts[int(t[3])],
                                        sorts[int(t[4])])
                else:
                    raise ValueError('unsupported sort: ' + t[2])
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
            vals[nid] = coerce(w, frame_inputs.get(str(nid), 0))
        elif op == 'state':
            if nid in regs:
                vals[nid] = regs[nid]
            else:
                vals[nid] = coerce(w, frame_inputs.get(str(nid), 0))
                regs[nid] = vals[nid]
        elif op == 'read':
            vals[nid] = aget(ref(a[0]), ref(a[1]))
        elif op == 'write':
            arr = ref(a[0])
            items = dict(arr[2])
            items[ref(a[1])] = ref(a[2])
            vals[nid] = acanon(arr[1], items, w[1])
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


def _seed(m, sid, v):
    w = m.width[sid]
    if isinstance(w, tuple):
        if isinstance(v, tuple):
            return v
        if isinstance(w[2], tuple):
            raise ValueError('broadcast init into a nested array')
        return acanon(v & mask(w[2]), {}, w[1])
    return v & mask(w)


def run(m, steps):
    """Run the model under a stimulus; return (bad_fired_depth | None,
    frames run). Constraints must hold at every frame up to the bad."""
    regs = {}
    constrained = True
    for t, frame in enumerate(steps):
        if t == 0:
            pending = {sid: r for sid, r in m.init.items()}
            tmp_vals, tmp_ref = eval_frame(m, dict(), frame, {})
            for sid, r in pending.items():
                regs[sid] = _seed(m, sid, tmp_ref(r))
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
                nxt[sid] = _seed(m, sid, ref(m.next[sid]))
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
    when uninitialized) and to the previous frame's next elsewhere.
    Array-typed nodes build hash-consed array terms instead of words;
    reads resolve through them, and the array axioms (base congruence,
    extensionality) accumulate in self.axioms — global truths assumed
    on every query."""

    def __init__(self, model):
        self.m = model
        self.g = AIG()
        self.words = {}              # (node id, frame) -> literal vector
        self.anodes = [None]         # array term id -> structure
        self.amap = {}               # structure -> array term id
        self.aew = {0: 0}            # array term id -> element width
        self.sel_cache = {}          # (term id, index word) -> element word
        self.base_sels = {}          # base id -> [(index word, element word)]
        self.base_eqs = {}           # base id -> [(e, A, B)]
        self.eq_cache = {}           # (A, B) -> literal e
        self.eq_done = set()         # (e, index word) already instantiated
        self.axioms = []             # AIG literals: valid array lemmas
        self._wix = {}               # term id -> write index words below it
        self._bas = {}               # term id -> base ids below it

    def _aintern(self, struct, ew):
        aid = self.amap.get(struct)
        if aid is None:
            self.anodes.append(struct)
            aid = self.amap[struct] = len(self.anodes) - 1
            self.aew[aid] = ew
            if struct[0] == 'base':
                self.base_sels[aid] = []
                self.base_eqs[aid] = []
        return aid

    def _bases_of(self, aid):
        out = self._bas.get(aid)
        if out is None:
            s = self.anodes[aid]
            if s[0] == 'base':
                out = frozenset([aid])
            elif s[0] == 'constarr':
                out = frozenset()
            elif s[0] == 'write':
                out = self._bases_of(s[1])
            else:                                    # aite
                out = self._bases_of(s[2]) | self._bases_of(s[3])
            self._bas[aid] = out
        return out

    def _write_indices(self, aid):
        out = self._wix.get(aid)
        if out is None:
            s = self.anodes[aid]
            if s[0] == 'write':
                out = self._write_indices(s[1]) | {s[2]}
            elif s[0] == 'aite':
                out = self._write_indices(s[2]) | self._write_indices(s[3])
            else:
                out = frozenset()
            self._wix[aid] = out
        return out

    def _select(self, aid, idx):
        """The element word of an array term at an index word."""
        key = (aid, tuple(idx))
        w = self.sel_cache.get(key)
        if w is not None:
            return w
        g = self.g
        s = self.anodes[aid]
        if s[0] == 'constarr':
            w = list(s[1])
        elif s[0] == 'write':
            hit = weq(g, list(idx), list(s[2]))
            w = wmux(g, hit, list(s[3]), self._select(s[1], idx))
        elif s[0] == 'aite':
            w = wmux(g, s[1], self._select(s[2], idx),
                     self._select(s[3], idx))
        else:                                        # a symbolic base
            w = [g.var() for _ in range(self.aew[aid])]
            self.sel_cache[key] = w      # before axioms: reentry-safe
            for pidx, pw in list(self.base_sels[aid]):
                same = weq(g, list(idx), list(pidx))
                agree = weq(g, w, list(pw))
                self.axioms.append(g.OR(same ^ 1, agree))
            self.base_sels[aid].append((tuple(idx), tuple(w)))
            for rec in list(self.base_eqs[aid]):
                self._inst_eq(rec, tuple(idx))
        self.sel_cache[key] = w
        return w

    def _inst_eq(self, rec, idx):
        """Pointwise instantiation of extensionality: e -> the two
        sides read equal at this index. A valid lemma either way."""
        e, aA, aB = rec
        k = (e, idx)
        if k in self.eq_done:
            return
        self.eq_done.add(k)
        ra = self._select(aA, list(idx))
        rb = self._select(aB, list(idx))
        self.axioms.append(self.g.OR(e ^ 1, weq(self.g, ra, rb)))

    def _aeq(self, aA, aB, iw):
        """One literal for extensional equality of two array terms:
        not-e forces a skolem witness index where the reads differ;
        e forces pointwise equality at both sides' write indices and
        at every base select, past and future."""
        if aA == aB:
            return 1
        key = (min(aA, aB), max(aA, aB))
        e = self.eq_cache.get(key)
        if e is not None:
            return e
        g = self.g
        e = g.var()
        self.eq_cache[key] = e
        rec = (e, aA, aB)
        for b in sorted(self._bases_of(aA) | self._bases_of(aB)):
            self.base_eqs[b].append(rec)
            for pidx, _ in list(self.base_sels[b]):
                self._inst_eq(rec, pidx)
        for idx in sorted(self._write_indices(aA)
                          | self._write_indices(aB)):
            self._inst_eq(rec, idx)
        wit = [g.var() for _ in range(iw)]
        ra = self._select(aA, wit)
        rb = self._select(aB, wit)
        self.axioms.append(g.OR(e, weq(g, ra, rb) ^ 1))
        return e

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
        if isinstance(w, tuple):
            if r < 0:
                raise ValueError('negated array reference')
            return w
        return wnot(self.g, w) if r < 0 else w

    def _compute(self, key):
        m, g = self.m, self.g
        nid, t = key
        op, a = m.node[nid]
        w = m.width[nid]

        def ref(r, at=None):
            return self._lookup(r, t if at is None else at)

        def aid_of(v):
            return v[1]

        arr_sorted = isinstance(w, tuple)
        if op == 'const':
            return wconst(a[0], w)
        if op == 'input':
            if arr_sorted:
                return ('ARR', self._aintern(('base', nid, t), w[2]))
            return [g.var() for _ in range(w)]
        if op == 'state':
            r = m.init.get(nid) if t == 0 else m.next.get(nid)
            if arr_sorted:
                if r is None:
                    return ('ARR', self._aintern(('base', nid, t), w[2]))
                v = ref(r, t if t == 0 else t - 1)
                if isinstance(v, tuple):
                    return v
                # a bitvec init broadcasts into the constant array
                return ('ARR', self._aintern(('constarr', tuple(v)), w[2]))
            if r is None:
                return [g.var() for _ in range(w)]
            return ref(r, t if t == 0 else t - 1)
        if op == 'read':
            return self._select(aid_of(ref(a[0])), ref(a[1]))
        if op == 'write':
            return ('ARR', self._aintern(
                ('write', aid_of(ref(a[0])), tuple(ref(a[1])),
                 tuple(ref(a[2]))), w[2]))
        if op == 'ite':
            if arr_sorted:
                c = ref(a[0])[0]
                x, y = aid_of(ref(a[1])), aid_of(ref(a[2]))
                if c == 1 or x == y:
                    return ('ARR', x)
                if c == 0:
                    return ('ARR', y)
                return ('ARR', self._aintern(('aite', c, x, y), w[2]))
            return wmux(g, ref(a[0])[0], ref(a[1]), ref(a[2]))
        if op in ('eq', 'neq') and isinstance(m.width[abs(a[0])], tuple):
            iw = m.width[abs(a[0])][1]
            e = self._aeq(aid_of(ref(a[0])), aid_of(ref(a[1])), iw)
            return [e if op == 'eq' else e ^ 1]
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
            # the array axioms are global truths: every query assumes
            # every axiom minted so far (bad/constraint cones minted
            # them; instantiation only ever adds valid lemmas)
            for ax in bl.axioms:
                if ax == 0:
                    raise ValueError('internal: contradictory array axiom')
                if ax != 1:
                    asm.append(cnf.lit(ax))
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
                        wd = m.width[nid]
                        if isinstance(wd, tuple):
                            aval = bl.words.get((nid, t))
                            if aval is None:
                                continue         # never observed: default
                            entries = {}
                            for pidx, pw in bl.base_sels.get(aval[1], []):
                                iv = model_bits(cnf, model, list(pidx))
                                vv = model_bits(cnf, model, list(pw))
                                entries.setdefault(iv, vv)
                            if entries:
                                frame[str(nid)] = {
                                    "default": 0,
                                    "set": {str(i): entries[i]
                                            for i in sorted(entries)}}
                        else:
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




# -- the induction machinery over the array blaster ----------------------------

def strip_init(m):
    """The same machine from an arbitrary state: init dropped, so
    frame 0 states blast to fresh variables (a fresh base array for
    an array state)."""
    m2 = Model()
    m2.width, m2.node, m2.order = m.width, m.node, m.order
    m2.inputs, m2.states = m.inputs, m.states
    m2.init = {}
    m2.next = m.next
    m2.bads, m2.constraints = m.bads, m.constraints
    return m2


def _bits_of(m, nid):
    """Bit width of a bit-vector node, None for arrays and unknowns."""
    w = m.width.get(nid)
    return w if isinstance(w, int) else None


def _diff(bl, sid, i, v, t):
    """AIG literal: bit (sid, i) at frame t differs from v."""
    lit = bl.word(sid, t)[i]
    return lit ^ 1 if v == 1 else lit


def _query(bl, cnf, aig_lits, budget):
    """Solve the conjunction of AIG literals under every array axiom
    minted so far (each a valid lemma — Ackermann congruence and
    extensionality instances — so assuming them never manufactures an
    unsat). Constants resolve here: any 0 is UNSAT, 1s drop out."""
    asm = []
    for x in list(aig_lits) + list(bl.axioms):
        if x == 0:
            return UNSAT, None
        if x == 1:
            continue
        asm.append(cnf.lit(x))
    return cnf.sat.solve(asm, budget)


# -- bit-invariant ------------------------------------------------------------

def candidates_from_init(m):
    """Every bit of a next-carrying bit-vector state whose frame-0
    literal constant-folds; the fold value is the candidate constant."""
    bl0 = Blaster(m)
    out = []
    for sid in m.states:
        if sid not in m.next or _bits_of(m, sid) is None:
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
        status, model = _query(bl, cnf, hold + [bl.constraint(0), ordiff],
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
    status, _ = _query(bl, cnf, hold + [bl.constraint(0), bl.bad(0)],
                       budget)
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
    status, _ = _query(bl, cnf, lits, budget)
    return status


# -- discharge ----------------------------------------------------------------

def _literal_ok(m, sid, i, terms):
    """A certificate literal names a bit of a next-carrying bit-vector
    state — or, when the judge says so, of any bit-vector term over
    the states (a judge that builds such terms itself, from atoms it
    defines, keeps them input-free by construction)."""
    if not isinstance(sid, int) or not isinstance(i, int):
        return False
    w = _bits_of(m, sid)
    if w is None or not 0 <= i < w:
        return False
    if terms:
        return sid in m.node
    return sid in m.next


def _discharge_bits(m, bits, budget, terms=False):
    seen = set()
    checked = []
    for entry in bits:
        if not isinstance(entry, list) or len(entry) != 3:
            return None
        sid, i, v = entry
        if (v not in (0, 1) or not _literal_ok(m, sid, i, terms)
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
    status, _ = _query(bl0, cnf0, [viol0], budget)
    if status != UNSAT:
        return None
    # consecution and safety, from an arbitrary invariant state
    bl = Blaster(strip_init(m))
    cnf = CNF(bl.g)
    hold = [_diff(bl, sid, i, v, 0) ^ 1 for (sid, i, v) in checked]
    viol1 = 0
    for (sid, i, v) in checked:
        viol1 = bl.g.OR(viol1, _diff(bl, sid, i, v, 1))
    status, _ = _query(bl, cnf, hold + [bl.constraint(0), viol1], budget)
    if status != UNSAT:
        return None
    status, _ = _query(bl, cnf, hold + [bl.constraint(0), bl.bad(0)],
                       budget)
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


def discharge_clauses(m, clauses, budget, clause_cap=5000, terms=False):
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
            if v not in (0, 1) or not _literal_ok(m, sid, i, terms):
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

    def query(bl, cnf, aig_lits):
        st, _ = _query(bl, cnf, aig_lits, budget)
        return st

    # init: no constrained initial state escapes the invariant
    bl0 = Blaster(m)
    cnf0 = CNF(bl0.g)
    if query(bl0, cnf0, [bl0.constraint(0), neginv(bl0, 0)]) != UNSAT:
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
    if query(bl, cnf, hold + [bl.constraint(0), neginv(bl, 1)]) != UNSAT:
        return None
    if query(bl, cnf, hold + [bl.constraint(0), bl.bad(0)]) != UNSAT:
        return None
    return {"init": "unsat", "consecution": "unsat", "safety": "unsat",
            "clauses": len(checked)}


def discharge(m, cert, budget, terms=False):
    """Re-check a certificate. Returns the obligations dict on a
    validated discharge, None on any failure."""
    if not isinstance(cert, dict):
        return None
    kind = cert.get("kind")
    if kind == "bit-invariant" and isinstance(cert.get("bits"), list):
        return _discharge_bits(m, cert["bits"], budget, terms)
    if kind == "k-induction":
        return _discharge_kind(m, cert.get("k"), budget)
    if kind == "clause-invariant" and isinstance(cert.get("clauses"), list):
        return discharge_clauses(m, cert["clauses"], budget, terms=terms)
    return None


# -- BMC with the k-induction step tried as the depth deepens -----------------

def bmc_with_induction(m, mode, bound, budget, clause_cap, step_pool,
                       k_cap=16, inf_cap=300, node_cap=4_000_000):
    """The bounded checker's own loop (arrays included), with the
    k-induction step tried after each proven depth — each proven depth
    extends the base for free. Adds ('kind-proved', K) to the result
    kinds of bmc()."""
    bl = Blaster(m)
    cnf = CNF(bl.g)
    state = {'bl': None, 'cnf': None, 'pool': step_pool}

    def try_step(kk):
        if kk > k_cap or state['pool'] <= 0:
            return False
        if state['bl'] is None:
            state['bl'] = Blaster(strip_init(m))
            state['cnf'] = CNF(state['bl'].g)
        if len(state['bl'].g.nodes) > node_cap:
            state['pool'] = 0
            return False
        before = state['cnf'].sat.conflicts
        st = kind_step(state['bl'], state['cnf'], kk, state['pool'])
        state['pool'] -= state['cnf'].sat.conflicts - before + 1
        return st == UNSAT

    proven = -1
    k = 0
    vacuous_from = None
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
                if try_step(k + 1):
                    return ('kind-proved', k + 1)
                k += 1
                continue
            for ax in bl.axioms:
                if ax == 0:
                    raise ValueError('internal: contradictory array axiom')
                if ax != 1:
                    asm.append(cnf.lit(ax))
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
                        wd = m.width[nid]
                        if isinstance(wd, tuple):
                            aval = bl.words.get((nid, t))
                            if aval is None:
                                continue
                            entries = {}
                            for pidx, pw in bl.base_sels.get(aval[1], []):
                                iv = model_bits(cnf, model, list(pidx))
                                vv = model_bits(cnf, model, list(pw))
                                entries.setdefault(iv, vv)
                            if entries:
                                frame[str(nid)] = {
                                    "default": 0,
                                    "set": {str(i): entries[i]
                                            for i in sorted(entries)}}
                        else:
                            val = model_bits(cnf, model, bl.word(nid, t))
                            if val:
                                frame[str(nid)] = val
                    steps.append(frame)
                fired, _ = run(m, steps)
                if fired != k:
                    return ('partial', proven,
                            'internal: model did not replay at depth %d'
                            % k)
                return ('witness', steps, k)
            proven = k
            if cnf.sat.conflicts >= budget:
                return ('partial', proven, 'conflict budget spent')
            if try_step(k + 1):
                return ('kind-proved', k + 1)
        else:
            if proven >= vacuous_from - 1:
                return ('all', 'inf')
            return ('partial', proven, 'constraints impossible yet unproven')
        k += 1
    return ('all', int(bound))


# =============================================================================
# Atoms and obligations.
# =============================================================================

def _map_bits(mc, entries):
    out = []
    for e in entries:
        if not isinstance(e, list) or len(e) != 2 or e[1] not in (0, 1):
            return None
        st = mc.atom(e[0])
        if st is None:
            return None
        out.append([st[0], st[1], e[1]])
    return out


def judge(src, payload, budget=300000):
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    try:
        mc = build(src)
        mapped = None
        if kind == "bit-invariant":
            bits = payload.get("bits")
            if not isinstance(bits, list):
                return None
            mapped = _map_bits(mc, bits)
            if mapped is None:
                return None
        elif kind == "clause-invariant":
            clauses = payload.get("clauses")
            if not isinstance(clauses, list):
                return None
            mapped = []
            for cl in clauses:
                if not isinstance(cl, list):
                    return None
                m1 = _map_bits(mc, cl)
                if m1 is None:
                    return None
                mapped.append(m1)
        elif kind != "k-induction":
            return None
    except (Frag, Refuse, RecursionError):
        return None
    with open("machine.btor2", "w", encoding="utf-8") as fh:
        fh.write("\n".join(mc.b.lines) + "\n")
    m = parse("machine.btor2")
    if kind == "k-induction":
        return _discharge_kind(m, payload.get("k"), budget)
    if kind == "bit-invariant":
        return _discharge_bits(m, mapped, budget)
    return discharge_clauses(m, mapped, budget)


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
