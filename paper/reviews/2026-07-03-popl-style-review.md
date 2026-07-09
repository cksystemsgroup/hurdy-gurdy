# POPL-style review (internal, pre-submission)

Produced 2026-07-03 by a fresh, context-free reviewer agent instructed to
review as an expert POPL PC member (semantics, compiler verification,
translation validation, proof assistants, SMT). The agent verified the Lean
mechanization (built it, checked the axiom audit), cross-checked evaluation
tables against the JSON data and the harvest code, and checked repo-level
claims before writing. Verdict: **C (weak reject), expert confidence.**

Kept verbatim below as the worklist for revision. Items fixed in the
2026-07-03 revision pass are marked [FIXED]; items requiring new
experiments or mechanization are marked [OPEN → future work].

## Addendum: post-submission revision pass (2026-07-03/04, after tag popl27-submitted)

Every remaining [OPEN] evaluation/mechanization item was closed by new,
regenerable experiments (commits c067112..HEAD):

- **True conjunction + language-owned inventories** (§3a/b, comments 4/5):
  coverage now measured as accepted∧square-passing per probe and per hop
  (`coverage.measure(faithful=)`, `Pair.square`, route-level conjunction in
  `grade.composed_coverage`); inventories language-owned; both RISC-V routes
  96/96 on one denominator (ECALL wart gone). First run caught three real
  defects (I20–I22). Commit c067112.
- **External benchmark** (§3 scale): the compliance slice as a derived
  question set — 78 questions, interpreter ground truth anchored by the
  Sail-simulator differential, decided along BOTH routes, 78/78 agree+correct
  (tab:bench). Enabling fix: riscv-sail keeps absolute addresses (0.3).
  Commit cff96e1.
- **Nontrivial certificate** (comment 14, question 6): bounded factorization
  of 2^31-1 (16×16-bit factors) — 2.8 MB DRAT → 11.8 MB LRAT re-validated by
  cake_lpr in ~5 s; two-column proved table (propagation- vs search-scale).
  Commit ~T1.3.
- **Escape-rate estimate** (§3 bugs): seeded fault injection through the
  gate stack; the experiment audited its own instrument (I23: degenerate
  probe operands; two hardening rounds, escapes 2/51 → 2/53 → 0/55; catches
  moved to the square layer 36→50→51; branch questions caught 0 — reported).
  tab:escape.
- **LLM-player experiment** (comment 8, question 5): first controlled
  two-arm study, 12 ground-truthed questions; both arms 12/12 — headline is
  the evidence class (say-so vs machine-checked artifacts incl. a 17 MB
  verified LRAT); limitations stated. results/llm_player/.
- **Specialization obligation mechanized** (comment 3):
  `universal_from_open_artifact` (Lean, propext only) derives Thm 4.9's
  per-instance translations from the single open translation.
- **Assumption 2 / shared bridge** (comment 6, question 3): branch
  questions re-decided with fully disjoint stacks after the head (native
  btormc vs bridge+z3), all agree; residual share (emission library,
  endpoints) stated. (2026-07-09 consistency pass: extended from ten to
  all twelve solver-level questions — the two C-headed rows included.)
- **Scalability** (§3 scale): tab:scale — loops to k=505 sub-second,
  certificates 25 kB → 11.8 MB, no cliff.

Still open: SV-COMP-style C tasks / upstream binaries (needs machine-mode),
larger differential volume, common-mode mutation families, A64 widening,
player experiment at unaided-failure difficulty; the venue question.

---

## 1. Summary

