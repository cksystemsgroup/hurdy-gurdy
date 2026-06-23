# Pair — `python-smtlib`  ·  Python → SMT-LIB

*Status: **partial** — slice 6 built (fixed-length integer lists, 2026-06-23).
In-scope end-to-end through the commuting square: a **straight-line integer function**
(integer assignment + linear arithmetic `+` / `-` / `*`-by-constant), **`if`/`else`**
(lowered by the SSA branch merge — an `ite` join), a **bounded loop**
`for i in range(<const>)` (fully unrolled `<const>` times over the advancing SSA),
a **BMC-bounded loop** `while <cond>: <body>` (unrolled to the fixed bound
`K` = 8 with per-iteration `ite` carry-through and a terminated-within-`K`
assertion), **nested loops** (a `for` / `while` inside another loop's body, or
inside an `if` arm inside a loop — the inner loop re-unrolled at each outer
iteration over the advancing SSA, within the depth/size caps `MAX_LOOP_DEPTH` = 2 /
`MAX_UNROLL_PRODUCT` = 64), and **fixed-length integer lists** (a list of static
length `L` modeled as a **tuple of `L` `Int` SSA vars** — *not* an SMT `Array`, so
the encoding stays in `QF_LIA`: list literal, constant / dynamic index read & write,
`len(xs)`, with `L` ≤ `MAX_LIST_LEN` = 16), terminated by a single `assert`. Every
other Python construct hard-aborts `unsupported: python:<construct>`. The `QF_LIA`
SMT-LIB prerequisite ([`languages/smtlib`](../../languages/smtlib/README.md), interp
v0.2) is built; this pair reuses it **unchanged** (no `Array` theory needed).
Implementation: `gurdy/pairs/python_smtlib/`
(translator `T`, carry-back `L`, `reach`/`cross_check`, `SPEC.md`) +
`gurdy/languages/python/` (the shared source interpreter `I_s`, interp v0.6). Widen
by the coverage ratchet — `break`/`continue`, then **unbounded** loops (proving
termination / invariant inference / CHC — the named growth path), then
variable-length containers (SMT array theory — the deliberate later trade) — next.*

## Slice 6 — fixed-length integer lists (2026-06-23)

- **Constructs added:** a **list literal** `xs = [e0, …, e{L-1}]` (each element an
  in-scope int expression; `L` the literal length), a **constant / dynamic index
  read** `xs[i]`, an **index write** `xs[i] = v` (SSA update), and `len(xs)`. See
  `SPEC.md` §"Integer lists".
- **The tuple-of-Ints model (stays in `QF_LIA`, no `Array` sort):** a list of
  statically-known length `L` is `L` separate `Int` SSA variables. A list literal
  declares `L` fresh `xs__<n>`, one per element. A **constant** index reads / updates
  that position directly (the loader bounds-checks the literal). A **dynamic** index
  `i` (an in-scope scalar int) fans out: a read is the right-fold `ite` chain
  `(ite (= i 0) e0 (ite (= i 1) e1 … e{L-1}))`; a write makes every position `j` a
  fresh `(ite (= i j) v old_j)`; both assert the path constraint `0 <= i < L`.
  `len(xs)` is the constant `L`. Because no `Array` sort is used, the pair reuses the
  shared `QF_LIA` evaluator and the solvers **unchanged**.
- **The length cap (the predictability test, `PAIRING.md` §2; the unrolling-bound
  cap, [`BENCHMARKS.md`](../../BENCHMARKS.md) §6):** the per-list element count is
  bounded by the fixed module constant `MAX_LIST_LEN = 16` in
  `gurdy/languages/python/subset.py` (a dynamic index fans out into an `L`-deep `ite`
  chain, so the cap bounds SMT size); a list literal longer than the cap hard-aborts
  `python:list-too-long` at load time.
- **Out-of-range handling (a sound under-approximation, like the `while` bound):** a
  *constant* out-of-range index is a definite error caught at load time
  (`list-index-out-of-range`); a *dynamic* index is range-asserted `0 <= i < L`, so
  an out-of-range access **excludes** the model (carried back as UNREACHABLE), never
  a silent wrong read. `I_s` (CPython) catches an out-of-range index as a defined
  error to stay total — a floor that never fires on a witnessed input (the model is
  range-constrained).
