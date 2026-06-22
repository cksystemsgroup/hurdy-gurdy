# Language — Python

*Status: **partial** — the shared source interpreter `I_s` is built
(`gurdy/languages/python/`, interp v0.4): **pinned real CPython restricted to the
subset**. A loader (`subset.load`) rejects any out-of-subset AST node with a
typed `unsupported: python:<construct>`; the accepted program runs under the host
CPython (tag recorded as `PYTHON_PIN`, e.g. `CPython 3.12.0`) in a restricted
namespace (`__builtins__` emptied — no imports / no I/O), producing a
deterministic post-step environment trace. Covered: a integer function of
assignment + linear arithmetic + `if`/`else` (slice 2: the guard evaluated
through CPython, only the taken arm executed) + a **bounded loop**
`for i in range(<const>)` (slice 3: the body run once per `i = 0..n-1`, the loop
variable dropped after the loop) + a **BMC-bounded loop** `while <cond>: <body>`
(slice 4: the guard evaluated through CPython, the body run while it holds, capped
at the BMC bound `WHILE_BOUND` = 8 so an unbounded loop can never hang `I_s`; the
body-only names dropped after the loop), terminated by a single trailing `assert`;
every other construct hard-aborts. Built with the `python-smtlib` pair
([`pairs/python-smtlib`](../../pairs/python-smtlib/README.md)). Widen by the
coverage ratchet.*

A defined **subset** of Python, as a high-level source language. Source of the
`python-smtlib` pair —
[`pairs/python-smtlib`](../../pairs/python-smtlib/README.md).

## Formal semantics (source of truth)

Python's reference semantics is the CPython language reference — informal and
large — so the pair fixes a **subset** with a precise small-step semantics over
an environment (the heap enters only when containers / objects are added). The
in-scope subset so far is integers, assignment, linear arithmetic, comparison,
**`if`/`else`** (slice 2 — the SSA branch merge), a **bounded loop**
`for i in range(<const>)` (slice 3 — a compile-time-constant trip count, fully
unrolled by `T`), and a **BMC-bounded loop** `while <cond>: <body>` (slice 4 —
unrolled to the fixed bound `K` = `WHILE_BOUND` with a terminated-within-`K`
assertion). **Unbounded** loops (proving termination / invariant inference),
nested loops, `break`/`continue`, and boolean operators / containers are the named
next widenings, out of scope and hard-aborting until then. The subset is the
pair's to widen by the coverage ratchet, never to shrink.

## Formal model — no Sail; the real interpreter is the oracle

Not an ISA — no Sail. The shared source interpreter `I_s` is **pinned real
CPython restricted to the subset**, not a hand-written mirror: a full Python
semantics is too large to re-derive faithfully, and CPython *is* the de-facto
semantics. The loader enforces the subset by rejecting any out-of-subset AST node
with a typed `unsupported: python:<construct>` (no silent drop), then executes the
accepted program under a pinned CPython tag, recording a trace of post-step
environment states ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5). This makes the
source side `checked` against CPython exactly as RISC-V is `checked` against
`sail_riscv_sim` — the high-level analogue of an ISA differential.

Heavier formal references, added as later cross-checks (not blockers):

- **K-Python** — Dwight Guth's Python 3.3 semantics in the **K framework**, tested
  against CPython; the formal gold oracle for the chosen subset.
- A recent executable **structural operational semantics** for Python, usable as
  a second reference.

## Shared interpreter

**Role: source. Built (interp v0.4, `gurdy/languages/python/`).** A deterministic
executor of the subset over an input binding → a trace of post-step program
states, realized as **sandboxed pinned CPython** restricted to the subset (the
soundness trade-off [`PAIRING.md`](../../PAIRING.md) §6/§9 resolves toward the
real interpreter). The loader (`subset.py`) is the subset boundary — it accepts
an AST allow-list (a single integer function: assignment + linear arithmetic +
`if`/`else` + a bounded `for i in range(<const>)` loop + a BMC-bounded
`while <cond>` loop + a trailing `assert`) and rejects everything else with a
typed `unsupported: python:<construct>`; the executor (`eval.py`) runs the
accepted program under the
host CPython (`PYTHON_PIN`) in a restricted namespace with `__builtins__` emptied,
so no import / no I/O / no name resolves outside the program's own variables.
Deterministic by pinning the CPython tag and the subset's lack of any
nondeterministic surface (no wall-clock, hashing-order, RNG, or I/O in scope) —
byte-stable across `PYTHONHASHSEED`. Shared by every Python pair.

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): the **CPython test
suite**, restricted to the chosen subset and pinned to a CPython tag, with
K-Python as the differential oracle. (Built with the pair, once its `QF_LIA`
prerequisite lands.)

## Pairs over this language

- [`python-smtlib`](../../pairs/python-smtlib/README.md) — source (**partial** —
  minimal vertical slice built).
