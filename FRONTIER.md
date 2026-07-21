# Frontier — the story: benchmarks in, a map of decidability-in-practice out

This document states the destination the rest of the repository is a
means to. [`ARCHITECTURE.md`](./ARCHITECTURE.md) defines the
instrument, [`POTENTIAL.md`](./POTENTIAL.md) names its ceiling; this
document names its **use**. The current vision — deterministic,
fidelity-graded translations with quantified trust — is not the end.
It is the instrument-grade foundation for the end:

> Present hurdy-gurdy **any benchmark whose questions reduce to
> decision procedures**. The platform eventually learns **all ways
> feasible in practice** to solve the benchmark — and saves, as
> structured evidence, **everything not yet solvable, and why**.

Run at that ambition, hurdy-gurdy is an **LLM-driven explorer of the
frontier of reducible decidability in practice**: benchmarks in; the
solved region out, with every feasible solution path enumerated,
cost-profiled, and trust-graded; and the frontier itself drawn by
evidence — every open point labeled with the obstacle that keeps it
open and the generation target that would close it, or the
proof-shaped reason none can.

## 1. Saturation, defined per benchmark

A benchmark `B` is a pinned set of questions `(p, φ)` over programs in
registered source languages (ingestion per
[`BENCHMARKS.md`](./BENCHMARKS.md) §4 — pinned snapshot, recorded
provenance). At graph `G`, `B` is **saturated** when every question in
`B` sits in exactly one of two terminal states:

- **Solved, all ways.** Some route answers it within budget — and the
  answer carries the full option set: every feasible route, its
  measured cost profile ([`ROUTES.md`](./ROUTES.md) §7), its assurance
  class, its branch corroboration. The books name no remaining
  generation target *inside the known set*: no registerable pair over
  the known target languages and solvers would add a new feasible way,
  a cheaper way (**cost**), or a more trusted way (**trust**).
- **Open, on the books.** A demand record
  ([`gurdy/core/ledger.py`](./gurdy/core/ledger.py)) names the
  question verbatim, its first failing obstacle, and a generation
  target that lies *outside* the known set: a reasoning language that
  does not exist yet (**shape**), decision cost no registered
  reduction tames (**cost**), a semantic anchor the world has not
  supplied (**trust**) — or, the outermost wall, outside the closure
  of sound reductions entirely ([`POTENTIAL.md`](./POTENTIAL.md) §5,
  where no target is honest to name). A cost target has a *memory*:
  the player reports the registered reductions it already played and
  spent on the question (`why_not(..., spent_reductions=…)`), and once
  every registered dial is spent the target advances past them — to
  the shape's charted native procedure family (an unbounded engine
  behind a solver brief, [`SYNTHESIS.md`](./SYNTHESIS.md) §3) or, off
  the chart, to the demand for a reduction nobody has designed. A
  played-and-spent dial never re-enters the target: the map moves
  when the books say the known set's answer was tried and found
  wanting.

Three properties make saturation a real terminal state rather than a
slogan:

1. **It is approached monotonically and never lost.** The ratchet
   ([`BENCHMARKS.md`](./BENCHMARKS.md) §5) means each loop iteration
   can only grow the solved region; a saturated benchmark is re-opened
   only by good news — a new solver, a new anchor, a new logic — and
   the terminal books say exactly where to plug the good news in.
2. **It is mechanically detectable.** Saturation is a fixpoint of the
   demand board: `gurdy recommendations`, restricted to `B`'s
   questions, stops naming targets in the known set. No judgment call
   decides when the experiment is over; the books do.
3. **It is honest.** `unknown` / `resource-out` are first-class
   verdicts, caps are declared, and a question parked on the books is
   not a failure hidden — it is the product. The open set, with its
   obstacle partition and evidence counts, is worth as much as the
   solved set.

### 1.1 The mechanics — records, the derivation, the fixpoint check

Saturation is executable, and this is its contract (implemented by
[`gurdy/core/question.py`](./gurdy/core/question.py),
[`gurdy/core/benchmark.py`](./gurdy/core/benchmark.py),
[`gurdy/core/frontier.py`](./gurdy/core/frontier.py); run as
`gurdy saturation`):

- **The question.** One type carries `(p, φ)`: source language, the
  observables φ reads, its shape, the asker's assurance floor, and —
  new with benchmarks — the program's identity. Its ledger dict (only
  the fields present) is its identity; questions without a program
  hash exactly as before.