- **Carry-back:** CPython runs the real list natively (a literal builds it,
  `xs[i] = v` mutates it, `len` reads its length); the `sat` model's input — incl. a
  dynamic index the solver chose to land the read / write on the firing position —
  replayed through CPython drives the list's element values to the firing assert. The
  commuting square holds on a list corpus incl. **a list updated in a loop** and a
  **solver-steered dynamic index**.
- **Boundary kept out of scope (hard-aborting):** `append` / `pop` / `insert` (a
  length change), a non-constant-length / nested list, slicing, a list of non-int, a
  list used as an int (`list-as-int`), `for x in xs` (only `for i in range(…)`), an
  over-cap length (`list-too-long`), a list joined at an `if` / re-bound in a loop to
  a different length (`list-join-mismatch` / `list-len-changed-in-loop`).

## Slice 5 — nested loops (2026-06-23)

- **Construct added:** a `for` / `while` may appear **inside another loop's body**
  (and inside an `if` arm inside a loop). The inner loop is unrolled by the **same
  per-construct schema, applied recursively** (constant `for`: full unrolling;
  `while`: BMC to `K`) at *each* outer iteration over the advancing SSA, with the
  shared SSA counter threaded through both levels and the existing active-flag /
  `ite` carry-through composing through the outer `while`'s join. There is **no new
  rule** — nesting is composition of slice 3 and slice 4. See `SPEC.md` §"Nested
  loops".
- **The depth/size cap (the predictability test, `PAIRING.md` §2; the
  unrolling-bound cap, [`BENCHMARKS.md`](../../BENCHMARKS.md) §6):** because the
  inner loop is re-unrolled at every outer iteration, the unrolled body copies
  **multiply**, so two fixed module constants in `gurdy/languages/python/subset.py`
  bound the SMT size — `MAX_LOOP_DEPTH = 2` (the max loop nesting depth: a loop
  inside a loop inside a loop hard-aborts) and `MAX_UNROLL_PRODUCT = WHILE_BOUND *
  WHILE_BOUND = 64` (the max product of unroll bounds along a nesting path: a `for
  i in range(n)` contributes `n`, a `while` contributes `WHILE_BOUND`; entering a
  loop that would push the running product over 64 hard-aborts). Both caps are
  **static** (a `for`'s trip count is a source constant; a `while`'s is
  `WHILE_BOUND`), so a loop nested past either cap hard-aborts
  `python:nesting-too-deep` at **load time** — never an enormous emitted script.
  `while`-in-`while` (8 × 8 = 64) is at the cap and allowed; `for range(9)` with a
  `while` inside (9 × 8 = 72) is over and aborts.
- **Carry-back:** CPython runs the real nested loops natively (each inner `while`
  capped at `K`), so the `sat` model's input replayed through CPython drives both
  levels the same number of iterations the recursive unrolling encodes to the
  firing assert — the same finite computation the multiplied SSA encodes.
- **Boundary kept out of scope (hard-aborting):** a loop nested deeper than
  `MAX_LOOP_DEPTH` or whose unrolled product would exceed `MAX_UNROLL_PRODUCT`
  (`nesting-too-deep`); `break` / `continue` (`Break` / `Continue`) at any level
  still abort.

## Slice 4 — BMC-bounded loop `while <cond>: <body>` (2026-06-23)

- **Construct added:** `while <cond>: <body>` — a **BMC-bounded loop**. `<cond>`
  is one integer comparison; `<body>` is a body of in-scope statements (assignment
  / nested `if`; **no** nested loop, **no** `assert`, **no** `break` / `continue`).
  **Lowered by bounded unrolling:** `T` unrolls `<body>` to the fixed bound `K`
  over the advancing SSA. Iteration `j` is gated by an *active* flag
  `active_j = cond_0 ∧ … ∧ cond_j` (a fresh `Bool` SSA symbol — the loop condition
  held at every iteration so far), and every variable the body changes is joined
  `(ite active_j body_value carried_value)` — when the loop is no longer active the
  value is carried through unchanged (a no-op iteration). After `K` iterations the
  encoding **asserts the loop terminated within `K`**: the condition lowered over
  the post-loop SSA map must be false `(assert (not cond_final))`. Body-only locals
  are dropped after the loop (it may run zero times or hit the bound); an
  accumulator read after the loop must be initialised *before* it. See `SPEC.md` §6.
