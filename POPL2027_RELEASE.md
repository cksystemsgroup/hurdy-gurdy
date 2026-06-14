# Releasing hurdy-gurdy for POPL 2027 — overview

*Status: planning overview (recorded 2026-06-12; updated 2026-06-14 with the
completed v0.6 LLM evaluation). What it takes to release hurdy-gurdy in a form
that (a) demonstrates value to LLMs in programming, (b) is publishable at
POPL 2027, (c) normatively defines what a good — as opposed to bad — future
pair looks like, so that others can build pairs, and (d) states the
approach's reach into mathematics, physics, and chemistry.*

> **2026-06-14 update.** The load-bearing LLM experiment (§2) is **done** —
> a full §7-grade run: conditions A/B/C/D × two unrelated model families
> (Claude Haiku 4.5, Gemini 2.5 Flash) × 5 seeds × 28 tasks = 560 cells per
> model, plus a T4 lift-quality addendum, with the §7 determinism (104/104
> byte-identical) and leakage checks logged. Results in
> `bench/riscv-btor2/runs/v0.6-two-family/RESULTS.md`. The headline claim is
> now **sharper and more defensible than the original draft assumed** — see
> the rewritten §1(P3) and §2. The short version: condition D (a coached
> source-level verifier) *matches or beats* the pair on raw verdict accuracy,
> so the pair's defensible win is not "most accurate" but "sound-by-
> construction, lowest hallucination, witness at the right abstraction, and
> no case-specific prompt engineering."

## 0. The calendar is the first constraint

| Date | Event |
|---|---|
| **2026-07-09** | POPL 2027 paper submission deadline (≈ 4 weeks from now) |
| 2026-08-31 → 09-03 | Author response |
| 2026-10-05 | Notification |
| post-acceptance | Artifact evaluation |
| 2027-01-10 → 16 | Conference (Mexico City) |

Consequence: **the paper must be written from evidence that exists today or
can be produced in ≤ 2 weeks.** No new mechanisms, no new pairs before the
deadline. The repo's standing discipline ("demand-driven, build nothing
speculative") is also the right submission discipline. POPL is
double-anonymous; the selfie/rotor lineage and this repo must be handled
per the anonymization rules (anonymized artifact link, lineage phrased in
third person).

## 1. What the paper is — three candidate framings, one recommendation

POPL accepts principles, not products. The repo contains three publishable
layers; the recommendation is to lead with the first and let the others be
its application and evaluation.

**(P1) The formal core — pairs as commuting squares, and the algebra of
their composition.** Already on disk, scattered across
`DESIGN_generalized_pairs.md` (Appendix A), `DESIGN_pair_taxonomy.md`, and
`PAIRING.md`:

- A *pair* is a deterministic translation `T : L_in → L_out` between
  languages with formal semantics, packaged with interpreters `I_in`,
  `I_out` and a lift `L`, subject to the commutation contract
  `I_in(p) ≡_π L(I_out(T(p)))` — a refinement square; in
  institution-theoretic terms (Goguen–Burstall) the satisfaction condition
  of an institution morphism.
- *Chains* are squares pasted on a shared edge; the paste lemma gives
  chain-faithfulness = conjunction of hop-faithfulness, **with error
  localization** to the failing hop — something monolithic verifiers
  structurally cannot do.
- Three composition laws, each already implemented and testable:
  **determinism composes** (and one nondeterministic hop collapses the
  chain cache), **trust composes as the meet** over the tier order
  `transparent > checked > reproducible > trusted` with verifier-hop
  re-establishment (`ChainResult.verify` lifts `reproducible → checked` on
  CBMC agreement), and **loss composes as the union** of declared
  `Preservation.discards`.
- The two orthogonal classification axes (output kind:
  compile-pair vs reasoning-pair; predictability: the four trust tiers).

This is genuinely POPL-shaped: definitions, small theorems (commutation,
paste, meet/union laws), and a running mechanized witness for each.

