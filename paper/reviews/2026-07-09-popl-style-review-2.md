# POPL-style review #2 (internal, post-revision)

Produced 2026-07-09 by a second fresh, context-free reviewer agent
(instructed NOT to read the 2026-07-03 review, to avoid anchoring), at
HEAD `9e25222` — i.e., reviewing the revised paper with all of the
first review's items closed. The agent built the Lean mechanization,
ran the full test suite, cross-checked every generated table against
its primary JSON and the harvest code, live-regenerated coverage /
branch / disjoint / certified-tier results read-only, and executed the
§3.2 worked example. Verdict: **B− (accept with reservations),
expert confidence 4/5.**

Kept verbatim below as the worklist for the camera-ready / next venue.

## Addendum: same-day fix pass (2026-07-09, after the review)

Everything fixable without new experiments was applied:

- **Major 1**: §4.7 now states plainly which hypotheses of Thm 4.9 no
  machine checks (`hZ`, the specialization obligation) and that the
  evaluation corroborates rather than cites them.
- **Major 2**: the §6 one-script claim is scoped (tab:bugs hand-mined;
  tab:player a curated record; escape earlier-round numbers from the
  incident record).
- **Major 3**: the player limitations list gained the grading-
  circularity item (now four).
- **Major 4**: the escape caption itself now carries the
  "seeded families covered ≠ escape rate zero" framing.
- **Minor 5**: tab:branch header "Route" (not "to SMT-LIB"); CRN/Python
  rows marked † = no decidable-square hop, acceptance with per-run
  faithfulness.
- **Minor 6**: capability caption no longer claims the C hop is marked
  per-run (it shows "---").
- **Minor 7**: `write_env` now records the full engine inventory
  (btormc 3.2.4, bitwuzla, boolector, cadical 3.0.0, drat-trim/cake_lpr
  pins) in env.json.
- **Minor 8**: bugs mining count frozen to its 2026-07-03 pass.
- **Minor 9**: "runs 1204 tests, all green (3 host-dependent skips)"
  (count updated to match the suite after the Minor-10 fix added
  tests).
- **Minor 10**: `decide_bounded` exhaustion signal now guarded by a
  trivially-reachable canary (negative control) + two permanent tests
  (a silently-broken stub binary is not trusted; the real binary
  passes).
- **Minor 11**: Def 3.2 purity marked as the contract, enforced on the
  evaluation host by twice-and-diff.
- **Minor 12**: appendix §B eBPF wording aligned (126-construct slice
  of the 256-opcode space).
- **Nits 13-15**: perf warm "<0.1"; bench total 78/78; abstract
  glosses "largely unsupervised" (one human gate: shared-emitter
  sign-off).
- **Related work**: Why3, Sledgehammer, SMT-COMP model validation,
  riscv-formal added with citations.
- Also: tab:proved TCB row labeled "(solve step)" with the route-hops
  clause in §6.5 prose; §6.3 gained a third honesty note (the benchmark
  cannot see MUL/ADD-class shared misreadings); the §6.9 decide time
  de-jittered.