- **Bound convention (the predictability test, `PAIRING.md` §2):** the unrolling
  depth is the **fixed module constant `WHILE_BOUND = 8`** in
  `gurdy/languages/python/subset.py` — *not* a heuristic, not adaptive, not a
  per-program choice. It is kept small (≤ 8) to bound SMT size
  ([`BENCHMARKS.md`](../../BENCHMARKS.md) §6, the unrolling-bound cap). The same
  constant is the executor's replay cap, so `I_s` and `T` unroll the same depth and
  anyone with the source can reproduce the unrolled bytes exactly.
- **Termination within `K` (the verdict's meaning):** the decided question becomes
  *"is there an input that **terminates within `K`** and violates the assert?"*. A
  run that would need a `(K+1)`-th iteration is **excluded** by the termination
  assertion — a **sound under-approximation of reachability** (BMC), reported as
  "no terminating-within-`K` counterexample" (UNREACHABLE), never a silent wrong
  answer. `I_s` runs the real `while` (capped at `K` for safety — the cap never
  fires on a witnessed input, since the solver only returns terminating-within-`K`
  models); the `sat` model's input replayed through CPython drives the loop the
  same number of iterations to the firing assert.
- **Boundary kept out of scope (hard-aborting):** a *nested* loop in a `while` body
  (`For` / `While`), `break` / `continue` (`Break` / `Continue`), `while … else`
  (`while-else`), an `assert` in the body (`branch-assert`), a non-comparison guard
  (`BoolOp`), and a body-only name read after the loop (`undefined-name`).

## Slice 3 — bounded loop `for i in range(<const>)` (2026-06-22)

- **Construct added:** `for <i> in range(<const>): <body>` — a **bounded loop**
  whose trip count is a **compile-time-constant non-negative integer literal**
  `<const>` (the bound convention — *not* a caller-supplied `k`). `<body>` is a
  body of in-scope statements (assignment / nested `if`; **no** nested loop and
  **no** `assert` in the body). **Lowered by full unrolling:** `T` re-lowers
  `<body>` `<const>` times over the advancing SSA, binding the loop variable `i`
  to the concrete iteration index `0, 1, …, n-1` (a literal — a read of `i` in the
  body lowers to that numeral). The trip count is constant, so every iteration is
  unconditional — **no per-iteration `ite`** (unlike a branch). After the loop the
  loop variable and any body-only local are dropped (not readable post-loop —
  `range(n)` may have `n == 0`); an accumulator read after the loop must be
  initialised *before* it. `range(0)` unrolls to nothing. See `SPEC.md` §5.
- **Bound convention (the predictability test, `PAIRING.md` §2):** the unrolled
  iteration count is exactly the literal `n` in `range(n)`; there is one in-scope
  shape, `range(<non-negative-int-literal>)`. A non-constant bound
  (`nonconst-range`), a start/step `range(a, b[, c])` (`range-shape`), a negative
  literal (`negative-range`), a non-`range` iterable (`nonrange-loop`), a
  `for…else` (`for-else`), a *nested* loop (`For`), and `break`/`continue`
  (`Break`/`Continue`) all hard-abort — so anyone with the source can reproduce
  the unrolled bytes exactly.

## Slice 2 — `if`/`else` (2026-06-22)

- **Construct added:** `if <cond>: <arm>` with optional `else: <arm>` (bare `if`
  and nested `if` included), `<cond>` one integer comparison, each arm a body of
  in-scope statements (assignment / nested `if`; **no** `assert`/loop in an arm).
  Lowered by the **SSA branch merge**: each variable reassigned on either arm is
  joined at the `if` as `(ite C then_ssa else_ssa)`; a side that did not reassign
  it contributes its incoming value; a variable assigned on only one arm is not
  readable after the join (`undefined-name`). See `SPEC.md` §4.

## Slice 1 — straight-line integer function (2026-06-22)

- **Construct covered end-to-end:** straight-line integer function — integer
  assignment, linear arithmetic (`+`, `-`, `*`-by-constant), one trailing
  `assert <int-compare>`. Property decided: *can the assert be violated for some
  integer input?* (`sat` ⇒ REACHABLE/violable, model = a concrete violating
  input; `unsat` ⇒ UNREACHABLE/holds-for-all).
- **`T`** (`translate.py`, `predicted`): SSA renaming in source order + the fixed
  per-construct lowering of `SPEC.md` (assignment, the branch-merge `ite`, the
  property); byte-reproducible across `PYTHONHASHSEED`.
- **`L`** (`lift.py`): decode the `sat` model's `<p>__in` input assignment and
  **replay it through pinned CPython** to exhibit the firing assert — with
  `if`/`else`, the replay walks only the branch the input selects, so the
  violating input drives the run down the branch that fires the assert.
- **`I_s`** (`gurdy/languages/python/`, interp v0.6): **pinned real CPython**
  (host tag recorded as `PYTHON_PIN`, e.g. `CPython 3.12.0`) restricted to the
  subset — a loader rejects any out-of-subset AST node with a typed
  `unsupported: python:<construct>`, the accepted program runs in a restricted
  namespace (`__builtins__` emptied: no imports / no I/O), producing a post-step
  environment trace.
- **`π`:** the named program variables at the observation point + the statement
  kind + the property verdict (`__cond__` / `__violated__`).
- **Fidelity:** `predicted` on the encoding + **`checked`** overall (the CPython
  differential validates the square every run via `cross_check`); **not**
  `proved` (LIA proof certificates have weaker tooling — not inflated).
- **div/mod:** `//` and `%` are **out of scope** (hard-abort `python:FloorDiv` /
  `python:Mod`). SMT-LIB `div`/`mod` are Euclidean while Python `//`/`%` are
  floored — they differ for negative operands; widening requires the explicit
  floor↔Euclidean correction (recorded in `SPEC.md`). Slice 1 uses arithmetic
  without division to sidestep it cleanly.
- **Coverage (`unsupported` histogram) — the ratchet grew (slice 6):** **11 / 27**
  probes covered (`straightline-int`, `if-else`, `bare-if`, `for-loop`,
  `while-loop`, `nested-loop`, `list-literal`, `list-index-read`,
  `list-index-write`, `list-dynamic-index`, `list-len`) — up from slice 5's 6 / 20;
  the five list constructs moved from unsupported (`List` / `Call` / `Subscript`) to
  covered (nothing dropped — `List` leaves the gap entirely now that a flat int list
  literal is in scope). The denominator grew by the new list-boundary probes that
  itemize the gap honestly (`list-too-long`, `nested-list`, the `append` `Expr`). The
  remaining gap, itemized: `{nesting-too-deep:1, nonconst-range:1, Break:1,
  FloorDiv:1, Mod:1, Div:1, Pow:1, nonlinear-mul:1, BoolOp:1, Call:1, list-too-long:1,
  nested-list:1, Expr:1, Return:1, Import:1, no-assert:1}`. Honest `partial`.
- **Interp version bump (additive):** the shared Python interpreter `0.5`→`0.6`
  and the translator `0.5`→`0.6` — the allow-list and the schema only grow (the
  loader newly admits the list AST nodes within the cap; the executor newly runs the
  real list and exposes only the `len` builtin; the translator's tuple-of-Ints
  lowering is new symbols only), so every slice-5 program is accepted and
  lowered/executed identically (the existing nested-loop / `while` / `if` /
  straight-line bytes are **byte-unchanged** — verified by a HEAD-vs-current diff;
  the cache key bumps with the schema). The shared `QF_LIA` SMT-LIB evaluator and the
  solvers are **unchanged** (no `Array` theory). Recorded in
  `gurdy/languages/python/__init__.py` and the pair registration.
- **Tests:** `tests/test_python_interp.py`, `tests/test_python_smtlib.py`
  (determinism twice-and-diff across `PYTHONHASHSEED`, including the if-merge
  ordering, the for-loop / while-loop / nested-loop unroll/trace, **and the list
  lowering** (loop-then-dynamic-write); per-construct schema incl. the byte-exact
  `ite` join, the byte-exact for / while / nested unrolling, **and the byte-exact
  list literal (L fresh Int vars), the const-index read/write, the dynamic-index
  `ite` chain + `0 <= i < L` range constraint, the per-position dynamic write, and
  `len` → the constant `L`**; a test asserting **no `Array` sort / `select` / `store`
  appears in the emitted SMT** (stays `QF_LIA`); the ratchet growth + typed-abort
  histogram; commuting-square `I_s(p)` vs `L(I_t(T(p)))` on straight-line, `if`/`else`,
  loop, nested-loop **and list** corpora (literal + const index, dynamic read/write,
  `len`, **a list updated in a loop**); `sat` carry-back fires the assert via the
  taken branch / the unrolled loops / **the list driven to its firing element (incl.
  a solver-steered dynamic index where the model picks `i` to hit a specific
  position)** + matching UNREACHABLE loop / **list (sum-of-elements, `len`)**
  invariants; the loop boundary **and the list boundary** abort — an over-cap length
  (`list-too-long`), a nested list, `append`, a list-as-int, an out-of-range constant
  index, `for x in xs`; the **out-of-range dynamic index recorded as a defined error**
  keeping `I_s` total; registration smoke).

## What the §9 open question taught us (high-level source, large real interpreter)

The brief's central wager — that a high-level language whose real interpreter is
too large to mirror can be `checked` by **re-executing the real interpreter**
rather than a hand-written one — held for the slice. The loader's AST allow-list
*is* the subset boundary, so the "restricted real interpreter" is exactly: parse,
reject out-of-subset nodes, run what's left under pinned CPython with builtins
removed. The unbounded-`int` → `Int`/`QF_LIA` fit paid off directly: a property
like `2*x == x + x` is UNREACHABLE over *all* integers (no 64-bit wraparound
counterexample), which a bit-vector lowering could not have shown — the
faithfulness the direct-to-LIA route was chosen for.

Compile a defined **subset** of Python **directly to the SMT-LIB hub** — the
`crn-smtlib` pattern (schema-determined unrolling into SMT, witness replayed
through the source interpreter) scaled up to a high-level language. Python is
**not** routed through the BTOR2 hub: it is not a machine (unbounded integers,
dynamic typing, a heap), so bit-blasting it to fixed-width words would be
*unfaithful*, and compiling it to an existing front-end would bury a hidden
intermediate language inside the translator
([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §9). Python's unbounded `int` maps
cleanly and faithfully to SMT `Int` (LIA) — a fit only the direct-to-SMT-LIB
route affords.

This pair is the platform's test of the hardest open question in
[`PAIRING.md`](../../PAIRING.md) §9 — the soundness story for a high-level
language whose real interpreter is large — now **answered** (below) rather than
deferred.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** Python (a subset) —
  [`languages/python`](../../languages/python/README.md).
- **Target.** SMT-LIB (`QF_LIA`; **fixed-length integer lists modeled as a tuple of
  `Int`s, not an `Array`** — array theory only for variable-length containers later)
  — [`languages/smtlib`](../../languages/smtlib/README.md).
- **Translator `T`.** A schema-determined encoding of the in-scope subset to
  `QF_LIA` by **bounded unrolling** (BMC): SSA + a fixed per-construct lowering.
  The first bounded loop (slice 3) is `for i in range(<const>)`, **fully unrolled**
  to its **compile-time-constant** trip count — the simplest bound convention (a
  fixed count read straight from the source, no per-iteration condition). The
  `while <cond>` loop (slice 4) is **unrolled to a fixed bound `K`** — the module
  constant `WHILE_BOUND = 8` (not a caller-supplied `k`; the most predictable
  choice, `PAIRING.md` §2), with each iteration gated by an `ite` carry-through and
  a **"terminated within `K`" assertion** so the property is decided over runs that
  terminate within `K` (a sound BMC under-approximation). **Nested loops** (slice 5)
  compose these recursively: an inner loop is re-unrolled at each outer iteration
  over the advancing SSA (the shared SSA counter threaded through both levels),
  bounded by the depth/size caps `MAX_LOOP_DEPTH` = 2 / `MAX_UNROLL_PRODUCT` = 64 so
  the multiplied unrolling stays small (a loop nested past either cap hard-aborts
  `nesting-too-deep`). **Unbounded** loops (proving termination, or invariant
  inference / CHC / Horn clauses) are the further **widening** direction.
  Deterministic and byte-reproducible (the predictability test,
  [`PAIRING.md`](../../PAIRING.md) §2).
- **Source interpreter `I_s`.** The shared Python-subset interpreter
  ([`languages/python`](../../languages/python/README.md)) — **pinned real
  CPython restricted to the subset**, not a hand-written mirror (the §9
  trade-off, resolved toward the real interpreter as the source oracle).
- **Target interpreter `I_t`.** SMT-LIB's `QF_LIA` model evaluator + text I/O —
  reused (the gating extension).
- **Target-to-source interpreter `L`.** Decodes a `sat` SMT model — the
  satisfying **input assignment** — and **re-runs it through CPython** to exhibit
  the property (the assertion that fires / the reached state). Pair-owned.

## Decisions (resolved — these were the open questions)

- **Target shape & logic.** `Int` / `QF_LIA`, **bounded unrolling** first; CHC is
  the growth path for unbounded loops. (A bit-vector / bounded-machine-int subset
  → BTOR2 / `QF_ABV` is a *deliberate* later trade to reach the bit-blast
  `proved` tier; **not** the default, because it sacrifices faithfulness to
  Python's unbounded ints.)
- **Soundness story** ([`PAIRING.md`](../../PAIRING.md) §6, §9). `I_s`
  **re-executes against pinned real CPython** restricted to the subset; the subset
  is enforced by the loader rejecting any out-of-subset AST node with a typed
  `unsupported: python:<construct>`. The commuting square is `I_s(p)` (CPython,
  the oracle) vs `L(I_t(T(p)))` (SMT model replayed through CPython), under `π`.
  K-Python (Guth, restricted to the subset) is the heavier formal cross-check,
  added later — not a blocker.
- **Subset (start thin, ratchet).** In scope now: `int` (as `Int`), assignment,
  linear arithmetic / comparison, `if`/`else`, a bounded `while` / `for i in
  range(n)`, nested loops, **fixed-length integer lists** (a tuple of `Int`s — list
  literal, const / dynamic index read & write, `len`), and `assert`. Out of scope
  (hard-abort `unsupported: python:<construct>`): variable-length / nested lists,
  `append`/`pop`/`insert`, slicing, `dict`/`set`/`str`, classes / objects,
  exceptions, `import`, floats, recursion, comprehensions, generators, dynamic
  attributes. Widen by the coverage ratchet — `break`/`continue`, then unbounded
  loops, then variable-length containers (SMT array theory — the deliberate later
  trade) next.

## Fidelity target

- **`predicted`** on the encoding (schema-determined, byte-reproducible from the
  spec) and **`checked`** overall (the square validated every run via the CPython
  differential). The ceiling is `checked`, **not** the bit-blast `proved` tier:
  LIA proof certificates have weaker tooling than the bit-vector DRAT pipeline.
  Do not inflate.
- **`π`** = the named program-variable environment at the observation point, plus
  the property verdict (REACHABLE / UNREACHABLE of the target predicate, e.g.
  `assert False`).

## Prerequisite (the gate)

- The shared SMT-LIB **`QF_LIA` model evaluator** must exist first
  ([`languages/smtlib`](../../languages/smtlib/README.md); REGISTRY "Platform
  deliverables"). `crn-smtlib` already surfaced the gap — the `QF_ABV`-only
  evaluator returns `smt_model_ok=None` on its `QF_LIA` script and falls back to
  source-interpreter replay. This pair reuses that machinery once the evaluator
  lands; until then the per-pair agent is **not** triggered
  ([`AGENTS.md`](../../AGENTS.md) §1, §5).

## Public benchmarks

- Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): the **CPython test
  suite**, restricted to the chosen subset and pinned to a CPython tag, with
  K-Python as a later differential oracle.

## Notes

- Registration is now a settled human act — the subset and the soundness story
  are fixed above ([`AGENTS.md`](../../AGENTS.md) §1). The remaining gate is purely
  the `QF_LIA` prerequisite, not an open design question.
- Solvers/checkers are SMT-LIB's shared inventory
  ([`SOLVERS.md`](../../SOLVERS.md)); z3 / cvc5 decide `QF_LIA`. The pair wires
  none of its own.
