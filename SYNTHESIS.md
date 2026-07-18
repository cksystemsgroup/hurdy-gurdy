# Synthesis — growing decision procedures from the books

This document says how the platform comes to *demand, admit, and
falsify* decision procedures it does not yet have — including
procedures written by LLM builders. [`FRONTIER.md`](./FRONTIER.md)
ends with a saturated benchmark's terminal board; this document reads
that board as the specification of the next solver. It is a design
document in the sense of [`FRONTIER-PLAN.md`](./FRONTIER-PLAN.md):
the mechanisms below are named work, not landed code, and the Status
notes say which is which.

## 1. The claim, and the principle that makes it safe

A saturated benchmark leaves behind exactly the evidence a procedure
search needs: shape-blocked demands carry the blocked φs verbatim
([`gurdy/core/whynot.py`](./gurdy/core/whynot.py), obstacle 3),
cost-blocked demands carry spent verdicts and measured per-engine
decide profiles (obstacle 4), and the solved region carries a
way-census of corroborated answers
([`gurdy/core/frontier.py`](./gurdy/core/frontier.py)). Turning that
evidence into a *new solver* is a generation problem the platform is
architecturally pre-adapted for, because of one standing principle:

> **Solvers are never trusted — only their answers are checked.**
> A candidate procedure need not be proven correct. It needs to emit
> certificates a deterministic checker validates, and its
> incompleteness is absorbed by the verdict vocabulary: a wrong
> answer dies at the certificate check, a missing answer is
> `unknown`, a divergent run is `resource-out` under declared
> budgets. Nothing about admitting an untrusted procedure weakens
> what an answer means.

This is the same separation that lets untrusted LLM agents build
translation pairs ([`ARCHITECTURE.md`](./ARCHITECTURE.md)): the
generator sits outside the trusted base, the gate admits only what
survives checking. Synthesis extends it from edges (pairs) to node
capabilities (procedures) — and §6 states the one place the
discipline gets *stricter*, not looser.

## 2. What the platform already supplies

Four seams exist today and are load-bearing for everything below:

- **The backend duck-type.**
  [`gurdy/core/solver.py`](./gurdy/core/solver.py): a solver is `id`
  plus `decide(artifact, directive) → Result` over the four-verdict
  vocabulary. `Z3SmtBackend` shows an in-process Python backend is a
  first-class citizen — a synthesized procedure's natural form.
- **One-line registration.**
  [`gurdy/solvers/inventory.py`](./gurdy/solvers/inventory.py): "a
  new engine is one entry here plus a backend class." A registered
  engine automatically joins multi-engine corroboration
  ([`gurdy/solvers/proved.py`](./gurdy/solvers/proved.py)).
- **Deterministic-side checking.** Witness replay through the shared
  interpreter for `reachable`
  ([`gurdy/languages/btor2/witness.py`](./gurdy/languages/btor2/witness.py));
  the bit-blast → DRAT/LRAT → verified-checker chain with an explicit
  TCB record for `unsat` ([`SOLVERS.md`](./SOLVERS.md) §§4–6,
  [`gurdy/solvers/proved.py`](./gurdy/solvers/proved.py)).
- **The evidence pipeline.** `why_not` demand records, the ledger's
  cost side, the scout's measured encoding blowup, and the fragment
  atlas — landed as [`gurdy/core/atlas.py`](./gurdy/core/atlas.py)
  ([`FRONTIER-PLAN.md`](./FRONTIER-PLAN.md) O1) — together contain
  everything a procedure brief must cite.

## 3. The demand: a `native-procedure` target kind

The books cannot currently ask for a solver. The target taxonomy is
pair- and language-shaped — in-set `pair` / `wider-projection` /
`reduction` / `declare-provenance`, out-set `reasoning-language` /
`independent-pair` ([`gurdy/core/frontier.py`](./gurdy/core/frontier.py))
— so a missing decision procedure is folded into `reasoning-language`
(a whole new language plus bridge, far heavier than what is needed)
or recorded nowhere: the scout deliberately writes no demand
([`tools/scout.py`](./tools/scout.py)). A new solver is only ever
exogenous good news ([`FRONTIER.md`](./FRONTIER.md) §1).