**(P2) The architectural principle — the question compiler.** All
reasoning lives in the LLM; the substrate is deterministic, schema-
contracted, self-describing (annotation sidecar), and predictable. CEGAR,
portfolios, abstraction choices are *re-specifications by the client*, not
features of the tool. This is the design thesis that distinguishes
hurdy-gurdy from CBMC/ESBMC/SeaHorn and from "LLM calls Z3" agent papers.

**(P3) The empirical demonstration — value to LLMs in programming.**
**Done** (v0.6, `runs/v0.6-two-family/RESULTS.md`). A/B/C/D × two families
× 5 seeds. The result is more interesting than the original "the pair is
most accurate" hypothesis, because condition D — the steelman — partly
refutes that hypothesis and forces a sharper claim.

UB-wedge verdict accuracy (the C-UB-but-RV64-defined subset, 8 tasks ×
5 seeds = 40 cells/condition):

| Condition | Haiku 4.5 | Gemini 2.5 Flash |
|---|---|---|
| A — source-only | 80% | 72% |
| **B — pair** | **100%** | 80% |
| C — solver-only (hand-written) | 72% | 52% |
| D — LLM + CBMC | 98% | **95%** |

Three findings, all cross-family and 5-seed stable:

1. **C does not recover B** (the §3.C control): given the *same z3* but no
   pair, wedge accuracy is no better than source-only and C is the *worst*
   condition for hallucinations. So B's gain is the schema-pinned RV64
   lowering, not "access to a solver."
2. **D matches or beats B on raw verdict accuracy** — Gemini D 96% overall
   beats B 81%. But D's verdict strength is *bought with task-class-specific
   prompt coaching* (`condition_d.md` hand-codes the UB-vs-RV64 distinction);
   B's prompt has no such hint, the schema handles it structurally.
3. **B keeps the advantages D cannot:** lowest hallucination rate (B 0/1 of
   140 vs D 1/5, A 9/19, C 13/21); witness fidelity at the **RV64**
   abstraction (B 4–5/5 vs D's 1–4/5 — CBMC reports C-source positions, not
   machine PCs); and soundness *by construction* (D is a tool the LLM must
   talk out of its own UB false-positives).

So the defensible empirical claim is **not** "the pair is the most accurate
oracle." It is: *the pair delivers the verdict accuracy of a hand-coached
source-level verifier while being sound by construction, the calibration-
safest (near-zero confident errors), and grounded at the right abstraction —
without any task-specific prompt engineering.* The no-LLM oracle differentials
(CBMC/ESBMC 13–16/18 vs hurdy-gurdy 18/18; 8/8 wedges vs CBMC 0/8, iter-42/43)
remain as the underlying soundness story.

A separate **T4 lift-quality addendum** (the §9.7 rubric, blind-graded)
adds an honest *negative*: the pair does **not** improve source-level causal
explanation (LLMs do that well unaided), and for the weaker model condition
B can *degrade* it by crowding the `lift` field out of the tool loop. This
sharpens, not weakens, the claim — it locates the pair's value precisely in
verdict soundness + grounding, not in prose.

**Recommended title-level thesis:** *certified, deterministic,
compositional translation pairs are the right substrate for LLM reasoning
about programs* — formal core (P1) as the contribution, question-compiler
architecture (P2) as the design, LLM experiments (P3) as the evaluation. The
evaluation's punchline is **calibrated soundness without coaching**, not a
leaderboard win.

**Venue-fit risk, stated plainly.** POPL reviewers may read the LLM
evaluation as out of scope and want more theory; CAV/PLDI/OOPSLA reviewers
would want less. Mitigation: the paper must stand with the LLM results
*removed* (P1+P2+oracle-level differentials already make a paper), and the
LLM results then make it timely. If POPL rejects: CAV 2027 (≈ Jan 2027
deadline) and PLDI 2027 (≈ Nov 2026 deadline) are natural fallbacks with
notification timing that allows resubmission either way.

## 2. The LLM experiment — done (was the load-bearing gap)