The paper proposes a calculus for reasoning about *graphs* of translations
between formally defined languages, where different edges honestly warrant
different levels of trust. The unit is a "pair": a translator, interpreters
for both languages, a *target-to-source interpreter* (carry-back) promoted
to a first-class component, and a declared projection naming which source
observables the pair promises to preserve. Faithfulness of a pair at a
program is a decidable commuting-square check; squares compose by a pasting
theorem whose extra hypothesis — a "support" condition demanding that an
earlier hop's carry-back not read target observables a later hop discards —
the authors identify as the non-folklore ingredient, and which induces a
compositional "keep/loss" computation for routes. On this base the paper
builds a fidelity algebra (five evidence grades quotiented onto a
four-element chain of assurance classes composing by weakest link), per-run
"re-establishment" of opaque hops by inline square checking, corroboration
between independently derived routes, a trusted-base ledger, a
coverage-ratchet discipline, and two end-to-end theorems expressing an
existential/universal asymmetry: witness-carrying answers are
self-certifying after carry-back and source replay, while universal answers
are where grades, branches, and checked certificates must carry the weight.
The compositional core is mechanized in Lean 4 (~750 lines, no mathlib).
The calculus is instantiated in a platform of 13 languages and 13 pairs
(C/RISC-V/AArch64/Wasm/eBPF/EVM/Python/Sail/CRN/SMILES over BTOR2 and
SMT-LIB hubs), all of it LLM-written under the architecture's checks as the
only semantic gate, and evaluated on per-construct coverage, dual-route
agreement (12 questions), four end-to-end case studies, one certified-UNSAT
exhibit re-validated by cake_lpr, and a mined catalog of 19 defects the
architecture caught.

The paper communicates its contribution clearly; it is unusually
well-written and unusually honest about its own limitations. My concerns
are that the theory is thin (the theorems are one-liners once the
definitions are fixed, and the paper half-admits this), that several
load-bearing prose claims outrun what the theorems and the implementation
actually establish (most seriously around the compiler hop, the universal
theorem, and the diversity assumption), and that the evaluation, while
genuinely regenerable, is very small and in two places measurably
inconsistent with the paper's own definitions.

## 2. Assessment of the core theory (Sections 3–4)

**Coherence of the definitions.** The definitions are clean and internally
coherent, with two significant scope restrictions that the paper does not
foreground enough. First, behaviors are *finite* sequences and semantics is
a *partial function* — so nondeterminism, divergence, I/O events, and
refinement (behavior *inclusion* rather than projected trace *equality*)
are all outside the calculus. This matters because the introduction
advertises the calculus as covering "an optimizing C compiler," yet a
trace-equality square (even with the retiming windows of Appendix A.2) is
not a notion an optimizing compiler can satisfy at any nontrivial
projection; the entire compiler-verification literature uses
simulation/refinement precisely because equality is unattainable.
Tellingly, the one hop in the platform where translation is genuinely hard
— C→RISC-V — is exactly the hop that *has no square* (grade `reproducible`,
no interpreter, no carry-back). The calculus is thus exercised only on
translations that are close to structure-preserving, where trace-equality
checking is easy. Second, Definition 3.1 requires a reference semantics as
a function; for C this is false (unspecified evaluation order, UB), and the
platform's own bug table (the `INT_MIN / -1` row) trips over exactly this.
[FIXED: scope paragraph added in §3.1]

**The pasting theorem and the support condition.** The theorem is correctly
stated and correctly proved (I checked the appendix proof and the Lean
proof; they agree). The counterexample in Appendix A.1 shows the support
condition is genuinely necessary *in this formulation*. But the condition
itself is mathematically routine: it says π∘Λ₁ must respect the equivalence
induced by π₂ — i.e., Λ₁ descends to a well-defined map on π₂-quotients.
This is the standard well-definedness/congruence condition for maps between
setoids, and analogues appear wherever simulations are composed vertically
across differing observations: CompCert avoids it by fixing one global
event type as the common currency; certified abstraction layers (Gu et
al.), CompCertO's simulation conventions, and Pilsner-style inter-language
simulations all confront versions of it. The paper's positioning —
"pasting is folklore; the support condition is not" — is therefore only
half-defensible: the condition is not folklore *as an explicit design rule
with a syntactic keep/loss computation*, and that engineering reading (the
`deps(f) ⊆ π₂` characterization, cumulative route loss) is genuinely
useful. But as mathematics it is a one-line observation, and the paper
should compare against the vertical-composition literature (see §5 below)
before claiming novelty. Note also that the π₂-closure clause of
Definition 3.6 is dead weight: the theorem never uses it (the appendix
concedes this obliquely, and the mechanization explicitly drops it). A
definition clause that neither the theorem nor the mechanization needs
should not be in the definition.
[FIXED: novelty repositioned in §1/§7; closure clause removed]