The fix is a **`native-procedure` generation target** — the first
inhabitant of the language-attached *capabilities* tier that
[`FRONTIER-PLAN.md`](./FRONTIER-PLAN.md) already derives beside
edge-shaped pairs. It is emitted from exactly two places:

- **Obstacle 3 (shape),** when the atlas locates the blocked shape's
  native procedure family but no registered hub declares the shape —
  the demand names the family and the hub it should attach to,
  beside the existing `reasoning-language` alternative.
- **The scout (cost),** when every prototyped embedding explodes —
  the demand carries the measured blowup as its justification,
  which is the brief's evidence section writing itself.

Classification against the known set falls out of the atlas: a
**charted** family (setting, procedure family, canonical citations
known) lies *inside* — registerable today, the instantiation case —
while an **uncharted** shape lies *outside*: genuine discovery, on
the frontier with the honest label. The atlas thereby stops being
reference data only and becomes load-bearing for the in/out line,
protected like every instrument the gate trusts.

*Status: landed. `why_not`'s shape obstacle consults the atlas: a
charted shape emits `native-procedure` (family, `attach_to_any_of`
the hubs the program reaches, the crossing in the note), an uncharted
one keeps the honest `reasoning-language` demand. The scout files its
one permitted demand — question supplied and every embedding
explosive → `native-procedure`, obstacle `cost`, origin `scout`,
justified by the scout rows on the books. The frontier derivation
classifies the kind by atlas chartedness — so a benchmark blocked on
a charted shape is honestly *not* saturated (the board names the
family to instantiate), while an uncharted one still parks on the
frontier. Under a mandate the kind escalates by construction:
`mechanical_design` knows no procedure lane, so delegated
instantiation never touches it.*

## 4. The contract: solver briefs

Pairs enter through a one-page brief a human registers
([`AGENTS.md`](./AGENTS.md) §1). Solvers today enter through a
language README with no per-solver contract — tolerable while every
engine is a pinned community binary, untenable the day a builder
submits one. A **solver brief** mirrors the pair brief and declares:

- **The attached language and the declared shapes.** Declared against
  the shape taxonomy of [`SOLVERS.md`](./SOLVERS.md) §9: exact shared
  tokens, each declaration a claim with per-verdict checker
  obligations, located in the atlas beyond the declared set.
- **The budget schema.** Declared limits (wall-clock, memory,
  bound), not the ad-hoc `directive` keys and hardcoded timeouts of
  the current adapters.
- **The certificate obligation, per declared shape × verdict.**
  Either a witness kind an existing deterministic checker validates,
  a new checker shipped alongside (entering the
  [`SOLVERS.md`](./SOLVERS.md) §6 TCB ladder at its honest rung), or
  an explicit `uncheckable` — which caps the engine's assurance
  contribution and closes the `unsupported` escape hatch that today
  lets a verdict go silently uncheckable.
- **The lineage declaration.** Which codebases and reference
  semantics the engine derives from. Corroboration currently counts
  codebases naively (`proved.corroborate`; the boolector/bitwuzla
  shared ancestry is a source comment, not a guard), and
  [`gurdy/core/trust.py`](./gurdy/core/trust.py) reasons over pair
  anchors only. For a synthesized engine, lineage must include the
  reference semantics and any solver corpus it was synthesized
  *from* — otherwise agreement between a teacher and its student
  launders itself into independence.

Registration stays human, exactly where the design line already
draws it ([`FRONTIER.md`](./FRONTIER.md) §4.2): choosing the
algorithm family is the creative act; what is delegated is the build
and the checking, never the judgment.

*Status: landed — [`gurdy/solvers/brief.py`](./gurdy/solvers/brief.py)
(the `SolverBrief` contract, validation, the assurance ceiling, and
registered briefs for every shipped engine, retroactively), the
`lineage` field on every backend, and lineage-aware corroboration in
[`gurdy/solvers/proved.py`](./gurdy/solvers/proved.py): `checked` now
requires agreement across disjoint declared lineages, so
boolector+bitwuzla alone reads `reproducible` with the note on the
record — the code trued to what SOLVERS.md §6 always claimed. Docs:
SOLVERS.md §2.1, AGENTS.md §1, REGISTRY.md.*