`BENCHMARKING.md`'s experiment, the thing that makes the "value to LLMs"
claim defensible, has now been **run end-to-end at §7 grade**
(`runs/v0.6-two-family/`). What exists:

- **All four conditions A/B/C/D**, ≥ 5 seeds, **two unrelated families**
  (Claude Haiku 4.5 via the `claude` CLI + bench MCP server; Gemini 2.5
  Flash via paid Google AI Studio) — 560 cells/model, 0 unresolved errors,
  full per-`(condition, model, seed, task)` JSONL + lossless transcripts +
  schema-valid manifests. Exceeds the playbook's own ≥ 2 models / ≥ 5 seeds
  bar.
- **The §7 hygiene checks are logged in the manifests:** determinism =
  104/104 corpus tasks recompile byte-identical (`check_determinism.py`,
  now run live by `run_matrix.py` rather than a fabricated constant); a
  structured `leakage_check` records that SCHEMA.md/corpus are *plausibly*
  in training data but condition A is **not** handicapped (the schema
  documents the BTOR2 translation, not RV64 semantics), with the empirical
  anti-memorization argument (A is 72–91%, not ~100%, failing exactly on
  the wedges — the signature of reasoning from general C knowledge, not
  reciting labels).
- The corpus split that carries the story — the **8-task UB wedge battery**
  and the **13-task lowering-sensitive subset** — is reported separately
  from the easy tasks (where, honestly, the pair is neutral: Gemini B ≈ A on
  the full set).

Two follow-ons remain *optional* and would only strengthen the paper:

- **The predictability probe** — still unrun, and still the cheapest novel
  second result: a transparent pair's schema lets the LLM *predict the
  artifact bytes*; the prediction gap is a direct, scalable understanding
  metric, chain length its difficulty dial (`DESIGN_generalized_pairs.md`
  §2). A small instance (predict the BTOR2 for the wedge tasks, exact/near
  match per model) is worth a subsection.
- **Condition E** (propose-and-check with v1.1.0 partial bindings) — a
  negative E result is still reportable; not blocking.

What this cost, for budget planning of any extension: the full A/B/C/D ×
2 models × 5 seeds run was ~1100 LLM sessions; it ran over ~2 days,
sequential with capped parallelism, gated only by the Google free-tier
daily cap until a billable key was used (the standing RAM discipline held —
one instance in flight).

## 3. Defining good vs bad pairs — the normative contribution

For others to develop pairs, the criteria scattered across `PAIRING.md`,
`DESIGN_pair_taxonomy.md`, and `DESIGN_generalized_pairs.md` §4/§10 must be
consolidated into **one normative definition + a mechanical conformance
check**. This is both a paper section ("What is a well-formed pair") and a
release artifact.

**A good pair:**

1. **Commutes, checkably.** Ships interpreters and a declared projection
   `π`; the alignment oracle can test `I_in(p) ≡_π L(I_out(T(p)))` on any
   input. Translator bugs *are* commutation failures, localizable to
   (step, label).
2. **Is deterministic.** Byte-identical artifact from
   `(spec, source, schema_version)`; `recompile_and_diff` passes. No
   hidden state, no adaptivity, no environment leakage.
3. **Declares an honest trust tier.** `transparent` (schema → bytes),
   `reproducible` (pin → bytes), `checked` (validated every run), or
   `trusted` (quarantined, admitted only behind a verifier hop). The cardinal
   sin is tier inflation — "certified" silently meaning "tested on a corpus."
4. **Has a schema that is a contract.** A reader (LLM or human) with the
   `SCHEMA.md`, the spec, and the source can in principle derive the
   output exactly (the predictability invariant) — or, for `reproducible`
   pairs, a `CONTRACT.md` with a digest-pinned toolchain.
5. **Declares its loss.** A `Preservation(keeps, discards)` contract, so a
   chain's total loss is the inspectable union of discards, never silent.
