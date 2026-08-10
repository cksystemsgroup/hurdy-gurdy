# SUMMARY — K1, btor2

## What was built

Registry, from empty, five entries:

- **`btor2`** (language) — interprets a subset of BTOR2 (bitvec sorts;
  `zero/one/constd/state/input`; `add/sub/mul/and/not/ite/ult/eq`;
  `init/next/bad/constraint`) by replaying a concrete per-step input
  trace. 8 vectors exercise every op; 5 mutants (swap add/sub, alias
  mul to add, disable bad-detection, ignore constraints, off-by-one
  depth) all correctly fail the gate.

- **`btor2-explicit`** (solver, lineage `k1-btor2-py`) — exact
  explicit-state BFS over the reachable-state graph, enumerating every
  legal input combination per state. A completed BFS over a finite
  bitvector state space is a genuine proof, not a heuristic: fixpoint
  closure certifies `all(inf)`, a budget cutoff certifies `all(k)` for
  whatever depth was fully verified, and a discovered violation is a
  replayable witness. `discharge.py` re-verifies any reachable-set-closure
  certificate from scratch (never trusting `solve.py`): base state
  correct, no listed state is bad, every transition out stays inside
  the listed set. 6-item corpus, 5 solver mutants, 4 certificate
  mutants — all caught.

- **`btor2-congruence`** (solver, lineage `k1-btor2-congruence-py` +
  `z3`) — **the new decision procedure this run adds.** The curated
  benchmarks each got one extra "inf" question this round
  (`parity32-inf`, `mod4-32-inf`) built specifically so explicit-state
  BFS can't reach it: 32-bit counters whose true reachable set has up
  to 2^31 states, far past `btor2-explicit`'s 200,000-state budget.
  For a single-state system, `btor2-congruence` searches power-of-two
  congruence classes `state mod g == r` (g = 2, 4, 8, ..., 2^W) via two
  cheap bitvector SMT queries per candidate — inductive (no legal step
  leaves the class) and safe (no state in the class is `bad`) — using
  z3 directly on the symbolic transition, so checking cost is
  independent of how large the described reachable set actually is.
  The first working `g` yields a certificate of *constant* size
  regardless of state-space size. `discharge.py` independently
  re-derives and re-checks both SMT obligations from a fresh parse.
  Scope is honest and narrow: exactly one state variable, and only
  the op set the parser covers; anything else — or no power-of-two
  class that both holds and excludes `bad` — is an abstention, never a
  guess. 6-item corpus (including a genuinely-unsafe item so a
  broken checker that skips either obligation gets caught), 4 solver
  mutants, 4 certificate mutants — all caught.

- **`btormc`** (solver, lineage `btormc`) — external plain BMC, honest
  about its limits: a `sat` verdict yields a witness; `unsat` up to a
  finite `kmax` yields a bounded `all`; an unbounded ask that finds
  nothing is left a partial, because k-induction success isn't
  reliably readable from btormc's own stdout.

- **`pono`** (solver, lineage `pono`) — a second, independently-coded
  external model checker, for corroboration. BMC hunts for witnesses
  (empirically pono's plain BMC reports `unknown`, never a clean
  bounded-unsat, on a miss — so unlike btormc it's never stretched
  into a bounded `all`). For unbounded asks with no BMC violation,
  bit-level IC3 (`ic3bits`, falling back to `ic3ia`) is a real decision
  procedure for these finite-state systems: a clean `unsat` becomes
  `all(inf)`, ungraded (`claimed` — no certificate is parsed from
  pono's own inductive invariant), existing purely to corroborate
  `btor2-congruence`'s certified proofs from a disjoint codebase.
  (One wrinkle found and fixed: pono selects its parser from the file
  extension and rejects the contract's `NNN.program` corpus naming —
  `solve.py` copies to a `.btor2`-suffixed temp file first.)

## What the two maps say

Both benchmarks are **fully terminal at the highest grade, every
question corroborated**:

**btor2-counters — 7/7 terminal.**
| question | best | grade |
|---|---|---|
| parity32-inf | all (inf) | certified +corroborated |
| parity-inf | all (inf) | certified +corroborated |
| frozen-inf | all (inf) | certified +corroborated |
| blocked-inf | all (inf) | certified +corroborated |
| deep-reach | witness (depth 60) | replayed +corroborated |
| input-reach | witness (depth 1) | replayed +corroborated |
| bounded-miss | all (bound 199) | certified +corroborated |

**btor2-machines — 7/7 terminal.**
| question | best | grade |
|---|---|---|
| mod4-32-inf | all (inf) | certified +corroborated |
| lockstep-inf | all (inf) | certified +corroborated |
| deep-frontier | witness (depth 90) | replayed +corroborated |
| shift-reach | witness (depth 7) | replayed +corroborated |
| wrap-reach | witness (depth 13) | replayed +corroborated |
| twobad-any | witness (depth 0) | replayed +corroborated |
| deep-bounded-miss | all (bound 89) | certified +corroborated |

The two questions curated specifically to defeat a first-pass kit
(`parity32-inf`: a 32-bit counter +2 with an odd target; `mod4-32-inf`:
a 32-bit counter +4 with a non-multiple-of-4 target) are exactly the
ones `btor2-congruence` was built for, and both land at `certified`
— `btor2-explicit` alone only gets as far as `all(bound=199999)` on
them (a real, honest, but merely-bounded fact — it hits its
200,000-state search budget long before the true ~2^31-state
reachable set closes). Every terminal result is independently
corroborated by at least one solver of disjoint lineage (`pono` for
the congruence proofs; `btor2-explicit`/`btormc`/`pono` cross-checking
each other's witnesses). `report` regenerates both `frontier.md`s
byte-identically from `log.jsonl`, and a second `play` doubles the log
(append-only) while leaving the frontier unchanged (best-per-question
is stable) — both invariants checked directly.

## What remains open, and why

Nothing is open on either pinned benchmark — both maps are fully
closed. What's honestly *out of scope* of what got built, should this
domain widen:

- **`btor2-congruence` handles exactly one state variable.** A
  multi-state system (even two independent counters) is an immediate,
  honest abstention (see corpus item 004) — no attempt to project onto
  one state or compose per-state invariants. Real designs interleave
  state, and closing that gap is a genuine next decision procedure,
  not a tweak.
- **The invariant class is power-of-two congruence only** (`state mod
  2^k == r`). It closes every "safe forever" question these
  benchmarks pose because every one of them is, underneath, a
  bitmasking fact. A counter stepping by a non-power-of-two constant
  against a modulus that needs a general linear congruence (say, step
  3 mod 100) or a safety fact that isn't a residue class at all (an
  order relation, a disjunction of ranges) would fall through to
  `btor2-explicit`'s bound and then to honest partial — no false
  claims, but no proof either.
- **`btor2-explicit`'s reachable-set closure is capped at 200,000
  states.** For any single-state affine counter the congruence search
  now closes that gap, but a program whose true reachable set is huge
  *and* not congruence-shaped (e.g. driven by a wide unconstrained
  input with a reachable set that doesn't reduce to a residue class)
  would sit at whatever bounded depth the BFS reaches before budget,
  same as before this run.
- **pono's plain BMC never certifies a finite bound** (confirmed
  empirically: it reports `unknown`, not `unsat`, on every miss tried,
  at every `k`) — so despite running two external model checkers, only
  `btormc`'s `-kmax` convention and `btor2-explicit`'s own BFS ever
  produce a bounded `all`. `pono`'s value is entirely in witnesses and
  in `ic3bits`/`ic3ia` unbounded proofs, not bounded ones.