## 5. The gate: how a candidate procedure is falsified

The §12 gate ([`SCALING.md`](./SCALING.md)) checks pairs — coverage,
twice-and-diff determinism, two-sided negative controls, the
PureOracle sandbox — and none of it touches solver artifacts. A
candidate procedure is admitted through a **solver gate** with four
checks, each an analogue of one the pairs already clear:

1. **Census replay** (the analogue of the ratchet's regression
   corpus). Re-decide the in-scope slice of the solved region —
   pinned questions, corroborated verdicts, way-census on file —
   with the candidate. Any disagreement with a corroborated answer
   fails admission outright; agreements are admission evidence *and*
   immediately purchase corroboration for every replayed question.
   The corpus exists (`iterations.jsonl`, the census in
   [`tools/saturation_report.py`](./tools/saturation_report.py));
   what is missing is only the harness that points it at an engine.
2. **Canaries and verdict-flip mutants** (the analogue of the
   two-sided negative control). A known-reachable canary must read
   reachable — the pattern exists in miniature as `_CANARY` and
   `_exhaustion_trustworthy` in
   [`gurdy/solvers/native_btor2.py`](./gurdy/solvers/native_btor2.py)
   — and a seeded mutation flipping a known verdict (a bad made
   reachable) must flip the candidate's answer. A candidate that
   cannot be made to fail is not checked, it is unfalsifiable.
3. **Certificate discipline** (already stated for `proved`-tier
   encodings, [`SCALING.md`](./SCALING.md) §12): a bogus certificate
   must fail its checker; success lines parse exactly; the checker
   is a different codebase from the producer.
4. **Budget honesty.** The candidate runs under its declared limits;
   `resource-out` at the gate is a recorded cost profile, not a
   failure — the gate admits sound-and-slow, and the books price it.

*Status: landed — [`tools/solver_gate.py`](./tools/solver_gate.py),
tested in [`tests/test_solver_gate.py`](./tests/test_solver_gate.py).
The candidate is a decider `(btor2_text, k) → verdict`; the shipped
census is the constrained-systems corpus (both polarities,
by-construction truth), with the saturation census as the intended
corpus at scale; adapters gate the registered families (the native
composite, the bridge with any inventory engine), and `runs ≥ 2` is
the opt-in twice-and-diff of §6. It is the admission check the next
hand-added engine (AVR is the named candidate,
[`SOLVERS.md`](./SOLVERS.md) §10) should clear too.*

## 6. Where the discipline tightens: synthesized means more checkable

External engines are exempt from the determinism gate because they
are admitted as the platform's one non-deterministic component
([`SOLVERS.md`](./SOLVERS.md) §1). A synthesized pure-Python
procedure has no such excuse, and the gate should not grant it one:

- it runs under the same **PureOracle sandbox seam** as untrusted
  `translate`/`lift` ([`SCALING.md`](./SCALING.md) §12.2),
- it is **twice-and-diffed** like any pair,
- and it clears the full solver gate of §5 besides.

The inversion is the point: the newest, least-trusted authors
produce the most-checkable artifacts. Admitting LLM-written
procedures does not dilute what green means — the synthesis lane is
gated strictly harder than the pinned binaries the platform already
believes.

## 7. The lane: from terminal board to backend class

The build side composes existing machinery, one lane beside pair
production ([`FRONTIER.md`](./FRONTIER.md) §4):

1. **Extraction.** A fourth operator joins the design-oracle table
   ([`FRONTIER-PLAN.md`](./FRONTIER-PLAN.md) §"far side"): a
   `native-procedure` frontier object becomes a **procedure-synthesis
   brief** — the fragment hull of its citing φs, the atlas location
   and family, the required contract (shapes, floor, budget
   envelope), the census slice that will falsify the build, and the
   certificate obligation.