**Grades vs. assurance classes.** The separation is a nice piece of
conceptual hygiene, and the observation that `predicted` and `proved` are
incomparable in evidence but identical in logical form is well made.
However, the mapping class(`predicted`) = `universal` is *asserted, never
argued*. "Output derivable byte-for-byte from a written specification" is a
statement about the translator implementing its rule table, not about the
rule table preserving semantics; a faithful-to-a-wrong-spec translator is
`predicted` and universally unfaithful. The paper's own evidence refutes
the mapping: the BTOR2→SMT-LIB bridge — the flagship `predicted` edge —
silently dropped `constraint` lines, "an under-constrained,
soundness-leaking encoding" (Table: bugs, row 8). So a declared-universal
edge was universally wrong within its domain until a coverage probe caught
it. At minimum the paper must state that grade *declarations* are
themselves trusted (they belong in the ledger), and that only `checked` is
mechanically enforced by the framework. Similarly, `proved`'s evidence ("a
machine-checked certificate that the square commutes") is ambiguous between
per-program and universal certificates; as used in §6.4 it is per-question,
which is `perrun` in the paper's own taxonomy, not `universal`.
[FIXED: declarations-are-trusted + per-question proved caveat added in §4.1]

**Re-establishment (Thm 4.3).** As a theorem this is literally the pasting
theorem with hypotheses renamed — the Lean file says so verbatim ("The
statement is `pasting` itself; this alias records the reading"). That is
fine as far as it goes; the conceptual reading has value. What is not fine
is its flagship application. The theorem requires the oracle to run and
pass *at every hop, including the head*. In the platform, the C→RISC-V
hop's square never runs (there is no C interpreter and no ISA-to-C
carry-back). Downstream squares validate that the BTOR2/SMT artifacts are
faithful to the *compiled binary*; they establish nothing about the
binary's faithfulness to the C source. Yet the paper claims, three separate
times (overview §2 "retroactively covers the compiler... the opaque head is
re-established per run (Thm 4.3)"; §4.2 "why an opaque, pinned C compiler
is admissible at the head"; §5.3 "re-established per run per Thm 4.3"),
that Theorem 4.3 covers the gcc hop. It does not: the theorem's hypotheses
are unsatisfied at hop 1. The honest statement — which the evaluation is
actually consistent with, since the C-spine questions are about `a0`, an
ISA observable — is that the verified route *starts at the binary*, and the
C hop contributes only reproducibility. This is the most consequential
overclaim in the paper.
[FIXED: §2/§4.2/§5.3 rewritten — verified routes begin at the binary]

**End-to-end theorems (4.8/4.9).** Theorem 4.8 is trivially true — the
paper embraces this ("its proof term is three tokens"), and I agree the
*asymmetry* is the right design lens; but the insight is not new: it is the
violation-witness/correctness-witness asymmetry that SV-COMP has
operationalized for a decade, and the certifying-algorithms literature's
producer/checker split (both discussed in §5). Also, 4.8's "TCB = adequacy
alone and nothing else" quietly excludes the φ-evaluator, the projection
code, and the open-program-closing substitution, all of which sit in the
final judgment. Theorem 4.9 is where I have a real objection: **the paper's
statement and the mechanized statement are different theorems.** The Lean
`universal_needs_machinery` assumes outright `hfaith : ∀ x, FaithfulAt …
(p x)` — route faithfulness at *every input instance*. The paper's clause
(i) claims this can be discharged by "perrun evidence together with branch
agreement per Lemma 4.5." It cannot: per-run oracle evidence covers only
the (finitely many, concrete) closures actually executed, while the
solver's universal verdict ranges over all inputs; and Lemma 4.5 only
converts agreement into "both faithful or both identically wrong" — the
bridge from there to faithfulness is Assumption 2, which is structural and
explicitly non-mathematical. Moreover, Theorem 4.9 has no proof anywhere in
the paper (the appendix proves 3.7, 3.8, 4.2, 4.7 only), so the reader who
chases the claim lands on a Lean theorem with a strictly stronger
hypothesis than the prose offers. Related: §3 defines pairs over *closed*
programs and the oracle checks closed runs, but the artifact shipped to the
solver encodes the *open* program with free inputs; the obligation that
translation commutes with input specialization — the actual soundness
content of BMC-style encoding — is never stated, in the paper or in Lean,
where `hrun` quantifies over per-instance translations that the platform
never performs.
[FIXED: 4.9 restated to match Lean; evidence-vs-entailment sentence;
specialization obligation stated explicitly. TCB residue of 4.8 widened.]

**Does the mechanization back what the paper claims?** Yes — I verified
this directly. All named theorems exist in
`paper/mechanization/Calculus/*.lean` (752 lines, matching "~750"); there
are no `sorry`s; `lake build` succeeds on the pinned toolchain and the
printed axiom audit matches §4.7's claims exactly (branch lemmas, ratchet,
and 4.8 axiom-free; pasting, weakest-link, re-establishment, 4.9 `propext`
only; localization the sole `Classical.choice` use; telescope adds
`Quot.sound`). The telescope construction with the reprojection lemma is
competent. But be clear about what is mechanized: the definitions plus
proofs that are each under ~15 lines of tactics. The genuinely intricate
content — first-failure localization to step and field, the fieldwise
keep/loss computation, the retiming case, everything about coverage
measurement — is not mechanized (the paper says so, to its credit). The
mechanization is best described as a machine-checked sanity audit of a
small design algebra, not a verification effort. It does back §4.7's
claims; §4.7's claims are modest. One further caveat: the mechanization's
`universal_needs_machinery` backs the *Lean* version of 4.9, not the
paper's clause (i), per the gap above.

