# Summary — domain `c`

## What was built

**Language `c`** (`registry/c/`) — a from-scratch, pure-Python deterministic
interpreter for a small C subset: `int`-only variables, `if`/`else`,
`for`/`while`, `assert`, the usual expression grammar (arithmetic, bitwise,
shifts, comparisons, `&&`/`||` with real short-circuiting, `?:`), and
`nondet_int()` reading from a supplied input stream. All arithmetic is
32-bit two's-complement with C's truncating (toward-zero) `/` and `%`,
matching real `gcc`/`cbmc` semantics rather than Python's floor semantics.
Observables: `violation` (did an `assert` fail) and `depth` (loop
iterations actually executed — the interpreter's own notion of how deep a
witness reaches). 10 vectors and 6 mutants (no-wraparound, Python-native
div/mod, no-short-circuit, bitwise-as-logical, no-depth-counting, inverted
assert) — every mutant fails at least one vector.

**Three independent solver pairs, all `c → violation`, no translation hops
needed** (both benchmarks only ask direct C safety questions):

- **`c-cbmc`** (lineage `cbmc`) — shells out to the real `cbmc`, with
  `--no-standard-checks` so only the user's own `assert` decides
  `violation` (not cbmc's own overflow/UB checks). Searches a *fixed*,
  wall-budget-derived doubling schedule of unwind bounds (0, 1, 2, 4, …) —
  fixed rather than time-adaptive so that determinism (every result is run
  twice and byte-compared) doesn't depend on machine jitter. A witness is
  cbmc's counterexample trace; a full proof is an unwind bound at which
  cbmc's own unwinding-assertion holds. Certificates (`{"unwind": k,
  "complete": bool}`) are independently re-verified by `discharge.py`
  re-running cbmc fresh at exactly that bound.

- **`c-z3bmc`** (lineage `z3`) — a second, independently-written front end
  (`czlib.py`: its own lexer/parser) feeding a Z3 bitvector symbolic
  executor, not cbmc's. Loops are unrolled with explicit state-freezing
  (`ite`-merged) up to a bound, with a "residual" formula standing in for
  cbmc's unwinding assertion (SAT residual ⇒ the bound wasn't enough;
  UNSAT ⇒ a full proof). This is genuinely independent of `c-cbmc`: it
  caught real bugs cbmc's approach can't (see below) and vice versa. One
  correctness bug surfaced and got fixed during construction: block-scoped
  variables (an `int y` declared inside an `if`) were leaking into the
  `ite`-merged outer environment as `None`, and — more importantly — code
  *after* a loop was being evaluated against the frozen, possibly-not-yet-
  terminated loop state instead of being gated by "the loop actually
  exited within the bound," which manufactured false violations on
  programs that hadn't unrolled far enough. Fixed by threading `(env, pc)`
  pairs through the executor so post-loop code is only reachable under
  `pc AND NOT(residual)`. A second lesson, empirical rather than logical:
  even with a fixed random seed, Z3's own wall-clock time for the *same*
  formula varied 13s–23s at 512 unrolled iterations on this machine — real
  search-time variance, not timeout-edge jitter. The bound schedule is
  capped at 256 for this reason (measured stable at ~1–2s), rather than
  pushed further and risking a nondeterministic byte-compare.

- **`c-loopsum`** (lineage `z3` + `loop-summarization`) — the expand-phase
  addition: a genuinely different decision procedure, not another
  unroller. For a single loop of the shape `for (int i = INIT; i < BOUND;
  i++) { VAR += LIT; ... }` guarded by an enclosing `if` that gives `BOUND`
  a literal upper bound, it derives the exact closed form `VAR_exit =
  VAR_init + LIT * k` instead of unrolling, checks that closed form can't
  overflow 32 bits across the whole reachable range of `k`, substitutes it
  into whatever comes after the loop, and asks Z3 once whether that's
  still safe. Trip count is irrelevant to its cost — proving `bigloop.c`
  (up to 60000 iterations) costs the same ~0.1s as `accum.c` (up to 30).
  It declines (honest `partial`, naming which structural requirement
  failed) on anything outside this shape — non-literal deltas
  (`loopv.c`'s `s += i`), non-affine bodies, unguarded loops, nested loops
  — falling back to the unrollers. `discharge.py` re-derives the pattern
  from source independently (doesn't trust the certificate's own numbers)
  and rejects any certificate whose claimed `ival`/`bound_lit`/`deltas`/
  `inits` don't match what's actually in the program.

## What the two maps say

Both benchmarks are now **fully terminal — 10/10 questions answered**,
every one `certified` or `replayed` (no result rests on an undischarged
claim), **8 of 10 corroborated** by two solver families with disjoint
lineage (`cbmc` vs `z3`) agreeing independently.

The two questions that *aren't* corroborated are the interesting ones —
each is exactly the case where one procedure wins and the others
genuinely can't follow:

- **`mulcomm-safe`** (`x*y == y*x` for all `int`) — `c-cbmc` times out
  past 60s per attempt bit-blasting a general multiplication identity
  (the benchmark's own comment calls this out: "bit-blasting groans").
  `c-z3bmc` discharges it in 0.005s because word-level bitvector
  multiplication is commutative at the theory level, no bit-blasting
  needed for *this* structure.
- **`bigloop-safe`** (`s += 3` for up to 60000 iterations, then `s % 3 ==
  0`) — reached the frontier first as an honest, certified-but-capped
  `all(bound=1024)` (cbmc) / `all(bound=256)` (z3bmc): both unrollers
  proved safety up to their bound and openly said they couldn't go
  further without unrolling all 60000 iterations, which timed at
  quadratic-ish cost (~11s at 1000, extrapolating to hours at 60000).
  Expanded to a full, certified `all(bound=inf)` via `c-loopsum`'s closed
  form — closing what was the one open item in `c-loops/frontier.md`.

## What remains open, and why it would be hard

Nothing is open in `c-straightline` or `c-loops` as pinned. Scoped
honestly, though:

- `c-loopsum`'s pattern is narrow by design (single affine-accumulator
  loop, literal bound, no nesting) — real programs with data-dependent
  deltas, multiple interacting loop variables, or nested loops fall
  straight back to unrolling, which is only as good as the bound it can
  reach in the wall budget. A genuine next step (not attempted here) is
  *relational* invariant inference (e.g. Houdini-style guess-and-check
  over a template lattice) to cover accumulators whose delta depends on
  another loop variable — `loopv.c`'s `s += i` is the smallest example in
  these two benchmarks that still needs full unrolling.
- The `c-cbmc` and `c-z3bmc` certificates are independently *re-verified*
  (the kernel never trusts `solve.py`'s own claim) but re-verified by
  re-running the *same* tool at the same bound — a stronger discharge
  would use a third, unrelated checker. `c-loopsum`'s discharge is
  stronger in this one respect: it re-derives the structural pattern from
  source rather than trusting the certificate's numbers at all.
- No translation pairs or additional languages were built. Both pinned
  benchmarks only ask direct `c → violation` questions, so per the
  contract's conjecture order (procedures before translations before
  languages) three solver pairs on one language fully answered what was
  asked; introducing a translation target would only be justified by a
  question this domain doesn't currently pose.