2. **Registration.** A human admits the design (§4). Under a mandate
   ([`tools/mandate.py`](./tools/mandate.py)) this stays on the
   creative side of the design line indefinitely: `mechanical_design`
   returns nothing for procedure briefs until a dedicated rung is
   earned, and it starts, like every delegated judgment, in shadow.
3. **Build.** A builder lane beside
   [`tools/builder_dispatch.py`](./tools/builder_dispatch.py)'s
   pair-widening: the deliverable is a backend class under
   `gurdy/solvers/`, its inventory entry, and its certificate
   emitter; `self_verify` for this lane *is* the solver gate.
4. **Admission.** The gate of §5, the ratchet, the merge queue —
   unchanged. A landed procedure closes its citing demands the same
   way a landed pair does, and the census it replayed at admission
   is corroboration already banked.

*Status: landed, shadow-first —
[`tools/procedure_dispatch.py`](./tools/procedure_dispatch.py): the
work list split by atlas chartedness (uncharted is listed apart and
never worked), the fragment hull, the markdown work item, the draft
`SolverBrief` that deliberately fails validation until a human
completes it (the write line, in type form), and `self_verify` =
brief validation + the solver gate at `runs=2`. The lane's reference
inhabitant is real:
[`gurdy/solvers/enum_btor2.py`](./gurdy/solvers/enum_btor2.py),
exhaustive bounded enumeration through the shared interpreter —
sound and complete within its declared path budget, `resource-out`
beyond it — registered in the brief table and admitted through the
gate end to end with no external binaries. What deliberately does
not exist: an autonomy rung — `mechanical_design` knows no procedure
design, so the kind escalates under every mandate until a human
builds and earns that rung.*

## 8. Honest limits, pre-registered

- **The corroboration bootstrap.** The first procedure for an
  uncharted fragment has no independent route to agree with beyond
  the census overlap; off-overlap its answers saturate at the
  certificate-checked rung until an independent engine or anchor
  exists — and that residue is itself a well-formed
  `independent-pair`-style demand, on the books, not hidden.
- **Hull overfitting.** A fragment generalized from one benchmark's
  blocked φs may be a benchmark-shaped procedure of no transfer
  value. The compounding of maps is the audit: the next benchmark's
  board shows whether the fragment is ever cited again, and a
  procedure nobody cites is shelf inventory, honestly priced.
- **Base rates.** Most demand closes cheaper: the atlas's known
  crossings are classical reductions — pairs, the platform's
  existing currency. The realistic yield is instantiation of charted
  families first, discovery rare — and the books' job is precisely
  to say when nothing cheaper will do.

## 9. Build order

1. Write the shape taxonomy and fix the dangling "SOLVERS.md §9"
   references (small, overdue, independent of everything else).
   *Landed: the taxonomy is [`SOLVERS.md`](./SOLVERS.md) §9.*
2. `tools/solver_gate.py` — census replay, canaries, verdict-flip
   mutants (useful for AVR before any synthesis exists).
   *Landed: the gate of §5, with the z3 bridge admitted through it
   end to end.*
3. The `native-procedure` target kind through `whynot` / `scout` →
   ledger → `frontier`, with in/out classification by atlas
   chartedness (makes the atlas load-bearing).
   *Landed: the kind of §3, the atlas drawing the in/out line, and
   the saturation semantics that follow — charted shape demands
   block the fixpoint honestly.*
4. Solver briefs, the certificate obligation, the lineage field, and
   the doc changes in SOLVERS.md / AGENTS.md / REGISTRY.md.
   *Landed: the contract of §4, with corroboration made
   lineage-aware.*
5. The builder lane, shadow-first, behind the same autonomy ladder
   as every other delegated act.
   *Landed: the lane of §7, with `enum-btor2` as its first
   inhabitant — hand-built to the lane's own work-item shape and
   gate-admitted. The rung stays unbuilt on purpose.*

Books first, gate second, generator last: solver synthesis becomes
*expressible and falsifiable* before any LLM writes a line of
procedure code. That ordering is this document's one non-negotiable.