Not addressed (need experiments — the review's grade-raisers):
at-scale/in-the-wild campaign, mechanically checking `hZ` /
specialization per pair, both-leg common-mode fault injection,
out-of-family player round.

---

**Reviewer persona:** PC member working in PL semantics, compiler
verification / translation validation, proof assistants, SMT, and
empirical evaluation of verification tools. Adversarial but fair; I
tried to break the paper's central "regenerable and machine-checked"
claim before assessing anything else.

**What I verified mechanically (all on the artifact at HEAD `9e25222`):**
- **Lean mechanization:** `lake build` (Lean 4.31.0) succeeds; the
  `#print axioms` audit (`Calculus/Audit.lean`) lists 16 results; the
  axiom footprints match Table `tab:mech` **exactly** (pasting/pasting₃:
  `propext`; localization: `propext, Classical.choice, Quot.sound`;
  agree/disagree/ratchet/existential: axiom-free; telescope:
  `+Quot.sound`, localization additionally classical). No `sorry`.
  ~830 lines as claimed.
- **Test suite:** `python3 -m unittest discover -s tests` →
  `Ran 1204 tests ... OK (skipped=3)` in 308 s.
- **Every generated table cross-checked against primary JSON**
  (`results/data/*.json`, `results/llm_player/results.json`) and against
  what `results/harvest.py` computes: capability (13 rows), composed
  coverage (10 routes), branch (12 solver-level + 2 trace-level + 12
  disjoint rows), bench (78/78/78, per-program rows, Σtime 51.8 s <
  "under a minute"), cases, perf, proved (41746 B DRAT / 18 B LRAT;
  2.8 MB / 11.8 MB; engines; controls all `false`), scale, escape
  (55/51+0/0/4/0), player (12 rows vs. `results.json`). **No
  discrepancies found.**
- **Live regeneration (read-only):** re-measured conjoined coverage for
  `riscv-btor2` (96/96), `evm-btor2` (86/144), `python-smtlib` (11/27)
  — matches; re-ran the loop `sum==99` unreach question along both
  routes **and** the disjoint native-btormc stack — all `UNREACHABLE`,
  agreeing; re-ran the propagation-scale certified exhibit end to end —
  reproduced byte-identical certificate sizes, `tier=proved`, TCB, and
  both negative controls correctly rejected.
- **Code-vs-definition checks:** `gurdy/core/coverage.py::measure`
  really conjoins acceptance with a square-oracle pass (any
  non-`Unsupported` exception propagates — no silent pass);
  `gurdy/core/grade.py::composed_coverage` really re-runs each hop's
  square on that hop's input;
  `gurdy/solvers/native_btor2.py::decide_bounded` really decides BTOR2
  natively (no bridge/SMT-LIB/Z3 anywhere in that path);
  `gurdy/solvers/proved.py::check_lrat_verified` requires the exact
  `s VERIFIED UNSAT` line and never falls back after a cake_lpr
  rejection; `tools/fault_injection.py` accounting (95 generated − 40
  inapplicable = 55; kills 51/0/0/4/0) matches `escape.json` and the
  paper's prose.
- **Worked example (§3.2):** executed the actual `JAL` probe square:
  post-step trace `(pc=8, x1=4, halted=F), (pc=8, x1=4, halted=T)` —
  matches the paper's table verbatim; the 0.1→0.2 fix is documented in
  `gurdy/pairs/riscv_btor2/translate.py:287-291` and the square passes
  now.
- **Consistency:** `check_crosswalk.py` passes (9 frozen appendix
  references match `main.aux`); zero undefined references/citations in
  `main.log`; 20 pages.

Negative results of my attempts to refute: I could not find a single
table cell inconsistent with its primary data, nor a mechanization
claim that overstates what the Lean file proves, nor a case where the
coverage or certified-tier code measures something other than the
paper's definition.

## 1. Summary

The paper proposes a calculus for *graphs* of translations rather than
single translators. The unit is a "pair": translator, source/target
interpreters (language-owned), and a mandatory *target-to-source
carry-back*, closing a commuting square that is decidable per program
under a declared projection (the pair's promise; its complement is
declared loss). Squares paste under a congruence-style *support*
condition, giving routes with a syntactic keep/loss computation. Each
edge carries a fidelity grade (trusted / reproducible / checked /
predicted / proved) mapped onto a totally ordered assurance-class
chain; classes compose by weakest link, per-run inline square checking
"re-establishes" opaque hops for a given run, and independently derived
routes to the same target corroborate each other under an explicit
diversity assumption. A trusted-base ledger itemizes what each checking
layer removes. The capstone is an asymmetry: witness-carrying
(existential) answers are self-certifying via carry-back and source
replay (TCB = source-interpreter adequacy only), while universal
answers are where grades, branches, and independently checked
certificates must carry the weight. The compositional core is
mechanized in Lean 4 (~830 lines, clean axiom audit). The calculus is
instantiated as a 13-language / 13-pair Python platform (two hubs:
BTOR2, SMT-LIB; dual independently derived RISC-V and AArch64 routes),
with every pair written by unsupervised LLM agents gated only by the
architecture's checks. The evaluation reports conjoined per-construct
coverage, composed route coverage, branch agreement (including fully
disjoint decision stacks: native btormc vs. bridge+Z3), a 78-question
compliance-derived benchmark with interpreter-derived ground truth,
witness-replay case studies, a cake_lpr-anchored certified tier up to
an 11.8 MB LRAT, a 23-incident defect catalog, a seeded fault-injection
escape-rate experiment (55 mutants, 0 escapes after probe hardening),
and a 12-question two-arm LLM-player experiment (both arms 12/12; the
claimed difference is evidence class, not accuracy).

## 2. Assessment of the core theory (sections 3–4)

The formal content is deliberately, and admittedly, thin. Pasting
(Thm 3.7) is folklore plus a one-line congruence condition (Def 3.6)
whose cousins the paper itself locates in CompCertO/DimSum territory;
weakest link (Prop 4.2) is immediate; the branch lemmas (4.4/4.5) are
transitivity of equality; Thm 4.8's proof term is three tokens. The
paper is unusually honest about this ("we claim no mathematical novelty
for the condition"), and I verified the honesty extends to the
mechanization: the Lean statements match the paper's statements, with
hypothesis lists that really are the TCBs claimed (e.g.,
`existential_self_certifying` assumes source-interpreter adequacy and
nothing else). The genuinely non-trivial engineering in the
mechanization is the route telescope (dependently typed chains with a
recursive coherence predicate and a reprojection lemma), which is nice
but not deep.

What I consider the real theoretical contributions, modestly sized but
real:
1. The grade/assurance-class separation (Def 4.1) resolving the
   `predicted`⊓`proved` meet question cleanly — a small but genuinely
   clarifying algebraic move.
2. The keep/loss computation as a syntactic route-level discipline
   ("declare your loss"), including the retiming case (appendix A.2,
   paper-stated only).
3. The existential/universal asymmetry elevated to an architectural
   principle with the carry-back as a *mandatory per-pair component*.
   The observation itself is well known (certifying algorithms, SV-COMP
   violation witnesses, PCC — all cited), so the contribution is the
   compositional packaging, not the insight.

Two boundary caveats a reader should keep in view, both disclosed but
load-bearing: (a) faithfulness is projected trace *equality* over
finite behaviors of a *deterministic* semantics — nondeterminism,
divergence, refinement, and hence optimizing compilation are out of
scope, and the one optimizing hop (gcc) has no square at all; (b)
Thm 4.9's clause (iii) — the certified/corroborated solver verdict —
enters the Lean statement as an abstract hypothesis (`hZ` over
target-interpreter behaviors). The formalization boundary is honest,
but the entire practical risk of the universal case
(solver-artifact-to-target-semantics correspondence, the `predicted`
bridge, the bit-blaster) lives exactly in that hypothesis. Clause
(iv)'s `CommutesWithSpecialization` is likewise stated as discharged
"by construction of its encoding" — I could not find where any pair
mechanically checks it (see Question 3).

## 3. Assessment of the evaluation (section 6)

The evaluation's distinguishing property — everything regenerable, and
I could regenerate it — is real and rare, and it should be said
plainly: this is among the most verifiable evaluations I have refereed.
That said:

- **Scale.** All programs are tiny (≤ 9 instructions authored; ≤
  69-step compliance programs; loops to N=100). Decide times are
  milliseconds-to-seconds. The paper's own defense ("fully specified
  rather than large") is fair, and Table `tab:scale` crosses the "toy"
  region smoothly, but nothing here stresses the architecture: no route
  disagreement occurs in any final table; every informative failure is
  historical (§6.6). An SV-COMP-scale or binary-for-binary riscv-tests
  campaign is named future work; for a POPL evaluation of a
  *measurement* framework I would want at least one in-the-wild
  disagreement or an unseeded escape.
- **Escape-rate experiment.** Methodologically the best section: honest
  denominator handling (inapplicable mutants excluded,
  non-commutative-only operand swaps), order-dependent kill attribution
  correctly phrased, and — crucially — the experiment's own history
  (probes hardened after `srl→sra` and `ult→ulte` escapes, incident
  I23) is reported rather than laundered. But the final "0 escapes" is
  therefore partly *by construction*: the probe corpus was hardened
  against exactly these mutation families, and the mutation operators
  themselves were mined from the incident catalog. The paper says this
  ("this mutation family is now covered"), yet the abstract-level
  impression of a measured gate strength exceeds what one translator's
  emission space under catalog-derived mutations supports. Also the
  "branch" gate here is only 4 authored questions, a weaker instance
  than `tab:branch`'s 12.
- **Compliance benchmark.** Ground truth comes from the shared
  reference interpreter — the same component inside both measured
  routes' squares. The anchoring argument (that interpreter is
  differentially validated against `sail_riscv_sim` on these same
  programs) is stated and plausible, but a shared-misreading defect of
  the MUL/ADD class would pass this benchmark undetected; the benchmark
  measures translator/route defects, not interpreter defects, and
  should say so as sharply as §6.6 does.
- **Certified tier.** I reproduced it end to end, including both
  negative controls. The checker-adapter incident (I19: `NOT VERIFIED`
  contains `VERIFIED`) and the resulting "a checker adapter without a
  negative control is itself unchecked" maxim is a genuinely valuable,
  citable observation. One quibble: `tab:proved`'s "Resulting TCB:
  bitwuzla:bit-blast, cake_lpr:verified" is the *solver-stage* TCB; the
  route hops and the `predicted` bridge that produced the SMT artifact
  are also assumed, as the ledger and §4.1's honesty note elsewhere
  concede — the table cell, read alone, understates.
- **Regenerability overclaim.** §6's "Every number is regenerated by
  one script from the live registry and real runs" is not true of two
  tables: `tab:bugs` is hand-curated (`bugs.tex` header says so), and
  `tab:player` formats a manual-protocol record
  (`harvest.py::run_player` docstring: "does not re-run the ...
  experiment"). The escape narrative's intermediate-round numbers ("36
  of 51", "50 of 53") are also not in the data. These are honest
  records, but the blanket claim should be scoped.

## 4. Assessment of the framing and claims (LLM story, growth model, honesty)

The two-directional LLM framing is the paper's most novel and most
fragile element. The **build** direction is credible: the 23-incident
catalog, with named blind spots (MUL/ADD caught by *manual audit*, not
the architecture), a common-mode emitter failure, tests codifying an
author's misreading, and clean-campaign positive controls, is exactly
the case-study evidence the claim needs, honestly labeled "not a hit
rate." The **player** direction is currently weak as an experiment:
both arms 12/12, so there is no measured benefit on correctness; arm
B's grading is close to circular (ground truth is platform-established,
and arm B answers via the platform — arm B can essentially only fail by
mis-operating the tools); entry points were scripted; the subject model
is from the builders' family. All three limitations are stated, and the
reframing to "evidence class" is legitimate — the E3 contrast (recall
of a prime vs. a 17 MB cake_lpr-validated LRAT) is a memorable
illustration — but as evidence for "LLMs can be supported in producing
correct conclusions" it is an anecdote, not a result. The growth-model
claim (open contribution admitted by architecture, not authorship) is a
design intention, not an evaluated property; no external contribution
has passed the gate.

On honesty generally: this paper sets a standard. Every gameable number
I hunted (denominator shopping, acceptance-vs-conjoined, escape
denominators, TCB rows) has an explicit anti-gaming note, and several
past sins (96 vs. 95 denominators, 0/33 Sail-route composition) are
confessed in the text. My checks corroborate the honesty rather than
undermining it.

## 5. Related work

Coverage is good and fair: certified compilation vs. TV, credible
compilation as ancestor of re-establishment, the compositional-
simulation line (Compositional CompCert, Pilsner, CompCertO, DimSum)
with the support condition correctly situated as their congruence
requirement, K/Sail as consumed monocultures, N-version programming
with Knight–Leveson as the standing caution, certifying algorithms /
PCC / DRAT / cake_lpr, SV-COMP witnesses as the deployed form of the
asymmetry, ETB for heterogeneous evidence, and recovery blocks /
fail-stop for the systems vocabulary. Missing and worth adding:
**Why3** (one VC language translated to many provers — the closest
deployed "hub with heterogeneously trusted edges");
**Sledgehammer-style checked reconstruction** (untrusted discovery +
trusted replay is precisely Thm 4.8's pattern in a prover); SMT-COMP
**model/proof validation** practice; and ISA-conformance frameworks
(e.g., riscv-formal) as prior art for spec-enumerated construct
yardsticks.

## 6. Detailed comments

1. **[Major]** §4.6/§4.7: the mechanized Thm 4.9 absorbs clauses (iii)
   and the artifact-to-`IZ`-behavior link into hypothesis `hZ`
   (`EndToEnd.lean`), and clause (iv)'s `CommutesWithSpecialization`
   (`Specialization.lean`) is claimed "discharged by construction" per
   pair with no mechanical check I could find in
   `gurdy/pairs/*/translate.py` or tests. State explicitly, near
   `tab:mech`, which hypotheses of the universal theorem are *checked
   by nothing*.
2. **[Major]** §6 opening: scope the claim "Every number is regenerated
   by one script" — exclude `tab:bugs` (hand-curated) and `tab:player`
   (curated record of a manual protocol), and the escape experiment's
   intermediate-round numbers (§6.7 prose).
3. **[Major]** §6.8: acknowledge the arm-B grading circularity
   (platform-established ground truth, platform-mediated answers) in
   the limitations list; the current three limitations omit it.
4. **[Major]** §6.7: the mutation operators are derived from the
   incident catalog and the probes were hardened against escapes from
   this same experiment; "0 escaped" should be framed as "the gate now
   covers the seeded families" *in the table caption itself*, not only
   in prose three sentences later.
5. **[Minor]** `tab:branch` top block: column head "Route (to SMT-LIB)"
   is wrong for the SMILES row (target is molecular-formula), and the
   CRN/Python rows are acceptance-only (`conjoined=False` in
   `composed.json`) yet sit under a "Composed *conjoined* coverage"
   caption with no per-row marker (contrast `tab:capability`'s
   "per-run" marks).
6. **[Minor]** `tab:capability` caption says the reproducible C hop is
   "marked per-run"; the row actually shows "---" in all columns.
7. **[Minor]** §6 intro asserts pinned versions (btormc 3.2, cadical,
   drat-trim `2e3b2dc`, cake_lpr `a4323b2`) but `env.json` records only
   commit/python/platform/z3; the checker pins live in `REGISTRY.md`.
   Record the full engine inventory in `env.json` so the pin claim is
   itself regenerable.
8. **[Minor]** `bugs.tex` says "675 commits across all refs"; the
   repository now has 713 (`git rev-list --all --count`). A frozen
   mining date would keep this stable.
9. **[Minor]** "the platform's own suite passes 1204 tests": my run
   gives 1201 passed + 3 skipped (of 1204 ran). Say "runs 1204 tests (3
   host-dependent skips)".
10. **[Minor]** `native_btor2.py::decide_bounded`: "exit 0 + empty
    stdout+stderr = UNREACHABLE" is a fragile exhaustion signal; the
    checker adapters got negative controls after I19, but this
    adapter's exhaustion path has none (a btormc build that silently
    exits 0 on error would produce false unreach in the disjoint
    block).
