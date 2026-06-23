# python-smtlib translation schema (`predicted`)

This is the self-contained, reviewable specification the translator `T`
implements mechanically (PAIRING.md §2). Given a Python-subset source program,
the emitted SMT-LIB script is determined **byte-for-byte** by the rules below —
no adaptive choices, no hashing, no timestamps. Anyone with the source and this
schema can reproduce the output exactly (the `predicted` predictability test).

Python is compiled **directly to the SMT-LIB hub**, *not* via BTOR2: Python's
unbounded `int` maps faithfully to SMT `Int` (`QF_LIA`), a fit only the
direct-to-LIA route affords; bit-blasting it to fixed-width words would be
unfaithful (pairs/python-smtlib brief; ARCHITECTURE.md §9).

## Scope (the vertical slice — widened by the ratchet)

In scope: a **single top-level `def`** whose parameters are all plain positional
integer inputs, with a body of:

- integer **assignment** `name = <linear>` to one `Name` target;
- **linear integer arithmetic** in `<linear>`: integer literals, parameter /
  local `Name` loads, unary `+` / `-`, binary `+` / `-`, and `*` **with at least
  one literal-constant operand** (kept linear);
- **`if <cond>: <arm>` with optional `else: <arm>`** (slice 2): `<cond>` is one
  integer comparison; each arm is itself a body of in-scope statements
  (assignments, nested `if`, a bounded `for` / `while` — **no** `assert` inside an
  arm). A variable assigned on *both* arms (or already in scope before the `if`)
  is readable after the join; one first assigned on only one arm is **not** (it
  may be undefined on the other path — reading it later aborts `undefined-name`);
- **`for <i> in range(<const>): <body>`** (slice 3) — a **bounded loop** with a
  compile-time-constant trip count; see "Bounded loop" below. `<body>` is a body
  of in-scope statements (assignments, nested `if`, and — slice 5 — a **nested
  `for` / `while`** within the nesting caps; **no** `assert`). The loop variable
  `<i>` is readable **inside** `<body>` (it is the iteration index) but **not**
  after the loop; a body-only-assigned name is likewise not readable after the loop
  (it may be undefined when the loop runs zero times — reading it later aborts
  `undefined-name`);
- **`while <cond>: <body>`** (slice 4) — a **BMC-bounded loop** unrolled to a
  fixed bound `K`; see "BMC-bounded loop" below. `<cond>` is one integer
  comparison; `<body>` is a body of in-scope statements (assignments, nested `if`,
  and — slice 5 — a **nested `for` / `while`** within the nesting caps; **no**
  `assert`, no `break` / `continue`). A body-assigned name is **not** readable
  after the loop (it may run zero times, or not terminate within `K`), so an
  accumulator must be initialised *before* it (the `if` one-arm / `for` rule);
- **nested loops** (slice 5) — a `for` / `while` may appear inside another loop's
  `<body>` (and inside an `if` arm inside a loop); see "Nested loops" below. The
  inner loop is unrolled at *each* outer iteration over the advancing SSA, the
  unroll sizes multiplying, bounded by the fixed nesting caps `MAX_LOOP_DEPTH` /
  `MAX_UNROLL_PRODUCT`;
- **fixed-length integer lists** (slice 6) — a list of statically-known length `L`
  modeled as a **tuple of `L` `Int` SSA variables** (*not* an SMT `Array`); see
  "Integer lists" below. In scope: a list literal `xs = [e0, …, e{L-1}]` (each
  element an in-scope int expression; `L ≤ MAX_LIST_LEN`), a constant / dynamic
  index **read** `xs[i]` and **write** `xs[i] = v`, and `len(xs)`;
- a single trailing `assert <l> <cmp> <r>` whose condition is one integer
  comparison with `<cmp>` in `== != < <= > >=`.

Everything else hard-aborts with a typed `unsupported: python:<construct>`
(BENCHMARKS.md §3), never a silent drop. The histogram key is the offending AST
node class (or a named guard):