6. **Externalizes every choice.** Anything heuristic becomes either
   schema-documented-and-fixed or a spec parameter. No third option, no
   reasoning in the translator.
7. **Lifts back.** A reasoning pair grounds solver output in source-level
   facts (witness replay), so verdicts are about the program, not the
   encoding.
8. **Earns effectiveness claims.** Benchmarked per `BENCHMARKING.md`
   (conditions A/B/C minimum) before any claim that the pair helps an LLM.

**A bad pair** (each item is the negation of one rule, and each is
observable): a hidden adaptive IR; nondeterministic output (collapses
caching, chaining, cross-checking, and the predictability probe at once);
an aspirational schema the bytes don't follow; undeclared loss
("understanding via a lossy chain is an illusion of understanding");
solver choices or bounds baked into translation; verdicts left in
reasoning-language terms; tier inflation; "effective" asserted from
anecdote.

**Release artifacts for this section:**

- `PAIR_QUALITY.md` (or a promoted `PAIRING.md` section): the eight rules
  above as the normative definition, with the 2×2 taxonomy and tier table.
- A **conformance suite**: `gurdy pair lint <pair>` (or a pytest battery a
  third-party pair must pass) checking mechanically what is mechanically
  checkable — determinism (recompile-and-diff), schema/version presence,
  declared tier and preservation contract, alignment-oracle wiring for
  pairs that claim interpreters, lifter round-trip on a witness. The
  existing `PAIR_TEMPLATE.md` becomes the scaffold; the suite is the gate.
- In the paper: a table of the seven existing hops/pairs
  (`riscv/aarch64/wasm/ebpf/evm → btor2`, `crn → smtlib`,
  `btor2 ↔ smtlib`, `c → riscv`, `smiles → formula`) scored against the
  eight rules — demonstrating the definition is discriminating, not
  decorative.

## 4. Beyond programming: math, physics, chemistry

The claim to make is **field-blindness**: a language is admissible as
`L_in` iff it has a formal semantics — executability not required. This is
already *demonstrated*, not just proposed, which is what saves the section
from being hand-waving:

- **Chemistry (shipped, both species).** `crn-smtlib` is a working non-CS
  *reasoning* pair — chemical reaction networks under discrete-population
  semantics to QF_LIA, decided by Z3. `smiles-formula` is a working non-CS
  *transparent compile* hop, run through the identical `CompileHop`
  machinery and commuting-square contract — the field-blindness witness.
- **Physics (roadmap, one strong concrete example).** `Lagrangian → EOM`
  via the variational schema is a textbook transparent compile pair — the
  predictability invariant holds in physics verbatim. Also: Feynman
  diagrams → amplitude integrands (deterministic Feynman rules), quantum
  circuits → ZX-calculus/SMT, dimensional analysis as a small decision
  pair, Modelica/bond graphs → DAE systems.
- **Mathematics (roadmap).** Polynomial systems → Gröbner bases (compile
  pair into computer algebra); Bayesian networks → weighted model
  counting → #SAT — a real chain from probability into logic; group
  presentations, term-rewriting systems.
- **The hub thesis generalizes:** SMT-LIB and #SAT/WMC become interlinguas
  that chemistry, physics, and probability route into — the same star
  topology the five ISA front-ends already form around BTOR2.

For the paper: one subsection + the field table from
`DESIGN_pair_taxonomy.md` §4, anchored by the two shipped chemistry
artifacts and (only if the schedule allows, post-submission) a
`lagrangian-eom` pair as the physics witness. **Do not build new field
pairs before the deadline** — the two chemistry artifacts carry the claim.

The deeper statement, worth one paragraph in the introduction: the
operational definition of understanding — *certified mobility between
representations* — is field-free. An LLM understands an object to the
degree it can move it, meaning-preservingly and checkably, into the
representation where a question becomes decidable. Programs are the first
instance, not the definition.

## 5. Release engineering (the "released" half of the ask)

