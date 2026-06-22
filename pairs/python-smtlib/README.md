# Pair — `python-smtlib`  ·  Python → SMT-LIB

*Status: **partial** — slice 3 built (bounded-loop widening, 2026-06-22). In-scope
end-to-end through the commuting square: a **straight-line integer function**
(integer assignment + linear arithmetic `+` / `-` / `*`-by-constant), **`if`/`else`**
(lowered by the SSA branch merge — an `ite` join), and a **bounded loop**
`for i in range(<const>)` (fully unrolled `<const>` times over the advancing SSA),
terminated by a single `assert`. Every other Python construct hard-aborts
`unsupported: python:<construct>`. The `QF_LIA` SMT-LIB prerequisite
([`languages/smtlib`](../../languages/smtlib/README.md), interp v0.2) is built;
this pair reuses it. Implementation: `gurdy/pairs/python_smtlib/` (translator
`T`, carry-back `L`, `reach`/`cross_check`, `SPEC.md`) + `gurdy/languages/python/`
(the shared source interpreter `I_s`, interp v0.3). Widen by the coverage ratchet
— nested / `while` loops (CHC, the named growth path), then containers (arrays
theory) — next.*

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
- **`I_s`** (`gurdy/languages/python/`, interp v0.2): **pinned real CPython**
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
- **Coverage (`unsupported` histogram) — the ratchet grew (slice 3):** **4 / 18**
  probes covered (`straightline-int`, `if-else`, `bare-if`, `for-loop`) — up from
  slice 2's 3 / 16; `for-loop` (the bounded loop) moved from unsupported to
  covered (nothing dropped). The denominator grew by two probes that itemize the
  loop boundary (`nested-loop`→`For`, `nonconst-range`). The remaining gap,
  itemized: `{While:1, For:1, nonconst-range:1, FloorDiv:1, Mod:1, Div:1, Pow:1,
  nonlinear-mul:1, BoolOp:1, Call:1, List:1, Return:1, Import:1, no-assert:1}`.
  Honest `partial`.
- **Interp version bump (additive):** the shared Python interpreter `0.2`→`0.3`
  and the translator `0.2`→`0.3` — the allow-list and the schema only grow, so
  every slice-2 program is accepted and lowered/executed identically (the cache
  key bumps with the schema). Recorded in `gurdy/languages/python/__init__.py`
  and the pair registration.
- **Tests:** `tests/test_python_interp.py`, `tests/test_python_smtlib.py`
  (determinism twice-and-diff across `PYTHONHASHSEED`, including the if-merge
  ordering **and the loop-unroll / loop-trace**; per-construct schema incl. the
  byte-exact `ite` join **and the byte-exact unrolling**; the ratchet growth +
  typed-abort histogram; commuting-square `I_s(p)` vs `L(I_t(T(p)))` on
  straight-line, `if`/`else`, **and bounded-loop** corpora; `sat` carry-back fires
  the assert via the taken branch / the **unrolled loop** + matching UNREACHABLE
  loop invariants; the `if`-arm and **loop boundary** abort — nested loop,
  non-constant / start-step / negative range, `break`/`continue`, an assert in the
  loop body, a loop-variable / body-only read after the loop; registration smoke).

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
- **Target.** SMT-LIB (`QF_LIA`; arrays for containers later) —
  [`languages/smtlib`](../../languages/smtlib/README.md).
- **Translator `T`.** A schema-determined encoding of the in-scope subset to
  `QF_LIA` by **bounded unrolling** (BMC): SSA + a fixed per-construct lowering.
  The first bounded loop (slice 3) is `for i in range(<const>)`, **fully unrolled**
  to its **compile-time-constant** trip count — the simplest bound convention (a
  fixed count read straight from the source, no caller-supplied `k`, no
  per-iteration condition). A caller-supplied bound `k` for a `while`-style loop
  (iterations past the bound gated, plus a "terminated within `k`" assertion) is
  the named next unrolling step; CHC / Horn clauses (unbounded loops via invariant
  inference) is the further **widening** direction. Deterministic and
  byte-reproducible (the predictability test, [`PAIRING.md`](../../PAIRING.md) §2).
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
- **Subset (start thin, ratchet).** First slice in scope: `int` (as `Int`),
  `bool`, assignment, arithmetic / comparison / boolean operators, `if`/`else`,
  one bounded `while` / `for i in range(n)`, and `assert`. Out of scope
  (hard-abort `unsupported: python:<construct>`): `list`/`dict`/`set`/`str`,
  classes / objects, exceptions, `import`, floats, recursion, comprehensions,
  generators, dynamic attributes. Widen by the coverage ratchet — containers
  (arrays theory) next.

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
