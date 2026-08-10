# dimacs — summary

## What was built

The registry started empty. Four entries were admitted through the gate:

- **`dimacs`** (language) — `interp.py` evaluates a CNF program against a
  JSON assignment (a signed-literal list) and reports `{sat, depth}`.
  4 vectors, 3 mutants (drops negation, checks only the first clause,
  always claims sat).

- **`dimacs-cadical`** (solver) — the standard-of-truth decision
  procedure. Runs `cadical`; SAT becomes a replayed witness (the
  assignment is fed back through `interp.py`), UNSAT becomes
  `all(bound=inf)` with an LRAT certificate produced by `drat-trim`
  from cadical's DRAT proof. `discharge.py` re-verifies that
  certificate independently with `cake_lpr`, a formally-verified
  (CakeML) checker from a different codebase than the pair that
  produced the proof — so a discharged certificate here is checked
  twice by unrelated implementations. Lineage: `cadical, drat-trim,
  cake_lpr`. 4-item corpus, 3 mutants, 5 certificate mutants (empty,
  garbage, wrong format, mismatched formula, truncated-before-the-
  empty-clause).

- **`dimacs-z3`** (solver) — the same decision, through z3's DIMACS
  front end. A wholly independent codebase (no shared lineage with
  cadical/drat-trim/cake_lpr), used to corroborate. No certificate
  capability (z3 -dimacs emits none), so its `all` results stay
  *claimed* — but two disjoint-lineage terminal results on the same
  question is what the kernel marks *corroborated*, independent of
  either one's grade.

- **`dimacs-pigeonhole`** (solver) — a new decision procedure, not a
  search. It recognizes a *generalized* pigeonhole shape directly in
  the clause set: P disjoint all-positive clauses that partition every
  variable ("this pigeon is in one of these holes") together with H
  disjoint groups over the *same* variable universe, each an explicit
  pairwise-NAND clique ("at most one pigeon in this hole"). Counting
  true variables through each partition gives T ≥ P and T ≤ H; P > H
  is a direct contradiction — polynomial in the input, independent of
  how large a resolution refutation of the same fact would be (which
  is exponential, by Haken's theorem, for the plain CDCL/resolution
  solvers above). `discharge.py` re-derives the pigeon side itself
  from the raw CNF (a deterministic scan, nothing to trust) and checks
  the supplied hole partition's cliques against the actual NAND
  clauses — it never calls the union-find search that found the
  partition, only verifies what it claims. 4-item corpus (including a
  P=H case that must be correctly *abstained* on, since equal
  pigeons/holes is satisfiable), 2 mutants (unconditional UNSAT claim;
  an off-by-one `pigeons >= holes` bug caught by that same P=H case),
  5 certificate mutants (missing variable, overlapping groups, a
  non-clique grouping, a wrong hole count, a certificate for a
  different formula's variable range).

No translations or further languages were needed — every question
routes directly, `dimacs` → solver, in one hop.

## What the two maps say

**`dimacs-mixed`** — 5/5 terminal, frontier holds 0.

| question | best | grade |
|---|---|---|
| php1110-wall | all (bound inf) | certified +corroborated |
| php43-unsat | all (bound inf) | certified +corroborated |
| php54-unsat | all (bound inf) | certified +corroborated |
| rand-sat-a | witness (depth 20) | replayed +corroborated |
| rand-sat-b | witness (depth 24) | replayed +corroborated |

**`dimacs-harder`** — 5/5 terminal, frontier holds 0.

| question | best | grade |
|---|---|---|
| dense-unsat | all (bound inf) | certified +corroborated |
| php1211-hard | all (bound inf) | certified +corroborated |
| php65-unsat | all (bound inf) | certified +corroborated |
| rand-sat-c | witness (depth 30) | replayed +corroborated |
| rand-sat-d | witness (depth 40) | replayed +corroborated |

All 10 questions across both benchmarks are terminal, every result is
either *certified* (a universal whose certificate discharged against
the source program) or *replayed* (a witness re-run through the
interpreter), and all 10 are *corroborated* — reached by two
decision procedures with disjoint lineage agreeing on the same
verdict. No contradictions were recorded.

The two php-pigeonhole instances that give cadical and z3 real trouble
(`php1110-wall`: 11 pigeons/10 holes, `php1211-hard`: 12/11) are where
`dimacs-pigeonhole` matters: plain CDCL search on these needs a
resolution refutation that is exponential in the pigeon count (Haken
1985), so cadical alone exhausts a 20s wall budget on both and returns
an honest partial (`"cadical exhausted its budget without a
verdict"`) — that partial is still on record in the log. z3 turned
out to solve 11-pigeon within ~11s at that same budget but needed the
larger 60s budget to also close 12-pigeon; `dimacs-pigeonhole` solves
either in ~0.03s regardless of size, because it isn't searching a
proof tree at all — it's checking a closed-form combinatorial
argument. That's the shape the contract asks expansion to take:
*semantics first* — a new decision procedure over the existing
`dimacs` language closed two open questions with a certified result,
before reaching for any translation or new language.

## What remains open, and why

Nothing is open on either pinned benchmark; the frontier is empty on
both maps.

What's *not* built, and would be the natural next expansion:

- **A general resolution/DRAT-independent proof system for other
  hard shapes.** `dimacs-pigeonhole` only recognizes the specific
  counting pattern above. A formula that's hard for CDCL but isn't
  shaped like generalized pigeonhole (e.g. it needs the symmetry
  argument for a different combinatorial principle, or a
  cardinality/PB argument that doesn't reduce to disjoint cliques)
  would fall back to cadical/z3 alone and inherit their scaling
  limits. Nothing in the two pinned benchmarks currently exercises
  that gap, so it hasn't been built — reifying syntax or a second
  bespoke procedure for a case that isn't in front of me would be
  getting ahead of the evidence.
- **No translation pairs or additional languages.** Every question on
  both benchmarks is answerable by a direct `dimacs` → solver route;
  building a translation (e.g. to a graph-coloring or ILP language)
  wasn't needed to reach or expand the frontier here, so per the
  contract's semantics-first ordering it wasn't added speculatively.
- **z3's `all` results stay *claimed*, not certified** — z3's `-dimacs`
  mode doesn't emit a checkable unsat proof, so its contribution is
  corroboration only, never the certificate itself. If a stronger
  grade on the z3 route specifically were wanted, the next step would
  be extracting z3's unsat core / proof mode and writing a
  `discharge.py` against it — not attempted since `dimacs-cadical`
  and `dimacs-pigeonhole` already carry certified grades on every
  question that needs one.