| Item | State | To do |
|---|---|---|
| PyPI package (`hurdy-gurdy`, `gurdy` CLI) | exists | cut a tagged release matching the paper (v1.0); freeze schema versions cited in the paper |
| README | **rewritten 2026-06-13** to match reality (5 registered pairs, the BTOR2 hub + cross-ISA cross-check, the registry CLI, the bench Pareto/wedge numbers) | add the pair-quality rules (§3) when `PAIR_QUALITY.md` lands |
| Docker bench image | multi-arch v0.2.1, digest-pinned, CBMC/ESBMC/cvc5 wired | freeze the digest the paper cites |
| Tests | 314+ unit tests, integration suites, oracle batteries | green run on the frozen tag; CI badge |
| **Artifact (AE)** | bench infra exists | one-command reproduction: container + `make popl-tables` regenerating every number in the paper from `bench/*/baselines/_runs/`; Zenodo DOI; anonymized for submission, named for AE |
| Docs for pair developers | `PAIRING.md`, `PAIR_TEMPLATE.md` | add `PAIR_QUALITY.md` + conformance suite (§3) |
| License | MIT | fine |

## 6. Schedule to July 9

- **Week 1 (Jun 12–19).** ✅ **LLM evaluation done ahead of schedule** —
  the full A/B/C/D × 2-family × 5-seed run + T4 lift addendum + §7
  determinism/leakage checks are complete and committed
  (`runs/v0.6-two-family/`). README rewritten. Remaining week-1 work:
  freeze claims and schema versions; draft the formal core (P1) — the
  definitions and laws are already on disk, they need POPL prose and the
  tikz-cd squares from `DESIGN_generalized_pairs.md` Appendix A.
- **Week 2 (Jun 19–26).** Build the paper's per-cell tables from the v0.6
  manifests; (optional) run the predictability probe. Write evaluation +
  design sections around the **sharpened, D-informed claim** (calibrated
  soundness without coaching). Related work: translation validation
  (CompCert, Alive2), institutions (Goguen–Burstall), bounded model
  checking (CBMC/ESBMC/Pono lineage), and the LLM+solver line of work this
  is *not* (no reasoning in the tool).
- **Week 3 (Jun 26–Jul 3).** Full draft. Internal/colleague review.
  Consolidate `PAIR_QUALITY.md` + conformance lint. Anonymized artifact
  snapshot.
- **Week 4 (Jul 3–9).** Polish, anonymization audit (selfie/rotor lineage,
  repo URLs, memory of authorship in examples), submit by AoE July 9.
- **Post-submission.** Public v1.0 release (PyPI tag, README rewrite,
  announcement); AE package; optional `lagrangian-eom` physics witness and
  condition-E battery for the author response / camera-ready.

## 7. Top risks

1. **Venue fit.** Mitigated by formal-first framing (§1); fallbacks PLDI/
   CAV 2027. Decide by ~Jul 1 from the draft's shape, not from hope.
2. ~~LLM experiments underdeliver or don't finish.~~ **Retired** — the
   A/B/C/D × 2-family × 5-seed run is complete and committed. Residual:
   the optional predictability probe and condition E are nice-to-haves,
   not load-bearing.
3. **Anonymization leak** via lineage, repo, or PyPI package name —
   needs an explicit pass, not an afterthought.
4. **Overclaiming — now the *first*-order risk, and the v0.6 data is the
   discipline.** The defensible claims, with D in hand: the pair gives
   **calibrated soundness without coaching** (not "highest accuracy" — a
   coached CBMC matches/beats it on verdicts); a Pareto/qualitative win on
   hallucination + witness-grounding + soundness-by-construction (not
   blanket dominance); `checked`-on-a-corpus (not "proven"); field-
   blindness witnessed by chemistry (not "works for all of science"). The
   T4 addendum is the honesty proof — we report where the pair *doesn't*
   help (causal-explanation prose). Every place the draft says *certified*
   or implies the pair is "more accurate," check it against §1(P3).
5. **Machine resources.** Bench runs sequential, one instance in flight,
   per the standing RAM constraint.
