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
  (assignments and nested `if` — **no** `assert`, `while`, or `for` inside an
  arm). A variable assigned on *both* arms (or already in scope before the `if`)
  is readable after the join; one first assigned on only one arm is **not** (it
  may be undefined on the other path — reading it later aborts `undefined-name`);
- a single trailing `assert <l> <cmp> <r>` whose condition is one integer
  comparison with `<cmp>` in `== != < <= > >=`.

Everything else hard-aborts with a typed `unsupported: python:<construct>`
(BENCHMARKS.md §3), never a silent drop. The histogram key is the offending AST
node class (or a named guard):

| construct | abort key |
|---|---|
| `while` loop | `python:While` |
| `for` loop | `python:For` |
| floored division `//` | `python:FloorDiv` |
| modulo `%` | `python:Mod` |
| true (float) division `/` | `python:Div` |
| exponent `**` | `python:Pow` |
| variable-by-variable product `x*x` | `python:nonlinear-mul` |
| boolean operator `and` / `or` | `python:BoolOp` |
| function call | `python:Call` |
| `list` / `dict` / `set` literal | `python:List` / … |
| `return <expr>` | `python:Return` |
| `import` | `python:Import` |
| chained / tuple assignment | `python:multiple-targets` |
| non-`Name` assignment target | `python:Attribute` / `python:Subscript` / … |
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
5. **Property.** The trailing `assert cond` lowers `cond` (one comparison
   `l <op> r`) to a predicate `C`: `==`→`(= l r)`, `!=`→`(distinct l r)`, and
   `< <= > >=` straight across, reading each name at its **joined** SSA version.
   The script asserts the **negation** `(assert (not C))`.
6. `(check-sat)`.

The script is `sat` **iff some integer input violates the assert** — i.e.
`not cond` is reachable. That is the property the pair decides:

- `sat` → REACHABLE: the assert is *violable*; the model binds each `p__in` to a
  concrete violating input.
- `unsat` → UNREACHABLE: the assert *holds for every integer input* (the solver
  proves it over all inputs; carried back as UNREACHABLE).

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
`ite`-joined value fire the assert — the branch the solver selected via `C`.
Soundness (PAIRING.md §6) is byte-prediction (this schema) **plus** model
validation:

- `smt_model_ok` — the shared `QF_LIA` evaluator re-checks the solver's model
  against the emitted script (the authoritative SMT-level witness check);
- `witness_ok` — the CPython replay's final (assert) state is `__violated__`,
  i.e. the assert genuinely fires on the decoded input.

The two must agree for a REACHABLE verdict; a divergence is a translator-or-solver
fault, localized by the commuting-square oracle.

## Projection `π`

The named program variables at the observation point (parameters + locals, in
declaration / first-assignment order) plus the statement kind `__stmt__`, the
condition truth `__cond__`, and the property verdict `__violated__` —
`projection_for(program)`. The commuting-square check `cross_check` runs `I_s(p)`
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