**Folklore dressed as new?** Weakest link (Prop 4.2), the branch lemmas
(4.4/4.5 are two-line consequences of transitivity of equality),
determinism-and-caching (Prop 3.9), and the ratchet (Prop 4.7 is:
extensions preserve values, hence verdicts) are all folklore or immediate.
The paper is largely upfront that the value is architectural rather than
mathematical, and I would not reject it for honesty about shallow proofs.
But the sum total of *new, nontrivial* theory is: the support condition
(routine as math, useful as discipline) and the grade/class separation (a
taxonomy). For POPL that is a thin theoretical core.
[OPEN → future work / venue decision]

## 3. Assessment of the evaluation (Section 6)

**Reproducibility and number-honesty.** I spot-checked every number I
could: the tables are byte-generated by `results/harvest.py` from the live
registry; `capability.json`, `composed.json`, `branch.json`, `cases.json`,
`proved.json`, `perf.json` all match the paper's tables and prose; the
claimed "1193 tests" matches an independent count of test functions in the
repo; the snapshot commit in `env.json` is a real ancestor of HEAD; the
bugs table is backed by a 675-commit mining document with per-incident
SHAs. This is a much higher standard of evidence hygiene than typical, and
I commend it.

**But two measured quantities contradict the paper's own definitions.**
(a) Definition 4.6 defines coverage as the per-construct *conjunction* of
covered and faithful, and §6's opening promises "per-pair conjoined
coverage." The code that produces Table 1 (`gurdy/core/coverage.py:measure`,
called from `harvest.py:run_capability`) counts a construct as covered iff
its probe *translates without a typed `Unsupported` abort* — no square
oracle, no faithfulness check, anywhere in the measurement.
`composed_coverage` (Table 2) likewise checks only that probes survive
translation at every hop. So the headline coverage numbers measure
translator *acceptance*, which is precisely the axis Definition 4.6 was
designed to close ("coverage is gamed by unsoundness — accept everything,
translate it wrongly"). The paper's §6.1 phrasing ("measured by running
every probe through the pair's translator") quietly concedes this, but the
table caption, the section headline, and Definition 4.6 all say
"conjoined." (b) Definition 4.6 fixes the inventory *per language*; the
harvest uses the *head pair's* probe set as the denominator, which is why
the same source language RISC-V appears as 96/96 on the direct route and
95/95 via Sail. If RV64IMC's inventory is 96 constructs, the Sail route is
95/96 with one construct lost, and both "the spine composes losslessly"
(§6.2) and "all of RV64IMC surviving composed to SMT-LIB" (§7) are wrong as
stated; if it is 95, the direct route's denominator is inflated. Either
way, the denominators are pair-chosen — exactly the "yardstick the
implementer does not choose" that §4.5 forbids. The AArch64 "33 in-scope"
and eBPF "126 in-scope" inventories have the same problem in starker form
(A64 has thousands of instructions; the honest full-inventory style of the
EVM row, 86/144, shows what the others should look like).
[FIXED: tables relabeled acceptance-coverage; denominators declared as
pair-owned (limitation); ECALL identified as the one-construct difference;
"losslessly"/"all of RV64IMC" corrected. OPEN: measuring the true
conjunction; language-owned inventories.]

**Scale.** The evaluation is very small, and I will quantify: 12
solver-level branch questions plus 2 trace comparisons, 4 end-to-end case
studies, 1 certified-UNSAT question — on programs of roughly 5–20
instructions ("6*7=42 on the operand stack", constant dataflow, a summation
loop at k=25). Total solve time for almost everything is under 100 ms.
There is no external benchmark (no SV-COMP tasks, no riscv-tests-derived
reachability set even though riscv-tests are already wired for adequacy),
no comparison against any existing tool as a baseline, and no scalability
data beyond one loop. The certified tier is inhabited by exactly one
question, and — the paper does not remark on this — its elaborated LRAT
certificate is **18 bytes** (`proved.json`), i.e., the bit-blasted CNF for
x²=3 is refuted essentially by unit propagation (unsurprising: x² mod 4 ∈
{0,1}). The certified pipeline has therefore been demonstrated on a
trivially-unsat instance; nothing shows it survives a certificate of
nontrivial size. The paper pre-empts with "deliberately limited but
non-trivial"; I accept "limited," but "the platform shows the discipline is
buildable ... at useful coverage" (§7) is not supported at this scale.
[FIXED: triviality of the certified instance reported. OPEN: external
benchmarks, nontrivial certificate, scalability.]

**The bugs evidence.** This is the strongest part of the evaluation and
also intrinsically anecdotal. The 19 incidents are well-documented
(commit-level provenance, catching mechanism taken from the primary record,
one disconfirmed report, incidents caught by ordinary unit tests excluded),
and three of the narratives are genuinely valuable: the checks catching
their own instruments (the `NOT VERIFIED` substring bug is a beautiful
cautionary tale), the unit-tests-codified-the-author's-misreading
observation, and above all the honestly-reported **MUL/ADD blind spot**,
where the interpreter and translator mis-decoded the same instruction
identically and the square was structurally blind. But note what that last
incident means: the component that Theorem 4.8 crowns as the *sole residual
TCB* (interpreter adequacy) is exactly the component that failed silently,
and it was found by manual audit, not by the architecture. The adequacy
discharge backing "trust is nearly free" is a 300-program seeded
differential, a 10-seed Csmith campaign (Csmith campaigns are normally run
at 5–6 orders of magnitude more volume), and 463 reference cases. The
evidence is real but the denominators are small, and there is no estimate
of what escaped. "Convincing as an existence proof of the mechanism,
anecdotal as a measurement of its power" is my summary.
[FIXED: no-denominator caveat added. OPEN: escape-rate estimate, larger
differential volume.]

## 4. Assessment of the framing

**The two-directional LLM experiment.** Direction one (LLM agents built the
pairs; the architecture was the only gate) is a real and interesting
experiment, and the paper is right that it strengthens rather than weakens
the thesis — a discipline claiming to manufacture trust from untrusted
translators is well served by maximally untrusted translator authors. But
it lacks controls: no comparison arm, no measure of gate escape rate (the
MUL incident proves the rate is nonzero), and "largely unsupervised" is in
tension with the artifact's own record of an autonomy protocol that
*escalated semantic changes to a human* (bugs_caught.md, I1). Direction two
— "the platform's intended player is an LLM" — appears in the abstract, the
introduction, and the related work, and is **evaluated nowhere**. There is
no experiment in which an LLM plays the platform and its conclusions are
assessed. Half of the paper's flagship framing is, at this snapshot, an
unsupported claim, and I would insist it be demoted to future work or
evaluated. The provenance disclaimer itself I consider an asset: it is the
right disclosure, it is consistent with the paper's thesis, and the
regenerable-numbers/mechanization discipline is exactly the correct
response to "why should we trust LLM-written claims." Some PC members will
be less charitable about "most of this paper's text was LLM-generated" (the
mechanization protects §§3–4, but nothing analogous protects the prose's
empirical characterizations — and indeed the overclaims I flag above are
all prose-level). The paper should expect this to be litigated and would be
wise to tighten every prose claim to what a theorem or a table licenses.
[FIXED: player direction explicitly marked architectural-not-evaluated;
supervision quantified. OPEN: LLM-player experiment.]

**Distributed-systems vocabulary.** Mostly used correctly. "Fail-stop"
(Schlichting–Schneider) is apt: the oracle converts silent wrong output
into detected failure. "Common-mode failure" and the
DMR-comparator-that-localizes framing are correct. The end-to-end argument
transplant is the best of these and is genuinely illuminating. Two
quibbles: "failure detector" has a specific Chandra–Toueg meaning
(unreliable crash detection under asynchrony) that does not fit a
synchronous, perfect acceptance test — the classical concept the square
oracle instantiates is the *acceptance test* of recovery blocks (Randell
1975), uncited; and a silently-wrong translator is a *Byzantine* component,
which is the model the redundancy argument actually addresses — saying so
would sharpen, not weaken, the analogy.
[FIXED: acceptance test (Randell) + Byzantine wording adopted.]

## 5. Related work

The section covers certified compilation, single-edge translation
validation, K/Sail, PCC/certifying algorithms, N-version programming, and
the end-to-end argument. A POPL reviewer will flag the following omissions,
several of which bear directly on claimed novelty:

- **Compositional compiler correctness — the biggest gap.** The entire line
  on composing simulations/refinements across heterogeneous languages and
  passes is absent: Compositional CompCert (Stewart et al., POPL'15),
  Pilsner/parametric inter-language simulations (Neis et al., ICFP'15),
  CompCertO and its simulation conventions (Koenig & Shao, PLDI'21),
  Certified Abstraction Layers (Gu et al., POPL'15), multi-language
  semantics (Matthews & Findler, POPL'07; Perconti & Ahmed, ESOP'14), and
  DimSum (Sammler et al., POPL'23 — a *decentralized, multi-language*
  semantics graph with wrappers between languages, uncomfortably close to
  this paper's graph framing). These works confront vertical composition of
  simulations *up to differing observations*, which is exactly the habitat
  of the support condition; the paper's "to our knowledge, new" claim for
  projection-compatible pasting cannot stand without engaging them.
- **Witness validation in practice.** SV-COMP's violation/correctness
  witness ecosystem (Beyer et al., FSE'15/'16) is the deployed form of the
  paper's existential/universal asymmetry, and certifying model checkers
  (Namjoshi, CAV'01; Kind 2's proof certificates, Mebsout & Tinelli
  FMCAD'16) prefigure the certified-unreachability tier. Theorem 4.8's
  design principle is anticipated by both.
- **Credible compilation** (Rinard & Marinov, 1999) — per-run compiler
  result validation with proofs, a direct ancestor of re-establishment.
- **Knight & Leveson (TSE'86)** — the canonical experimental refutation of
  failure independence in N-version programming. Citing Avizienis for
  diversity without Knight–Leveson is not tenable, especially since the
  paper's own MUL incident is a correlated failure between "independently"
  built components, and since the LLM agents plausibly share a model family
  and hence failure modes.
- **Decompilation into logic / verified lifters** (Myreen et al.) — prior
  art on the carry-back as a first-class, even verified, component; the
  claim that the lifter is "usually an afterthought" needs this
  qualification.
- **Rushby's Evidential Tool Bus** and the assurance-case literature —
  prior frameworks for combining heterogeneous verification evidence with
  recorded provenance; the grade/ledger machinery is a formalized cousin.
[FIXED: all of the above cited and engaged; support-condition novelty claim
repositioned.]

## 6. Detailed comments

1. **[Major] §2, §4.2, §5.3 — re-establishment applied to the C hop.**
   [FIXED]
2. **[Major] Thm 4.9 — prose hypotheses vs. mechanized hypotheses.**
   [FIXED — restated to match Lean; evidence-vs-entailment made explicit]
3. **[Major] §3/§4.6 — open vs. closed programs.** [FIXED — specialization
   obligation stated as explicit assumption; mechanization OPEN]
4. **[Major] §6.1/§6.2 vs. Def. 4.6 — coverage measured as acceptance.**
   [FIXED — relabeled honestly; true conjunction measurement OPEN]
5. **[Major] §6.2, §7 — inconsistent inventories 96 vs. 95.** [FIXED —
   ECALL named; denominators declared pair-owned; prose corrected;
   language-owned inventories OPEN]
6. **[Major] Assumption 2 vs. shared bridge/emitter.** [FIXED — diversity
   scoped to the prefix up to reconvergence; ledger row amended]
7. **[Major] §4.1 — class(predicted) = universal unjustified.** [FIXED —
   grade declarations are trusted inputs; per-question proved noted]
8. **[Major] LLM-player direction not evaluated.** [FIXED — marked
   architectural at this snapshot; experiment OPEN]
9. **[Minor] §3.1 scope restrictions unstated.** [FIXED]
10. **[Minor] Def. 3.6 π₂-closure clause unused.** [FIXED — removed]
11. **[Minor] Prop. 3.9 "detects" → "can detect".** [FIXED]
12. **[Minor] "strictly stronger evidence" rhetoric.** [FIXED — softened]
13. **[Minor] Thm 4.8 TCB omits φ-evaluator/projection/substitution.**
    [FIXED]
14. **[Minor] §6.4 certified exhibit trivially unsat.** [FIXED — reported;
    nontrivial instance OPEN]
15. **[Minor] §6.5 no denominator for bugs-caught.** [FIXED — caveat added]
16. **[Minor] §6.6 "30–70 ms" vs. data.** [FIXED — matched to perf.json]
17. **[Minor] "failure detector" → acceptance test.** [FIXED]
18. **[Minor] Python adequacy circular.** [FIXED — honest sentence]
19. **[Nit] Mechanization cross-refs off by one; README kfaithful axiom
    claim.** [FIXED]
20. **[Nit] Abstract "13 pairs converging on two hubs".** [FIXED —
    "organized around"]
21. **[Nit] "largely unsupervised" vs. escalation protocol.** [FIXED —
    supervision characterized]

## 7. Questions for the author response

1. The square oracle never runs on the c-riscv hop. Do you defend the claim
   that Theorem 4.3 "re-establishes" the pinned gcc head, given that the
   theorem's hypotheses require an oracle pass at every hop — or do you
   accept that verified routes begin at the compiled binary, and will you
   revise §2/§4.2/§5.3 accordingly?
2. For universal verdicts: pairs and the oracle are defined on closed
   programs, yet the solver consumes a symbolic encoding of the open
   program. Where is the specialization-commutes-with-translation
   obligation stated or checked? And how do you reconcile Theorem 4.9's
   clause (i) with the mechanization?
3. Your two flagship branches share the btor2-smtlib bridge hop and the
   shared BTOR2 emitter, and your own incident I3 is a cross-route
   common-mode failure through that shared code. How is Assumption 2
   satisfied by the branch runs of Table 2 as measured?
4. Table 1/2 coverage is computed by acceptance-only measurement, and the
   two RISC-V routes use different denominators (96 vs. 95). How do you
   reconcile this with Definition 4.6 — and which RV64IMC construct does
   the Sail route lose?
5. What, concretely, exists of the second direction of the "two-directional
   experiment" (the LLM player)?
6. The certified exhibit's LRAT is 18 bytes. Have you run the cake_lpr rung
   on any certificate of nontrivial size?

## 8. Overall merit

**Score: C (weak reject). Confidence: expert.**

To be explicit about the positives: the honesty discipline here —
regenerable numbers, a clean and verified-by-me Lean audit, self-reported
blind spots, a disconfirmed bug — is the best I have seen in some time, and
the carry-back-as-first-class-component principle plus the keep/loss
bookkeeping deserve to influence how people build translation pipelines.
But a POPL paper needs either a substantial theoretical contribution or
claims that are rigorously matched to evidence, and this submission
currently has neither: the theory's one novel ingredient is a congruence
condition whose novelty claim has not been tested against the
compositional-compiler-correctness literature it never cites, and the
paper's three most prominent stories — the re-established compiler head,
the universal-answer theorem, and route diversity — each say more than the
corresponding theorem or measurement licenses, in ways I verified against
the authors' own artifact. The evaluation, though genuinely regenerable, is
a dozen toy questions and two definitional mismatches away from supporting
its own tables' captions.

The three changes that would most improve the paper's chances:

1. **Make every prose claim match a theorem or a measurement.**
2. **Engage the missing literature and re-position the novelty claims.**
3. **Scale the evaluation to where the claims live.**

With those done this becomes a strong systems-flavored paper — though the
authors should consider whether its natural home is PLDI, CAV, or OOPSLA
rather than POPL.