- **The records.** A demand record is the question verbatim, the
  first failing obstacle, the generation target, the `origin`
  (`organic` / `campaign` / `scout`), and — when asked from a
  benchmark — the `suite` tag. Suite is a record field like origin,
  never part of question identity: the same question from two suites
  is one question, filed twice. Nothing else is stored: the §1.5
  fingerprints of the plan are *derived* views — the required
  contract joins over recorded questions, and cost curves live on the
  ledger's cost side already. One ledger, no parallel currencies.
- **The benchmark.** A pinned suite object: a `suite` id, a source
  (`github:owner/repo@commit` or a local directory), and instances
  each carrying a path, a sha256, a question, and an optional
  expected label. Fetch is streamed-with-pin
  ([`BENCHMARKS.md`](./BENCHMARKS.md) §4): cache, verify, and a hash
  mismatch is an error, never a substitution.
- **The derivation.** A pure function of (demand records, registry):
  records group by target signature; each group becomes a **frontier
  object** — the target's kind and detail, the **required contract**
  (union of cited observables, the highest cited floor, the histogram
  of spent verdicts), the evidence (distinct questions, origins,
  suites, first/last seen), and its classification against the known
  set: `pair` / `wider-projection` / `reduction` /
  `declare-provenance` targets lie **inside** (registerable today —
  with any registered-but-unbuilt matches named); a
  `native-procedure` target is classified by the atlas
  ([`SYNTHESIS.md`](./SYNTHESIS.md) §3 — charted lies inside,
  instantiation; uncharted outside, discovery); while
  `reasoning-language` and `independent-pair` targets lie **outside**
  (a hypothetical language; an artifact the world has not supplied),
  and a question may honestly carry **no** target at all
  ([`POTENTIAL.md`](./POTENTIAL.md) §5). Derived, never stored; no
  write path exists.
- **The fixpoint check.** `gurdy saturation <benchmark> [--ledger L]`
  re-diagnoses every question of the benchmark statically, merges the
  suite's recorded demands from the current iteration's books (a
  **cost** demand carries a spent verdict a static re-ask cannot
  reproduce, so it stands for the iteration; the loop owns freshness —
  pass the iteration's ledger, not all history), and partitions: **solved** (statics pass, no
  standing dynamic demand), **open with an in-set target**, **open on
  the frontier**. The benchmark is **saturated** iff the second class
  is empty — the tier-2 emptiness of the plan's F5 — and the exit
  code says so. The way-census side of "solved, all ways" is the
  report's job (plan C5), not the fixpoint's.

## 2. "All ways", "feasible", "in practice" — each word load-bearing

- **All ways** is plural on purpose. The loop is two loops
  ([`POTENTIAL.md`](./POTENTIAL.md) §3): the capability loop finds *a*
  way; the trust loop finds *independent* ways, because a second route
  answers no new question but manufactures fidelity
  ([`ROUTES.md`](./ROUTES.md) §4). A saturated benchmark has exhausted
  both — every question is answered along every feasible route, and
  the trust of each answer has been pushed to the anchor supply's
  limit (`gurdy trust-options`; saturation is a verdict on the trust
  axis too, [`gurdy/core/trust.py`](./gurdy/core/trust.py)).
- **Feasible** means within declared budgets. `resource-out` is a
  permanent verdict class, not a transitional one; a way that exceeds
  every budget is not a way, and the demand it records (**cost**) is
  the standing order for the abstraction pair or solver advance that
  would make it one.
- **In practice** means measured, never asymptotic. The books' cost
  side profiles every hop per runner class
  ([`ROUTES.md`](./ROUTES.md) §7); dominance is computed only between
  fully measured routes; an unmeasured route reads `unmeasured`, never
  cheap. The frontier of practice moves with solvers and abstraction
  pairs, and the map records where it stood, dated and pinned.

## 3. The current vision is exactly the means

Every load-bearing feature of the platform, read from the story's end,
is a requirement of frontier cartography:

| The platform has… | because a trustworthy frontier map needs… |
|---|---|
| determinism + the commuting square ([`ARCHITECTURE.md`](./ARCHITECTURE.md)) | a map its untrusted explorer cannot falsify |
| pinned benchmark ingestion ([`BENCHMARKS.md`](./BENCHMARKS.md) §4) | "presented any benchmark" as a literal input mode |
| routes, branches, fidelity accounting ([`ROUTES.md`](./ROUTES.md)) | "all ways" — capability and trust separately purchasable |
| the five-obstacle diagnosis (`gurdy why-not`) | the frontier's local gradient: what would extend the map *here* |
| the books + `gurdy recommendations` ([`AGENTS.md`](./AGENTS.md) §1) | "everything not yet solvable, saved" — deduplicated, origin-tagged evidence |
| the builder pipeline + the gate ([`SCALING.md`](./SCALING.md)) | throughput: the loop must run faster than a human's hands |
| directional pairs + CEGAR ([`POTENTIAL.md`](./POTENTIAL.md) §6) | the cost frontier, which is where "in practice" actually lives |
| the trust advisor + anchor census ([`gurdy/core/trust.py`](./gurdy/core/trust.py)) | the honest end of the trust axis, stated as saturation, not spin |
| the stated limits ([`POTENTIAL.md`](./POTENTIAL.md) §5, §7) | the line between *open in practice* and *open in principle*, drawn, not blurred |

None of these was designed as a feature of one more verification tool.
Each is what it takes for the maps of §1 to be worth keeping — which
is the sense in which the current vision is the means and the map is
the end.

## 4. The two production lanes

The loop's throughput is pair production, and pairs are produced in
exactly two lanes. (A third lane — solver capabilities: decision
procedures the books demand (`native-procedure`), a dedicated gate
admits, and a human registers — is tooled, shadow-first, in
[`SYNTHESIS.md`](./SYNTHESIS.md); no autonomy rung exists for it, so
under every mandate it escalates.)

### 4.1 By others, through PRs we check — landed

An external contributor's pair enters the platform exactly as a
builder agent's does, and the gate does not care about the
difference: the PR-native gate runs on every branch
([`SCALING.md`](./SCALING.md) §12.1 — coverage measured, determinism
twice-and-diffed, protected fields diff-rejected), untrusted
`translate`/`lift` grade behind the `PureOracle` sandbox seam (§12.2),
every touched pair clears the two-sided negative control (§12.3),
shared-layer edits classify into the additive/coordinated lanes
(§12.5), the merge queue orders and judges candidates in propose mode
(§12.6), and provenance is coordinator-attested, never self-reported
(§12.7). Green CI is designed to *mean* safe-to-merge; a human
approves the proposed plan. This lane requires no new work — it is the
[`SCALING.md`](./SCALING.md) pipeline, phases 1–7, as landed.

### 4.2 By us, autonomously — not done yet; the missing link is registration

Most of this lane also exists: `why_not` emits draft brief stubs, the
books recommend targets by evidence, and
[`tools/builder_dispatch.py`](./tools/builder_dispatch.py) already
automates the build side for partial-pair widening
([`SCALING.md`](./SCALING.md) §12.4, demonstrated on `evm-btor2`).
What does not exist is the closure of the loop
`demand → brief → registered → built → merged` at its one remaining
human point: **registration** ([`AGENTS.md`](./AGENTS.md) §1) — held
human deliberately, as the platform's scope valve.

The path forward that keeps the valve is the **scoped registration
mandate**: a human registers not a pair but a *region*. A mandate is
brief-shaped — it names the benchmark being saturated, the obstacle
classes in scope, the admissible source/target languages, and fixes
the protected fields' floors (projection, coverage targets, direction
policy) — and within it the coordinator may register demand-cited
briefs autonomously; anything outside escalates. Registration stays a
human act in the only sense that matters: the human writes the
mandate and can revoke it; what is delegated is its mechanical
instantiation, one evidence-cited brief at a time.

Autonomous registration must be *earned* exactly as autonomous merging
is ([`SCALING.md`](./SCALING.md) §12.8): a further rung on the same
ladder — **L4 mandate-registration** — graduated by the same shadow
discipline. While the queue sits below it, the coordinator records
which briefs it *would* have registered under the mandate beside those
the human actually registered; the rung is earned by a window of zero
false-go disagreements, and burned back down by any mandate-registered
brief the human later rejects on scope.

*Status: the shadow machinery is landed*
([`tools/mandate.py`](./tools/mandate.py); the L4 rung in
[`tools/autonomy.py`](./tools/autonomy.py)) — shadow mode is the only
mode implemented, and taking it up sharpened the design with the
**design line**: the mandate instantiates only briefs whose design is
*mechanical* (a widening of a named pair's projection; taking up an
already-registered brief). An in-scope target whose design needs a
creative act — which translator, from which spec — escalates even
inside the region: delegated instantiation is not delegated judgment.
Nothing registers until the window is earned *and* a human raises the
level, and no code path exists from the mandate to a write under
`pairs/`.