| construct | abort key |
|---|---|
| a loop nested past `MAX_LOOP_DEPTH` or `MAX_UNROLL_PRODUCT` (see "Nested loops") | `python:nesting-too-deep` |
| `for` over a non-constant `range(n)` bound | `python:nonconst-range` |
| `for` with a start/step `range(a, b[, c])` | `python:range-shape` |
| `for` over a negative `range(n)` bound | `python:negative-range` |
| `for` over a non-`range` iterable (incl. `for x in xs`) | `python:nonrange-loop` |
| `for … else` / `while … else` | `python:for-else` / `python:while-else` |
| `break` / `continue` (in any loop) | `python:Break` / `python:Continue` |
| floored division `//` | `python:FloorDiv` |
| modulo `%` | `python:Mod` |
| true (float) division `/` | `python:Div` |
| exponent `**` | `python:Pow` |
| variable-by-variable product `x*x` | `python:nonlinear-mul` |
| boolean operator `and` / `or` | `python:BoolOp` |
| function call (other than `len(xs)`) | `python:Call` |
| a list literal longer than `MAX_LIST_LEN` | `python:list-too-long` |
| a nested list / non-int element `[[1],[2]]` | `python:nested-list` |
| a length-changing op `xs.append(…)` / `xs.pop()` / `xs.insert(…)` | `python:Expr` |
| a list used where an int is expected (`y = xs`, `xs + 1`) | `python:list-as-int` |
| an out-of-range *constant* index `xs[5]` (incl. negative `xs[-1]`) | `python:list-index-out-of-range` |
| subscripting an int scalar `a[i]` | `python:index-non-list` |
| list slicing `xs[a:b]` (read or write) | `python:list-slice` |
| a pre-loop list re-bound to a different length in the loop | `python:list-len-changed-in-loop` |
| a list joined at an `if` with a different length per arm | `python:list-join-mismatch` |
| `len(...)` of a non-list / non-name argument | `python:len-non-list` / `python:len-arg` |
| `dict` / `set` literal | `python:Dict` / `python:Set` |
| `return <expr>` | `python:Return` |
| `import` | `python:Import` |
| chained / tuple assignment | `python:multiple-targets` |
| non-`Name`/non-list-index assignment target | `python:Attribute` / … |
| chained comparison `a < b < c` | `python:chained-compare` |
| read of an unassigned name (incl. a one-arm-only local at the join) | `python:undefined-name` |
| `assert` inside an `if` arm | `python:branch-assert` |
| an `assert` that is not the last statement | `python:non-trailing-assert` |
| no trailing `assert` | `python:no-assert` |
| a statement after the `assert` | `python:post-assert-statement` |
| `*args` / `**kwargs` / defaults / kw-only | `python:param-shape` |
| more than one `def`, or top-level code | `python:module-shape` / the node class |

## Logic