11. **[Minor]** Def 3.2 claims purity "on every host"; the evaluation's
    twice-and-diff evidence is single-host (macOS/arm64). Either cite
    the dev-image cross-check or weaken.
12. **[Minor]** Appendix §B calls eBPF a "256-opcode … inventory slice"
    while the language-owned denominator is 126; the conclusion's "eBPF
    complete" is complete *against the declared slice*. Align the
    wording.
13. **[Nit]** `tab:perf` "warm 0.0 ms" — print "<0.1".
14. **[Nit]** `tab:bench` total row prints "78 & 78" where per-program
    rows print "8/8".
15. **[Nit]** Abstract "largely unsupervised" is glossed; §5.4's
    definition (human sign-off gate on shared-emitter edits) is the
    honest version — consider one clause in the abstract.
16. **[Nit]** "13 languages" counts molecular-formula as a language;
    defensible under Def 3.1, but the symmetry with "13 pairs" reads as
    marketing.

## 7. Questions for the author response

1. **Probe adequacy.** Def 4.6 rests on one (now two-instance) probe
   per construct. Beyond post-hoc hardening after escapes (I23), what
   principled adequacy criterion do the probes satisfy, and can you
   bound what "96/96 conjoined" implies for inputs unlike the probes?
2. **Diversity under LLM authorship.** Both diverse-prefix translators
   (and the interpreter) are same-family LLM products; MUL/ADD was a
   correlated misreading across two "independent" components. Have you
   run *both-leg* (common-mode) fault injection — the class §6.7 says
   single-leg mutation cannot model — even at small scale?
