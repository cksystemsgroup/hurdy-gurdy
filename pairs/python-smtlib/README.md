# Pair — `python-smtlib`  ·  Python → SMT-LIB

*Status: **registered** — design questions resolved (2026-06-22); **gated on the
`QF_LIA` SMT-LIB language extension** ([`languages/smtlib`](../../languages/smtlib/README.md)).
Do not trigger the per-pair agent until that prerequisite is built.*

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
  `QF_LIA` by **bounded unrolling** (BMC): SSA + a fixed per-construct lowering,
  loops unrolled to a caller-supplied bound `k`. Deterministic and
  byte-reproducible (the predictability test, [`PAIRING.md`](../../PAIRING.md)
  §2). CHC / Horn clauses (unbounded loops via invariant inference) is the named
  **widening** direction, not the first slice.
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