`QF_LIA` — quantifier-free linear integer arithmetic. Program variables are
`Int` (arbitrary precision, the faithful match for Python's unbounded `int`);
the property is a `Bool` predicate.

## SSA + per-construct lowering (emitted in source order)

1. **Inputs.** Each parameter `p` (declaration order) is one input variable
   `(declare-fun p__in () Int)`. The "current SSA version" of `p` starts at
   `p__in`.
2. **Assignment.** A counter `n` (from 0) numbers assignment results. For the
   `i`-th assignment `name = e` (source order): declare `(declare-fun name__n ()
   Int)`, assert `(= name__n <lower(e)>)` where `e` is lowered using the
   *current* SSA version of every read name (so `x = x + 1` reads the previous
   version), then make `name__n` the current version of `name` and increment `n`.
3. **Expression lowering** `lower(e)`:
   - integer literal `c` → `c` if `c ≥ 0`, else `(- |c|)` (SMT-LIB has no
     negative-literal token);
   - name load → its current SSA version;
   - unary `-x` → `(- <x>)`; unary `+x` → `<x>`;
   - `a + b` → `(+ <a> <b>)`; `a - b` → `(- <a> <b>)`; `a * b` → `(* <a> <b>)`.
4. **Branch merge** (`if cond: then [else: else]` — the standard SSA φ as an
   `ite`). The same counter `n` numbers branch-join results too.
   1. Lower the guard `cond` once to a predicate `C` over the **incoming** SSA
      versions (`(> x__in 0)` etc., the same comparison lowering as the property).
   2. Lower the **then** arm from a *copy* of the incoming SSA map (its
      assignments — including a nested `if` — advance the counter but do not
      touch the incoming map or the else arm), giving a post-then map; lower the
      **else** arm likewise from its own copy of the incoming map. A bare `if`
      with no `else` lowers an empty else arm, so every variable's else-version
      is just its incoming version.
   3. **Join.** For each live variable `v` (in declaration / first-assignment
      order — the deterministic key) let `t` = its then-version (or its incoming
      version if the then arm did not reassign it) and `e` = its else-version
      (likewise). If `t = e` (touched identically or in neither arm), `v` keeps
      that shared version with **no emission**. Otherwise declare a fresh
      `(declare-fun v__n () Int)`, assert `(= v__n (ite C t e))`, and make
      `v__n` the current version of `v`. A variable assigned on only one arm and
      not in scope before the `if` is dropped by the join (the loader already
      rejects reading it later as `undefined-name`), so it never produces an
      `ite`.

   Worked example (`if x > 0: y = 1 else: y = -1`, incoming `x = x__in`):

   ```smt2
   (declare-fun y__0 () Int) (assert (= y__0 1))           ; then arm
   (declare-fun y__1 () Int) (assert (= y__1 (- 1)))        ; else arm
   (declare-fun y__2 () Int) (assert (= y__2 (ite (> x__in 0) y__0 y__1)))  ; join
   ```
5. **Bounded loop** (`for i in range(n): body` — **full unrolling**, BMC with a
   compile-time-constant bound). The **bound convention is fixed and explicit**
   (the predictability test, PAIRING.md §2): the trip count is the **constant
   integer literal `n`** in `range(n)` — *not* a caller-supplied bound. There is
   exactly one in-scope range shape, `range(n)` with a single non-negative
   integer literal; a non-constant bound (`nonconst-range`), a start/step
   (`range-shape`), a negative literal (`negative-range`), a non-`range` iterable
   (`nonrange-loop`), a `for…else`, or a *nested* loop (`For`) all hard-abort, so
   the unrolled iteration count is fully determined by the source text.

   The loop is lowered by re-lowering `body` **`n` times in source order**, over
   the **advancing** SSA map (each iteration sees the previous iteration's SSA
   versions — a true unrolling, not `n` independent copies), with the loop
   variable `i` bound to the **concrete iteration index** `0, 1, …, n-1` (a plain
   non-negative numeral) on the `k`-th pass — so a read of `i` in `body` lowers to
   the literal `k`, never an `Int` SSA variable. Because the trip count is a
   constant, every iteration is **unconditional**: there is no per-iteration path
   condition and therefore **no `ite`** (unlike a branch). The shared counter `n`
   keeps numbering across all iterations, so the bytes are reproducible.

   After the loop, the loop variable `i` and any name first assigned in `body`
   are **dropped** from the current SSA map: they are not readable after the loop
   (`range(n)` may have `n == 0`, so a body-only name could be undefined), exactly
   the loader's rule — an accumulator read after the loop must be initialised
   *before* it (its current SSA version is then the **last** iteration's). For
   `n == 0` the body lowers zero times, so the loop emits nothing and every
   variable keeps its pre-loop version.

   Worked example (`s = x; for i in range(3): s = s + i`, incoming `x = x__in`):

   ```smt2
   (declare-fun s__0 () Int) (assert (= s__0 x__in))        ; s = x (pre-loop)
   (declare-fun s__1 () Int) (assert (= s__1 (+ s__0 0)))   ; iteration i = 0
   (declare-fun s__2 () Int) (assert (= s__2 (+ s__1 1)))   ; iteration i = 1
   (declare-fun s__3 () Int) (assert (= s__3 (+ s__2 2)))   ; iteration i = 2
   ```
   After the loop the current version of `s` is `s__3` (and `i` is dropped).
6. **BMC-bounded loop** (`while cond: body` — **bounded unrolling**, BMC). Unlike
   `for` (whose trip count is a source constant), a `while` has no statically-known
   trip count, so it is unrolled to a **fixed bound `K`**. The **bound convention is
   fixed and explicit** (the predictability test, PAIRING.md §2): `K` is the module
   constant **`WHILE_BOUND = 8`** in `gurdy/languages/python/subset.py` — *not* a
   heuristic, not adaptive, not a per-program choice. It is kept small (≤ 8) to
   bound SMT size (BENCHMARKS.md §6, the unrolling-bound cap). The same constant is
   the executor's replay cap, so `I_s` and `T` unroll the same depth.

   The body is unrolled `K` times over the **advancing** SSA map. For iteration `j`
   (`0 ≤ j < K`), with `incoming` the SSA map at its start:
   1. Lower `cond` over `incoming` to a predicate `cond_j` (the same comparison
      lowering as the property / an `if` guard).
   2. Declare a fresh **`Bool`** *active* flag
      `(declare-fun while__active__<n> () Bool)` constrained
      `active_j = cond_0 ∧ … ∧ cond_j` — i.e. `active_0 = cond_0`, and for `j > 0`,
      `active_j = (and active_{j-1} cond_j)`. `active_j` is true exactly when the
      loop condition held at **every** iteration up to and including `j`, so
      iteration `j` actually executes. (The active flags draw on the shared SSA
      counter, so their `__<n>` numbering is globally unique and reproducible; they
      are not program variables and never participate in a join.)
   3. Lower `body` **unconditionally** from a *copy* of `incoming` (advancing the
      shared counter), giving the would-be post-body SSA versions.
   4. **Join.** For each live variable `v` (declaration / first-assignment order),
      let `b` = its body-version (or its incoming version if the body did not
      reassign it) and `c` = its incoming version. If `b = c` (untouched), `v` keeps
      that version with **no emission**. Otherwise declare a fresh
      `(declare-fun v__<n> () Int)` constrained `(= v__<n> (ite active_j b c))` and
      make it `v`'s current version — when the loop is no longer active the value is
      **carried through unchanged** (a no-op iteration). This is exactly the `if`
      merge with `active_j` as the guard and the carried value `c` as the else-arm.

   After `K` iterations, **assert termination within the bound**: lower `cond` over
   the post-loop SSA map (`cond_final`) and emit `(assert (not cond_final))`. A run
   that terminated early carries a false `cond` through to `cond_final` (so the
   assert holds); a run that would need a `(K+1)`-th iteration still has
   `cond_final` true, so this constraint **excludes** it. The decided property is
   therefore *"is there an input that **terminates within `K`** and violates the
   assert?"* — a model that needs more than `K` iterations is unsatisfiable
   (carried back as UNREACHABLE), **never** a silent wrong answer. Finally, any name
   first assigned in `body` is **dropped** from the current SSA map (not readable
   after the loop — it may run zero times or hit the bound), exactly the `for` rule.

   Worked example (`while x > 0: x = x - 1`, incoming `x = x__in`, the first two of
   `K = 8` iterations):

   ```smt2
   (declare-fun while__active__0 () Bool)
   (assert (= while__active__0 (> x__in 0)))                 ; cond_0
   (declare-fun x__1 () Int) (assert (= x__1 (- x__in 1)))   ; body iter 0 (x - 1)
   (declare-fun x__2 () Int)
   (assert (= x__2 (ite while__active__0 x__1 x__in)))       ; join: run iff active_0
   (declare-fun while__active__3 () Bool)
   (assert (= while__active__3 (and while__active__0 (> x__2 0))))  ; cond_0 ∧ cond_1
   (declare-fun x__4 () Int) (assert (= x__4 (- x__2 1)))    ; body iter 1
   (declare-fun x__5 () Int)
   (assert (= x__5 (ite while__active__3 x__4 x__2)))        ; join
   ;  … iterations 2..7 …
   (assert (not (> x__23 0)))                                ; terminated within K
   ```
   After the loop the current version of `x` is `x__23` (the value at loop exit
   within `K`).
7. **Nested loops** (`for` / `while` inside another loop's `body`, or inside an
   `if` arm inside a loop — slice 5). The lowering is the **same per-construct
   schema, applied recursively**: when `emit_for` / `emit_while` lowers a loop body
   that itself contains a `for` / `while`, the inner loop is lowered by the very
   same `emit_for` / `emit_while` over the advancing SSA, threading the **shared SSA
   counter** through both levels so the bytes stay reproducible. There is **no new
   rule** — nesting is just composition of §5 (full `for` unrolling) and §6 (`while`
   BMC unrolling):

   - inside a `for` (constant trip count `n`), the inner loop is re-lowered at each
     of the `n` outer iterations, over the SSA as it stands at that iteration (the
     outer loop variable is bound to its concrete index, so the inner body sees it
     as a literal). The inner loop drops its own loop variable / body-only names at
     its join, exactly as at the top level;
   - inside a `while` (bound `K`), the inner loop is lowered **unconditionally**
     inside each of the `K` outer body copies (the outer `active_j` flag gates the
     *whole* body copy at the outer join, so the inner loop's own `ite`s compose
     under it — when the outer iteration is inactive the outer join carries every
     variable through unchanged, nullifying the inner loop's effect);
   - a loop inside an `if` arm inside a loop is the same: the `if` merge (§4) joins
     the arm (which contains the inner loop) against the other arm, and the whole
     `if` sits inside the outer loop's body copy — one level of loop nesting, not
     two (an `if` is not a loop).

   **The nesting caps** (the predictability test, PAIRING.md §2; the unrolling-bound
   cap, BENCHMARKS.md §6). Because the inner loop is re-unrolled at every outer
   iteration, the unrolled body copies **multiply**, so two fixed module constants in
   `gurdy/languages/python/subset.py` bound the size:

   - `MAX_LOOP_DEPTH = 2` — the maximum loop **nesting depth** (a top-level loop is
     depth 1; a loop in its body is depth 2). A loop reached at depth 3 — a loop
     inside a loop inside a loop — hard-aborts `python:nesting-too-deep`.
   - `MAX_UNROLL_PRODUCT = WHILE_BOUND * WHILE_BOUND = 64` — the maximum **product of
     unroll bounds** along a nesting path (a `for i in range(n)` contributes `n`; a
     `while` contributes `WHILE_BOUND`). This product is the number of times the
     innermost body is unrolled; if **entering** a loop would push the running
     product over `64`, that loop hard-aborts `python:nesting-too-deep`. So
     `while`-in-`while` (8 × 8 = 64) is allowed; `for range(9)`-with-a-`while`-inside
     (9 × 8 = 72) is not.

   Both caps are **static** (a `for`'s trip count is a source constant; a `while`'s
   is `WHILE_BOUND`), so the abort fires at **load time** (BENCHMARKS.md §3) — the
   translator never emits an enormous script. The caps are shared by the loader (the
   boundary check + the typed abort) and the translator (which re-derives the same
   product as it recurses), so the bound is predictable from the source and this
   spec.

   Worked example (`for i in range(2): for j in range(3): s = s + 1`, incoming
   `s = s__0`): the inner `for` (trip count 3) is unrolled at each of the 2 outer
   iterations, for 2 × 3 = 6 unconditional body copies over the advancing SSA —
   `s__1 = s__0 + 1`, `s__2 = s__1 + 1`, …, `s__6 = s__5 + 1` — with no `ite` (both
   trip counts are constant, every iteration unconditional). After the loops the
   current version of `s` is `s__6`.
8. **Integer lists — the tuple-of-Ints model** (`xs = […]`, `xs[i]`, `xs[i] = v`,
   `len(xs)` — slice 6). A Python list of **statically-known length `L`** is modeled
   as **`L` separate `Int` SSA variables** — a *tuple of Ints* — **not** an SMT
   `Array`. This keeps the encoding inside the existing `QF_LIA` fragment (`Int` +
   linear arithmetic + `ite`; no `Array` sort, no `select` / `store`), the faithful
   fit for Python's lists of unbounded ints. `L` is a compile-time constant in every
   case (the literal's length), bounded by the fixed module constant
   **`MAX_LIST_LEN = 16`** in `gurdy/languages/python/subset.py` (a longer literal
   hard-aborts `list-too-long`) — because a dynamic index fans out into an `L`-deep
   `ite` chain, the cap bounds the per-list SMT size (BENCHMARKS.md §6).

   A list-typed name `xs` carries, in the SSA state, its **tuple of element terms**
   `[t0, t1, …, t{L-1}]` (each `ti` an `Int` SSA version of position `i`), kept
   separate from the scalar SSA map. The four operations lower as:

   1. **List literal** `xs = [e0, …, e{L-1}]`. Lower each element `ei` over the
      current SSA map, then declare `L` fresh `(declare-fun xs__<n> () Int)`, one per
      element, asserting `(= xs__<n> <lower(ei)>)`. The `L` fresh symbols become the
      tuple for `xs` (a prior binding of `xs`, scalar or list, is replaced). The
      shared counter numbers all `L`, so the bytes are reproducible.

      Worked example (`xs = [x, x + 1, x + 2]`, incoming `x = x__in`):

      ```smt2
      (declare-fun xs__0 () Int) (assert (= xs__0 x__in))
      (declare-fun xs__1 () Int) (assert (= xs__1 (+ x__in 1)))
      (declare-fun xs__2 () Int) (assert (= xs__2 (+ x__in 2)))
      ```
   2. **Index read** `xs[i]` (an integer term).
      - **Constant `i = k`** (the loader has bounds-checked `0 ≤ k < L`): the term is
        the tuple element `t_k` **directly** — no new symbol, no constraint. (`xs[1]`
        above lowers to `xs__1`.)
      - **Dynamic `i`** (an in-scope scalar int): assert the range
        `(assert (and (<= 0 <i>) (< <i> L)))` as a side constraint, then read via the
        right-folded `ite` chain `(ite (= <i> 0) t0 (ite (= <i> 1) t1 … t{L-1}))` over
        the `L` positions. The range constraint makes position `L-1` the catch-all
        `else`, so an out-of-range index is **excluded** by the solver — a defined
        under-approximation (like the `while` termination assertion), never a silent
        wrong read.
   3. **Index write** `xs[i] = v` (an SSA update of the tuple).
      - **Constant `i = k`**: only position `k` becomes a fresh `xs__<n>` =
        `<lower(v)>`; the other positions keep their terms. The tuple advances at one
        slot.
      - **Dynamic `i`**: assert the range `0 ≤ i < L`, then **every** position `j`
        becomes a fresh `xs__<n>` constrained `(= xs__<n> (ite (= <i> j) <v> t_j))` —
        the matched position takes `v`, every other carries its old term unchanged
        (the standard select-update of a value array, done element-wise so it stays in
        `QF_LIA`).

      Worked example (`xs = [0,0,0]; xs[i] = v`, incoming `i = i__in`, `v = v__in`,
      `xs = [xs__0, xs__1, xs__2]`):

      ```smt2
      (assert (and (<= 0 i__in) (< i__in 3)))
      (declare-fun xs__3 () Int) (assert (= xs__3 (ite (= i__in 0) v__in xs__0)))
      (declare-fun xs__4 () Int) (assert (= xs__4 (ite (= i__in 1) v__in xs__1)))
      (declare-fun xs__5 () Int) (assert (= xs__5 (ite (= i__in 2) v__in xs__2)))
      ```
   4. **`len(xs)`** lowers to the **constant numeral `L`** (the static tuple width).

   **Lists across control flow.** A list is joined at an `if` / `while` **element-
   wise**, exactly as a scalar is (§4 / §6) but per position: each slot `j` becomes
   `(ite <guard> then_j else_j)` when the two sides differ, or keeps the shared term
   when they agree. Both sides have the same length — the loader's
   `list-join-mismatch` check (an `if` whose two arms leave a list different lengths)
   and `list-len-changed-in-loop` check (a pre-loop list re-bound to a different
   length in the body) rule out an ambiguous tuple width, so the join is always
   well-defined. A list updated in a loop (index-written in the body) advances its
   tuple over the unrolling just as a scalar accumulator advances its term — "a list
   updated in a loop" is the same mechanism, applied per position.

   **Out of scope** (hard-abort, the honest gap): `append` / `pop` / `insert` (a
   length change — the tuple width must be static), a non-constant-length or nested
   list, slicing, a list of non-int, a list used as an int, `for x in xs`
   (only `for i in range(…)` is in scope), `dict` / `set` / `str`, and list
   comprehensions. **Widening to a variable-length list** would need SMT array theory
   (`QF_ALIA`) — a deliberate later trade that leaves the small-fixed-length tuple
   model, which is the named next step, not this slice's job.
9. **Property.** The trailing `assert cond` lowers `cond` (one comparison
   `l <op> r`) to a predicate `C`: `==`→`(= l r)`, `!=`→`(distinct l r)`, and
   `< <= > >=` straight across, reading each name at its **joined / unrolled** SSA
   version. The script asserts the **negation** `(assert (not C))`. A dynamic list
   index in `cond` (e.g. `assert xs[i] == v`) emits its `0 ≤ i < L` range constraint
   as a **separate** top-level `(assert …)` *before* the negated property (the range
   constraint is unconditional; only the property's truth is negated), so an
   out-of-range index excludes the model rather than spuriously violating the assert.
10. `(check-sat)`.

The script is `sat` **iff some integer input violates the assert** — i.e.
`not cond` is reachable. That is the property the pair decides:

- `sat` → REACHABLE: the assert is *violable*; the model binds each `p__in` to a
  concrete violating input.
- `unsat` → UNREACHABLE: the assert *holds for every integer input* (the solver
  proves it over all inputs; carried back as UNREACHABLE).

With a `while` loop the quantifier narrows to **inputs that terminate within `K`**
(the termination assertion, §6): the decided question is *"is there an input that
terminates within `K` and violates the assert?"*. A program that would only violate
the assert on a run needing more than `K` iterations is UNREACHABLE here — a
**sound under-approximation of reachability** (BMC), reported honestly as "no
terminating-within-`K` counterexample", never a silent wrong verdict. Widening to
**unbounded** loops (proving termination, or invariant inference / CHC) is the named
next step.

With a **dynamic list index** (§8) the quantifier narrows the same way to **inputs
whose every dynamic index is in range** (the `0 ≤ i < L` constraints): a program
that would only violate the assert via an out-of-range access is UNREACHABLE here —
the same sound under-approximation, reported honestly, never a silent wrong verdict.
(A constant index is bounds-checked statically at load time, so it cannot reach the
solver out of range.)

## The div/mod wrinkle (why `//` / `%` are out of this slice)

SMT-LIB `div` / `mod` are **Euclidean** (`0 ≤ (mod m n) < |n|`), while Python
`//` / `%` are **floored**. They agree for non-negative operands but **differ for
negative operands** — e.g. `(-7) // 2 == -4` and `(-7) % 2 == 1` in Python, but
`(div (- 7) 2) == -3` and `(mod (- 7) 2) == 1` under SMT-LIB Ints. Lowering
Python `//` / `%` directly to SMT `div` / `mod` would therefore be **unsound**
for negative inputs. This slice keeps `//` / `%` **out of scope** (hard-abort
`python:FloorDiv` / `python:Mod`); choosing arithmetic without division
sidesteps the issue cleanly. **Widening to `//` / `%` requires the explicit
floor↔Euclidean correction** — e.g. lower `a // b` (for symbolic-sign `b`) via a
fresh quotient/remainder pair `q, r` constrained by `a = b*q + r` *with the
floored sign rule* (`r` carries the sign of `b`, `0 ≤ |r| < |b|`), not the
Euclidean `mod`. Until that correction is specified and tested, the constructs
stay aborted (the honest gap, not a silent mis-translation).

## Carry-back `L` and the soundness story

A `sat` model binds each `p__in`. `L` (`decode_inputs` + `lift`) reads the
violating input assignment and **replays it through the shared Python
interpreter `I_s`** — pinned real CPython restricted to the subset (SOLVERS.md
§4: the solver only proposes; the deterministic interpreter disposes). So the
behavior `L` returns is CPython's, not the solver's. With `if`/`else`, the
replay evaluates each guard through CPython and walks **only the taken arm**, so
the violating input necessarily drives the run down the branch that makes the
`ite`-joined value fire the assert — the branch the solver selected via `C`. With
a **bounded loop**, the replay runs the body the **same `n` times** the unrolling
lowered (the loader-validated constant trip count), so the violating input drives
the loop's accumulated value to the firing assert — the same finite computation
the unrolled SSA encodes. With a **`while` loop**, the replay runs the real `while`
through CPython (capped at the same bound `K`, which never fires for a witnessed
input, since the solver only returns terminating-within-`K` models), so the
violating input drives the loop the same number of iterations the unrolling encodes
to the firing assert. With **nested loops**, CPython runs the real nested loops
natively (each inner loop capped at `K` if it is a `while`), so the violating input
drives both levels the same number of iterations the recursive unrolling encodes to
the firing assert — the same finite computation the multiplied SSA encodes. With
**integer lists** (§8), CPython runs the real list (a list literal builds it,
`xs[i] = v` mutates it in place, `len` reads its length); the solver's model binds
the inputs — including a dynamic index `i` the solver chose to land the read / write
on the firing position — so the replay drives the list's element values to the
firing assert, the same tuple-of-Ints computation the SMT encodes. The decoded
index is always in range (the `0 ≤ i < L` constraints restrict the model), so the
replay never hits the out-of-range *defined-error* floor on a witnessed input.
Soundness (PAIRING.md §6) is byte-prediction (this schema) **plus** model
validation:

- `smt_model_ok` — the shared `QF_LIA` evaluator re-checks the solver's model
  against the emitted script (the authoritative SMT-level witness check);
- `witness_ok` — the CPython replay's final (assert) state is `__violated__`,
  i.e. the assert genuinely fires on the decoded input.

The two must agree for a REACHABLE verdict; a divergence is a translator-or-solver
fault, localized by the commuting-square oracle.

## Projection `π`

The named program variables at the observation point (parameters + locals
readable after their block, in declaration / first-assignment order — the loop
variable and loop-body-only locals are *not* in `π`, matching that they are not
readable after the loop) plus the statement kind `__stmt__`, the condition truth
`__cond__`, and the property verdict `__violated__` — `projection_for(program)`. A
**list** variable (slice 6) is one named field observed *as a whole* — its element
values (a Python list in the trace; both `I_s(p)` and the replay run CPython, so the
lists compare equal). The commuting-square check `cross_check` runs `I_s(p)`
on the witness's decoded input and aligns it, under `π`, against `L(I_t(T(p)))`
(the same replay), so a faithful pair makes the two traces identical at every
step and observable, and the witnessed state is genuinely `__violated__`.

## Fidelity

`predicted` on the encoding (this schema, byte-reproducible) + `checked` overall
(the CPython differential every run). The ceiling is `checked`, **not** the
bit-blast `proved` tier: LIA proof certificates have weaker tooling than the
bit-vector DRAT pipeline (pairs/python-smtlib brief). Do not inflate.

## Pinned oracle

`I_s` is **pinned real CPython** (`PYTHON_PIN`, the host CPython tag). The subset
has no nondeterministic surface (no wall-clock / RNG / hashing / I/O — enforced
by the loader's allow-list and the runtime restricted namespace with
`__builtins__` emptied), so a fixed CPython tag makes the trace byte-reproducible
(ARCHITECTURE.md §4).
