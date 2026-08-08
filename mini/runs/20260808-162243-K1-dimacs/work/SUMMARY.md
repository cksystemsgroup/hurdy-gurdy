# SUMMARY

## What was built

Domain: `dimacs` (DIMACS CNF SAT). The registry started empty; four
entries were built and admitted through `kernel.py gate`:

- **`dimacs`** (language) — `interp.py` checks a candidate total
  assignment against a CNF file and reports the observable `sat`.
  This is the only ground truth in the system: every witness a
  solver proposes gets replayed here. 7 hand-written vectors, 3
  mutants (always-true, flipped polarity, drops the last clause) —
  each mutant is caught by at least one vector.

- **`dimacs-cadical`** (solver, `lineage: [cadical, cake_lpr]`) — runs
  the `cadical` SAT solver. SAT instances return a `witness`
  (the model); UNSAT instances return `all(bound="inf")` carrying an
  **LRAT** refutation proof, discharged by `cake_lpr` (a HOL4-verified
  checker — a different codebase from the solver that produced the
  proof). 4-item corpus, 3 solver mutants, 4 certificate mutants
  (wrong format, empty proof, garbage, and a proof lifted from a
  different formula) — all correctly rejected.

- **`dimacs-z3`** (solver, `lineage: [z3]`) — runs Z3's DIMACS front
  end as a second, wholly independent decision procedure. SAT
  instances return a witness; UNSAT instances return
  `all(bound="inf", cert=null)` — claimed, not certified, since the
  CLI path used here doesn't hand back a checkable proof. Same
  4-item corpus, 2 solver mutants.

- **`dimacs-dpll`** (solver, `lineage: [dimacs-dpll-scratch]`) — a
  from-scratch chronological DPLL search (unit propagation + a
  most-active-variable branching heuristic), no external SAT engine
  anywhere. UNSAT instances emit a proof trace: at every failed
  branch the negation of the accumulated decision literals is
  provably RUP (unit-propagation-checkable) against the original
  clauses plus every earlier proof line — the standard way to read a
  resolution refutation off a DPLL trace, just without LRAT's hint
  numbers. `discharge.py` re-verifies that trace with its own
  from-scratch RUP checker (`dpll_core.verify`), sharing no code with
  cadical, cake_lpr, or z3. 4-item corpus (the pigeonhole one moved
  to slot 003 on purpose, so `cert_prog` is an instance that actually
  needs case-splitting — a trivial 2-clause instance made every
  certificate trivially "RUP" and hid bad ones), 3 solver mutants, 5
  certificate mutants.

All three solvers decide the same observable (`sat`) on the same
language, directly — no translation pairs were needed, so none were
built; per the contract's semantics-first order, decision procedures
were exhausted before reaching for syntax.

## What the two maps say

Both `benchmarks/dimacs-mixed` and `benchmarks/dimacs-harder` are
fully closed: **8 of 8 questions terminal**, every one **corroborated**
across three disjoint lineages (`{cadical, cake_lpr}`, `{z3}`,
`{dimacs-dpll-scratch}`), no contradictions.

| question | best | grade |
|---|---|---|
| rand-sat-a (SAT) | witness, depth 20 | replayed +corroborated |
| rand-sat-b (SAT) | witness, depth 24 | replayed +corroborated |
| php43-unsat | all(inf) | certified +corroborated |
| php54-unsat | all(inf) | certified +corroborated |
| rand-sat-c (SAT) | witness, depth 30 | replayed +corroborated |
| rand-sat-d (SAT) | witness, depth 40 | replayed +corroborated |
| php65-unsat | all(inf) | certified +corroborated |
| dense-unsat | all(inf) | certified +corroborated |

The from-scratch DPLL closed every UNSAT instance too, with proof
lengths of 11 (php43), 47 (php54), 239 (php65), and 9 (dense) RUP
lines, all found in well under a second — these are small, structured
instances (≤40 variables), so no search engine here was ever under
real pressure.

Frontier: **reached** (every question terminal on both benchmarks)
and **expanded**: every UNSAT verdict was lifted from claimed to
certified via a discharging certificate (twice over — cake_lpr and
the from-scratch RUP checker are independent certifiers), and every
verdict — SAT and UNSAT alike — is corroborated by three disjoint
codebases rather than resting on one solver family's word.

## What remains open, and why it's hard

Nothing is open on either pinned benchmark. Both are fully decided at
the best available grade.

What would make the frontier interesting to push further isn't
present in these benchmarks: everything here is small enough that
`cadical`, Z3, and a bare from-scratch DPLL all agree in milliseconds.
The genuine open problems in this domain live past this pin's scope —
larger/harder instances (industrial SAT competition benchmarks,
structured crypto/verification CNFs, or pigeonhole instances large
enough that even cadical needs real conflict-driven learning) would
be where `dimacs-dpll`'s plain chronological search runs out of road
long before `dimacs-cadical` does, which is itself a fact worth
surfacing rather than hiding: this registry's second solver is
honestly weaker than its first, and that gap is exactly what
corroboration is supposed to expose, not paper over.
