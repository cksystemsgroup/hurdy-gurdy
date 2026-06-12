# Releasing hurdy-gurdy for POPL 2027 — overview

*Status: planning overview (recorded 2026-06-12). What it takes to release
hurdy-gurdy in a form that (a) demonstrates value to LLMs in programming,
(b) is publishable at POPL 2027, (c) normatively defines what a good — as
opposed to bad — future pair looks like, so that others can build pairs,
and (d) states the approach's reach into mathematics, physics, and
chemistry.*

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

**(P3) The empirical demonstration — value to LLMs in programming.** The
claim with teeth: an LLM equipped with a pair reasons about programs more
correctly than the same LLM (a) alone, (b) with the raw solver, and (c)
with a source-level verifier — *specifically on lowering-sensitive
programs*, where the C-level verdict and the ISA-level verdict differ.
Existing oracle-level evidence (iter-42/43, `V2_PROGRESS.md`):

| Tool | Correct (18-task canonical subset) | FP | Median s |
|---|---|---|---|
| CBMC | 13/18 | 5 | ~0.041 |
| ESBMC | 16/18 | 2 | ~0.259 |
| hurdy-gurdy | 18/18 | 0 | ~1.768 |

plus **8/8 adversarial C-UB-but-RV64-defined wedges correct where CBMC is
0/8** (false positive on all) and ESBMC false-positive on ≥ 5. The honest
framing is a Pareto frontier — CBMC owns the speed corner, hurdy-gurdy the
soundness corner — not a strict dominance claim.

**Recommended title-level thesis:** *certified, deterministic,
compositional translation pairs are the right substrate for LLM reasoning
about programs* — formal core (P1) as the contribution, question-compiler
architecture (P2) as the design, LLM experiments (P3) as the evaluation.

**Venue-fit risk, stated plainly.** POPL reviewers may read the LLM
evaluation as out of scope and want more theory; CAV/PLDI/OOPSLA reviewers
would want less. Mitigation: the paper must stand with the LLM results
*removed* (P1+P2+oracle-level differentials already make a paper), and the
LLM results then make it timely. If POPL rejects: CAV 2027 (≈ Jan 2027
deadline) and PLDI 2027 (≈ Nov 2026 deadline) are natural fallbacks with
notification timing that allows resubmission either way.

## 2. The load-bearing gap: the LLM experiments themselves

`BENCHMARKING.md` already specifies the experiment that makes the
"value to LLMs" claim defensible; it has not yet been run end-to-end.
This is the **single highest-priority work item** before the deadline:

- **Conditions A/B/C are required** (source-only LLM; LLM + pair tool
  surface; LLM + raw solver but hand-written encoding). C is what
  separates "you gave it a structured pair" from "you gave it a solver."
  **D** (LLM + CBMC/ESBMC, no pair) is strongly recommended — it is the
  condition the wedge battery was built for. **E** (propose-and-check,
  v1.1.0 partial bindings) if time permits; a negative E result is still
  reportable.
- ≥ 2 LLMs, ≥ 3 runs per cell, per-`(condition, LLM, task-class)` tables
  in the artifact bundle — the playbook's own bar.
- Corpus exists: 104 task directories; the 18-task canonical measured
  subset and the 8-wedge battery are the headline slices. Task classes
  must split out the *lowering-sensitive* subset, where the B/D gap is the
  story.
- **The predictability probe** is a cheap second result, unique to this
  architecture: a transparent pair's schema lets the LLM *predict the
  artifact bytes*; the prediction gap is a direct, scalable measure of
  model understanding, and chain length is its difficulty dial
  (`DESIGN_generalized_pairs.md` §2). Even a small instance (predict the
  BTOR2 for the wedge tasks, measure exact/near-match rates per model) is
  a novel evaluation primitive worth a section.

Budget realism: A/B/C/D on 18 + 8 tasks × 2 models × 3 runs is
~600 LLM sessions plus solver time — feasible in one to two weeks if
started immediately, run sequentially with capped parallelism (this
machine has OOM'd before; keep corpus processing one-instance-at-a-time
per the standing RAM discipline).

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
| README | **behind reality** — names 2 pairs + 1 planned; repo has 5 ISA pairs, the bridge, CRN, 2 hops | rewrite around the taxonomy (genus/species, tiers, chains); add the pair-quality rules |
| Docker bench image | multi-arch v0.2.1, digest-pinned, CBMC/ESBMC/cvc5 wired | freeze the digest the paper cites |
| Tests | 314+ unit tests, integration suites, oracle batteries | green run on the frozen tag; CI badge |
| **Artifact (AE)** | bench infra exists | one-command reproduction: container + `make popl-tables` regenerating every number in the paper from `bench/*/baselines/_runs/`; Zenodo DOI; anonymized for submission, named for AE |
| Docs for pair developers | `PAIRING.md`, `PAIR_TEMPLATE.md` | add `PAIR_QUALITY.md` + conformance suite (§3) |
| License | MIT | fine |

## 6. Schedule to July 9

- **Week 1 (Jun 12–19).** Freeze claims and schema versions. Stand up the
  condition-A/B/C/D harness from `BENCHMARKING.md` and start runs on the
  canonical 18 + 8 wedges (2 models × 3 runs, sequential, RAM-capped).
  Draft the formal core (P1) — the definitions and laws are already
  written, they need POPL prose and the tikz-cd squares that exist in
  `DESIGN_generalized_pairs.md` Appendix A.
- **Week 2 (Jun 19–26).** Finish LLM runs; build per-cell tables; run the
  predictability probe. Write evaluation + design sections. Related work:
  translation validation (CompCert, Alive2), institutions (Goguen–
  Burstall), bounded model checking (CBMC/ESBMC/Pono lineage), and the
  LLM+solver line of work this is *not* (no reasoning in the tool).
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
2. **LLM experiments underdeliver or don't finish.** The paper still
   stands on P1 + oracle-level differentials (18/18 vs 13/18 vs 16/18;
   8/8 wedges); LLM results become author-response or camera-ready
   material. Don't let condition E block A–D.
3. **Anonymization leak** via lineage, repo, or PyPI package name —
   needs an explicit pass, not an afterthought.
4. **Overclaiming.** The honest claims: Pareto frontier (not dominance),
   `checked`-on-a-corpus (not "proven"), field-blindness witnessed by
   chemistry (not "works for all of science"). Every place the draft says
   *certified*, verify the tier vocabulary backs it.
5. **Machine resources.** Bench runs sequential, one instance in flight,
   per the standing RAM constraint.