## 5. The key experiment: saturate a benchmark designed by others

The story implies its own decisive experiment, and the platform's
features are showcased by it strictly as a side effect — nothing is
demonstrated that the run does not need.

**The benchmark.** HWMCC — the hardware model-checking competition
corpus: designed by others, labeled with verdicts, native to the BTOR2
hub (no translation debt to pay before the loop starts), and its
pinned streamed-with-pin ingestion already exists
([`tools/abstraction_bench.py`](./tools/abstraction_bench.py) streams
a slice by commit and sha256, per [`BENCHMARKS.md`](./BENCHMARKS.md)
§4). SV-COMP is the natural second act — source-level C questions down
the full spine — but HWMCC is the honest first.

**The protocol** — the loop of [`POTENTIAL.md`](./POTENTIAL.md) §2,
run to the §1 fixpoint with the books on:

1. Pin the suite; establish ground truth where labels exist
   (bridge + native-checker agreement, witnesses replayed — the
   discipline of the player experiments).
2. Run the player over every task with `GURDY_LEDGER` set and
   `origin=campaign` — manufactured demand is displayed apart from
   organic demand by construction, so the experiment cannot launder
   its own probing into evidence.
3. What answers, answers with its way-census attached (routes, cost
   profiles, assurance, branch agreement). What does not lands on the
   books through `why_not`, first failing obstacle named.
4. `gurdy recommendations` → registration (human at first; the §4.2
   mandate when it exists) → builders → the gate → the merge queue.
5. Re-run. The ratchet makes progress monotone. Stop when the board
   over the benchmark names no target inside the known set — that
   board *is* the result.

**The deliverable — the saturation report:**

- the **curve**: answered fraction of the benchmark per loop
  iteration, monotone by the ratchet;
- **cost per answer** across iterations — falling is the accumulating
  instrument, measured ([`POTENTIAL.md`](./POTENTIAL.md) §7);
- per solved question, the **way-census**: every feasible route with
  profile, assurance, and corroboration;
- the **terminal board**, partitioned by obstacle —
  needs-a-new-logic (shape) / needs-cheaper-decision (cost) /
  needs-a-new-anchor (trust) / outside-the-closure — the domain's
  future-work section, machine-generated, each entry carrying its
  distinct-question evidence count.

**Showcased as a side effect,** because the run needs each one:
pinned ingestion ([`BENCHMARKS.md`](./BENCHMARKS.md) §4), routes and
branch agreement ([`ROUTES.md`](./ROUTES.md) §4–6), solver and
certificate discipline ([`SOLVERS.md`](./SOLVERS.md)), the diagnosis
and the books ([`INTERFACE.md`](./INTERFACE.md) §2A), the builder
pipeline and the gate ([`SCALING.md`](./SCALING.md)), abstraction and
CEGAR on the cost-bound instances ([`POTENTIAL.md`](./POTENTIAL.md)
§6), and the trust census against the anchor supply
([`gurdy/core/trust.py`](./gurdy/core/trust.py)).

**Pre-registered honesty.** The curve may plateau on cost; the plateau
is a finding — the measured practice-frontier of the domain — not a
failure. Caps are declared per [`BENCHMARKS.md`](./BENCHMARKS.md) §6
and ride in the provenance; `unknown`/`resource-out` are counted,
never hidden; campaign origin stays displayed apart, end to end.

## 6. What hurdy-gurdy becomes

[`POTENTIAL.md`](./POTENTIAL.md) ends by handing the player a luthier.
This document says what the luthier is for. Run benchmark after
benchmark through the loop and the platform stops being a library of
translations and becomes a **cartographer**: each saturation deposits
a map — the region of the benchmark decidable in practice, every path
through it enumerated and priced, and a surveyed frontier where every
open question carries the exact instrument that would move it and what
that instrument costs, or the stated reason no instrument can. The
maps compound, because pairs are shared: the next benchmark starts on
richer ground than the last. The frontier is redrawn by every solver,
anchor, and logic the world supplies, and the terminal books say
exactly where each piece of good news plugs in. And the current
vision — determinism, squares, gates, books — is precisely what makes
the maps worth trusting.

The vision is the means. The map is the end.