3. **Specialization obligation.** For `riscv-btor2` and the bridge,
   what concretely discharges `CommutesWithSpecialization` — a test, an
   argument in the artifact, or nothing beyond encoding structure? If
   nothing, does any current table depend on it?
4. **Non-extension updates.** The I21 fix (0.1→0.2) was not an
   extension. How many non-extension bumps occurred, and what did
   dependent-pair re-validation cost — i.e., how expensive is the
   ratchet discipline when it actually fires?
5. **Player experiment.** If arm B's platform run had contradicted the
   platform-derived ground truth, how would grading have resolved it?
   And do you have any pilot data on questions where arm A fails?
6. Would you commit, for the camera-ready, to scoping the "every number
   by one script" sentence and to per-row conjoined/acceptance marking
   in `tab:branch`?

## 8. Overall merit

**Grade: B−** (accept with reservations; I would not champion it
against a strong theory paper, but I would defend it against a claim
that its numbers or mechanization are unsound — I tried and failed to
break them).

**Expert confidence: high (4/5)** — I verified the artifact end to end
(Lean build + axiom audit, full test suite, all tables against primary
data, live regeneration of coverage / branch / disjoint /
certified-tier results, and the §3.2 worked example executed verbatim);
I am less certain only about POPL-fit calibration relative to this
year's pool.

**The two or three changes that would most raise the grade:**
1. **One result at scale or in the wild** — a binary-for-binary
   riscv-tests or SV-COMP-slice campaign in which a route disagreement,
   an unseeded escape, or an arm-A player failure actually occurs; the
   framework is built to localize failures, and the evaluation never
   shows it doing so outside its own history.
2. **Close the universal-verdict gap**: mechanize or mechanically check
   the specialization obligation per reasoning pair, and give the
   solver-artifact-to-target-semantics hypothesis (`hZ`) an explicit
   checked or tested surrogate — right now the theorem with the most
   practical weight has the least checked hypotheses.
3. **Tighten the claim boundary** (comments 2–5): scope the one-script
   claim, mark acceptance-only rows, state the player-grading
   circularity, and recaption the escape table — the paper's
   credibility is its greatest asset, and these are the few places
   where the rhetoric outruns the (otherwise verified) record.
