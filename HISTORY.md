# History — how hurdy-gurdy evolves

This file is the system's memory. The working tree carries only what
the current design needs — [`KERNEL.md`](./KERNEL.md) is the
specification, [`README.md`](./README.md) the entry point — and
everything a redesign retires is *removed, not rewritten*: git history
preserves every byte, this file preserves the story, and each era below
names its tags and the commit at which its documents were last present.
When the system changes shape again, the same discipline applies — a
new era entry here, removals in the tree, nothing silently edited into
pretending it was always so.

## Era 1 — rotor (before this repository)

Hurdy-gurdy descends from **rotor**, developed as part of selfie
([github.com/cksystemsteaching/selfie](https://github.com/cksystemsteaching/selfie),
`tools/rotor.c`). Rotor fixed one translation — RISC-V machine code to
BTOR2 — and hurdy-gurdy began as its generalization: not one
translation but a growing graph of them.

## Era 2 — v2: the pair generation (tags `v2-final`, `v2-final.1`)

The first platform generation: translation pairs between formal
languages, each checked by running both sides. Superseded whole by v3;
its final state is preserved at the tags.

## Era 3 — v3: the instrument (2026-06-16 → 2026-08-05)

Promoted to the repository root on 2026-06-16 (prior v3 history at tag
`v3-final`; the v2/v3 branches were deleted 2026-07-17). This is the
era the papers describe, and its shape was:

- **The calculus.** A pair = two languages with deterministic shared
  interpreters, a pure translator, a carry-back map, a declared
  projection, and a direction — closing a commuting square checked per
  program. Contracts (assurance, direction, kept observables, cost)
  compose along routes by the componentwise meet. Untrusted LLM
  authors, trusted answers: existential answers certified by witness
  replay, universal answers graded. Mechanized in Lean under
  `paper/mechanization/`.
- **The spine and the fan-out.** The C–RISC-V–BTOR2–SMT-LIB spine
  audited complete for RV64IMC (2026-06-21); every registered pair
  brought to at least partial across ~15 pairs (2026-06-22),
  including field-blind corners (chemical reaction networks, SMILES)
  as the domain-genericity existence proof.
- **Autonomy at scale.** The SCALING program (complete 2026-07-12):
  builder agents, a two-sided gated admission (negative controls both
  ways), a sandboxed pure-oracle seam, a merge queue in propose mode,
  and graduated autonomy earned on shadow ledgers.
- **The frontier program.** Merged 2026-07-17: answerability as a
  five-condition filtration, saturation as a decidable per-benchmark
  fixpoint, six facilitation theorems (F1–F6) with the compositional
  core in Lean, demand recorded on books and aggregated into frontier
  pairs with required contracts, registration held behind a human
  valve (with a scoped mandate as its delegated instantiation), and a
  third lane for solver synthesis behind its own gate.
- **The campaign.** The pre-registered HWMCC protocol ran seven
  iterations over the pinned 110-question `hwmcc-sosylab-beem` suite
  (2026-07-18 → 2026-07-28, ledger at
  `paper/frontier/results/hwmcc-sosylab-beem/`): 82 of 110 ever
  answered, four at every depth, the terminal board holding one
  in-set entry (`native-procedure`, 29 citing questions), not
  saturated, the host's engine enumeration closed — btormc,
  btor2-havoc CEGAR, pono (nine modes), AVR, msat-ic3ia, and ABC's
  PDR, whose last-member closures of two long-resistant pins were the
  campaign's controlled experiment.
- **The papers.** The instrument paper — *Untrusted Authors, Trusted
  Answers* — submitted to POPL27 (2026-07-03, rejected on formatting
  2026-07-17, preserved at tags `popl27-*`) and published as the
  arXiv preprint (v2 = tag `arxiv.2`), including the directional
  square and the player-v2 separation (unaided LLM 7/8 vs. the same
  model over the platform 8/8). The frontier paper
  (`paper/frontier/`) states the frontier problem, F1–F6, the domain
  kit K1–K4, the campaign status, and — re-cut 2026-08-05
  (`4b17542`) — closes with the discovery program.
- **The turn.** The campaign's structural finding (worked out in
  `DISCOVERY.md` and `INVERSION.md`, and distilled into the frontier
  paper's closing section): every artifact the loop could build was
  meaning-preserving by construction, so the loop was conservative
  over truth — it discovered instruments, never facts — and the
  commuting square has four unknowns of which the platform only ever
  solved for the translation. That analysis, plus the judgment that
  the accumulated machinery had grown too complicated, forced Era 4.

## Era 4 — the kernel (2026-08-05 → 2026-08-14; tag `era4-final`)

Designed fresh on branch `dev`, prioritizing simplicity, learning
from Era 3 ([`KERNEL.md`](./KERNEL.md), first landed at `838489d`);
reconciled onto `main` 2026-08-13. The moves:

- translation and solving are **one kind of edge**; a solver pair's
  target is the result;
- **results are the only currency** — witness / all(bound) / partial —
  and the frontier of a benchmark is its non-terminal results;
- certification is Λ-then-check on both sides, with the strict grade
  ladder *claimed < checked < certified* (certified = re-discharged at
  the source, route-independent);
- the LLM runs autonomously until a human pulls the plug, and **never
  writes a result** — only the kernel does, by running checked code;
- conjectures go **semantics first**: (a) decision procedures, then
  (b) translation, then (c) languages — new syntax earned by
  demonstrated semantics;
- the kernel is small, hand-written, and proved
  (`kernel/mechanization/`); everything else is generated content
  admitted through one gate;
- Era 3 is not discarded but **mined**: its code stays in the tree as
  the quarry the carry-over wraps into `registry/` entries — first
  done for the btor2 interpreter and btormc (`runs/btor2-demo/`);
- at the 2026-08-13 reconciliation the vocabulary completed: **domain**
  (a root language plus its external anchors — the ungenerable half of
  the old kit) and **path** (one play of a route, logged with result,
  grade, and cost) join language, pair, route, and frontier as the
  first-class concepts, and the frontier renders as **board and
  graph** (`frontier.md`, `frontier.dot`), both pure functions of the
  log;
- the 2026-08-14 debloat finished the mining: everything Era 3 had as
  a *mode of operation* — the `gurdy` CLI and its players, the MCP
  server, the route/grade/frontier machinery of `gurdy/core/`, the
  `tools/` orchestration, the `pairs/`/`languages/`/`benchmarks/` doc
  dirs, and their tests (~29K lines) — left the tree for git history,
  because the kernel is the only mode machinery now (two modes:
  `driver play` over a benchmark, `driver admit` for a hand-written
  entry). What Era 3 had as *pair semantics* was carried through the
  gate instead of deleted: `aarch64`, `crn`, `c`, and the abstraction
  spec language `btor2-spec` joined the registry as languages, and
  `aarch64--btor2`, `aarch64--sail`, `crn--smtlib`, `c--riscv`, and
  the first two directional (`over`) pairs `btor2-spec--havoc` /
  `btor2-spec--interval` as pairs; `gurdy/` remains in-tree as the
  imported library those entries wrap, tested but no longer a mode.

### The 2026-08-05 documentation reconciliation

With Era 4 the Era-3 design documents were removed from the tree
(this commit; last present at `838489d`, and still carried in full on
branch `main` — recover any with `git show 838489d:<NAME>.md`). What
each was, and where its living content went:

| removed | what it was | superseded by |
|---|---|---|
| `ARCHITECTURE.md` | the pair: six components, the square, determinism | `KERNEL.md` §1–2; the instrument paper |
| `ROUTES.md` | routes, contract meet, bounded claims | `KERNEL.md` §1, §3 |
| `SOLVERS.md` | reasoning languages, witness checking, canary discipline | `KERNEL.md` §2; carried into `registry/pairs/*/solve.py` |
| `REGISTRY.md` | the v3 registry model | `kernel/registry.py`; `KERNEL.md` §9 |
| `PAIRING.md`, `FRAMEWORK.md` | the v3 pair-implementation contract and shared layer | `KERNEL.md` §9 executable contracts |
| `AGENTS.md` | human registration, per-pair agents, the valve | `KERNEL.md` §4 (no valve; the gate + plug-pull) |
| `SCALING.md` | builder autonomy, merge queue, sandbox seam | `KERNEL.md` §4, §9 (sandboxed runner; one gate) |
| `BENCHMARKS.md` | pinned ingestion, coverage vs. triviality | `KERNEL.md` §3, §10; two-sided controls |
| `INTERFACE.md` | the LLM-facing player surface (MCP) | `kernel/driver.py` CLI; a machine surface returns when the loop needs it |
| `DOMAINS.md` | domain-genericity of the v3 platform | the frontier paper's kit (K1–K4) |
| `FRONTIER.md`, `FRONTIER-PLAN.md` | the frontier program: story and plan | the frontier paper; `KERNEL.md` §3 (frontier = non-terminal results) |
| `SYNTHESIS.md` | the procedure lane and solver gate | `KERNEL.md` §2 (one gate for every pair) |
| `PROVING.md` | how proofs would be demanded | `KERNEL.md` §6 (Lean obligations in manifests) |
| `DISCOVERY.md`, `INVERSION.md` | the discovery program and the four unknowns | the frontier paper §8; `KERNEL.md` §4 (the conjecture order) |
| `POTENTIAL.md` | the ceiling: five obstacles, anchor scarcity, directional squares | the instrument paper; `KERNEL.md` §2, §5 (roots cost trust) |
| `HANDOFF.md` | cross-machine work transfer | retired with the workflow that needed it |

`DOCKER.md` stays in the tree: the pinned toolchain image is the
reproducibility substrate in every era — kernel-era solver pairs
declare engines this image pins.

The instrument paper (`paper/`, the arXiv preprint at tag `arxiv.2`)
is untouched: it is the published, citable record of Era 3 and
references the retired documents by their historical names on
purpose. The frontier paper (`paper/frontier/`), never published,
moves with the design: re-cut 2026-08-06 for the kernel
architecture, with its Era-3 form (filtration, F1–F6, kit, valve)
preserved whole in git history at `4b17542` and accounted for
theorem by theorem in the paper's own §6. The same holds inside the quarry — the
docstrings and SPEC files under `gurdy/` speak Era-3 vocabulary and
cite the retired documents; they are historical artifacts of the
generation they document, mined rather than maintained, and their
citations resolve in git history.

## Era 5 — v5: generated whole (2026-08-14 → 2026-08-19; tag `era5-final`)

Designed fresh **from the initial commit** on branch `v5` (31
commits), keeping Era 4's vocabulary — results as the only currency,
one gate, two modes, the frontier as the non-settled remainder — and
adding the rule that justified a fresh lineage rather than an
increment: **every implementation is generated, in Python; there are
no existing tools inside the system.** Era 4's registry had wrapped
eight engines and imported the Era-3 library; Era 5 owned its
endpoints. The moves:

- **Terminals.** The stop of a route became a registered kind: a
  generated solver bundled with its generated certifiers (`Λ` for
  witnesses, `discharge` for certificates), admitted through the same
  gate as pairs — witnesses must replay, certificates must discharge,
  mutants must fail, determinism must hold.
- **The generation rule enforced in layers**: no manifest field can
  point at a tool; the runner is sealed (own process, empty
  environment, temporary directory, wall cap; every check run twice
  and byte-compared); every implementation is committed source.
- **Accelerators**: an entry may ship one re-implementation in a
  performance-oriented language, admitted only by byte-agreement with
  its Python reference on every admission invocation; the reference
  stays the semantics, and checks are never accelerated. The bounded
  checker's C mirror (`btor2-bmcf`) ran about 23× its reference and
  was revised three times, its caps learning the mirror's pace.
- **Revision, not mutation** (`653457e`): admitted entries are
  content-pinned; extension arrives as `<name>@<r>` with a
  conservativity obligation — byte-agreement with the predecessor on
  its whole checkable surface. `btor2@2` (signed division) and
  `btor2@3` (arrays) were the first uses; retired entries — the
  cone-of-influence self-pair, the reference bounded checker — were
  pruned with their evidence banked.
- **The language of state** (`dda6a73`): solver progress as a derived
  language over btor2 — claims that carry their own checking plans —
  with the strengthening square as a self-pair; the experiment Era 6
  generalized into evidence languages.
- **Domains own nothing**: every admitted pair and terminal serves
  every domain; the gate, not topical relatedness, is the only
  membership test — first stated here, kept since.
- **The hardware campaign.** HWMCC'24's bit-vector track swept in
  tiers, every file sha256-pinned with the official verdict it was
  selected under: `hwmcc24-mini` (74 questions, 46 settled),
  `hwmcc24-arrays` (55, 5 settled), `hwmcc24-mid` (80, 45 settled) —
  by five generated terminals: random simulation, bounded model
  checking with its mirror, k-induction, IC3, and binary decision
  diagrams written from the format's semantics alone as the first
  disjoint lineage, so that `corroborated` could fire (`587c8ca`:
  five verdicts carried the flag).
- **The software campaign.** A C interpreter admitted on twelve
  vectors and the recorded testimony of clang — 1045 verdict
  agreements on random recorded-tape stimuli over the in-fragment
  SV-COMP corpus, the compiler that never entered (`d92a6cc`); the
  C→BTOR2 pair, 1188 squares held and five mutants refused; and
  `svcomp25-mini` (79 questions from a competition of 33 verifiers,
  26 settled): fourteen bugs walked home across the bridge and
  replayed in C, three loops proven safe at bound infinity.
- **The lesson that forced Era 6.** Witnesses crossed the bridge
  home; proofs could not: a k-induction certificate found at BTOR2
  discharged there (*checked*) but had no road back to C
  (*certified*), because the correspondence every translator computes
  was discarded at the kernel boundary. And the trust story kept two
  textures — squares judged translation empirically while terminals
  pronounced verdicts on their own admitted word, the one node in the
  graph with no interpreter.

## Era 6 — v6: judged whole (2026-08-20 → ; tag `era6-campaign-1` at the consolidation)

Designed fresh **from the initial commit** on branch `v6` (22 commits
to the consolidation), keeping both Era 5 rules and finishing the
thought: **generation produces syntax; only interpretation produces
truth.** There is exactly one semantic device, the interpreter, and
exactly one trust event, an interpreter run judging a transported
artifact. The moves:

- **Two kinds only**: language (syntax + interpreter + evidence
  schemas) and transport (total: `T`, `Λ`; partial: search).
  Terminals dissolve into searches that *write* evidence and
  pronounce nothing; the graph is homogeneous — every node
  interprets, every edge translates.
- **Channels** (`prog`, `wit`, `obs`, `claim`, `cert`, `hint`): one
  artifact kind, one direction, one named arrival check — always an
  interpreter run. The square is the `prog` channel's arrival check,
  not a primitive; `claim` is the checkless channel and floors at
  *claimed* by construction.
- **Evidence languages**, induced never written: witness schemas free
  for every language (replay is the judge), certificate schemas
  declared per language with generated checkers — the judges; the
  trusted base is exactly the admitted judges, printable as a list.
- **Grades as geometry**: gap = hops to the last arrival check;
  *certified* = gap 0 as a theorem; each arrival check removes
  everything upstream from the trust meet; `regrade` re-discharges
  stored certificates closer to home — the map re-graded without
  being re-solved.
- **The ledger**: witness surprisal, cleared bits, certificate length;
  per-channel conversion rates (dilution, surprisal shift, inflation,
  bound rescale); profiling, never a grade; piloted retroactively on
  Era 5's logs before being written into the design.
- **Oracles, not organs** (`a509ec9`): an existing tool may testify at
  admission, entering only as anchors with provenance — never the
  trusted base, never a play.
- **`POTENTIAL.md`**: every tool boundary is three boundaries in one —
  trust, information, optimization — and owning the implementations
  pulls them apart: tools as instruments, as conjectures, boundaries
  as seams, semantics as writable, the base as an object of science.
- **The first campaign** (2026-08-29 → 08-30): the hardware domain
  and the BTOR2 interpreter; the naive search settling six of
  seventy-four by replay alone; bounded model checking with its C
  mirror; the software domain and C; RISC-V as the middle vertex,
  anchored by no domain and corroborated only by squares on both
  sides; the triangle C→BTOR2, C→RISC-V, RISC-V→BTOR2; the
  `induction` and `clauses` schemas on BTOR2 with the searches that
  write them; C's own `induction` judge, rebuilt by the RISC-V road;
  arrays reaching the judges. Boards: `hwmcc24-mini` 43 of 74 — 14
  universal answers *certified* at gap 0 by judges alone, one of them
  officially unsolved; `svcomp25-mini` 26 of 79 — 14 witnesses
  certified at C, four proofs lifted to *certified* at C by `regrade`
  without re-solving, one about a 2048-cell array. No `corroborated`
  flag, honestly: every route shared the C front end and one
  generator.

### The 2026-09 consolidation — one branch again

Three branches — `main` (Eras 1–4), `v5`, and `v6` — shared only the
initial commit. The consolidation made Era 6's tree the tree of
`main` by one merge commit with three parents (`main`, `v5`, `v6`),
so that every commit of every era is reachable from `main`, the
first-parent history reads as the era succession, and the tree is
Era 6's small one. Tags mark the last state of each lineage:
`era4-final` (`c46ec0b`), `era5-final` (`e6ac2f8`), `era6-campaign-1`
(`11dbf40`); the `v5`, `v6`, and `dev` branches were deleted after
the merge. Nothing was rewritten. What returned to the tree returned
as documents or data — never as code, because under Era 6 the kernel
is the only hand-written code and everything else enters through the
gate:

| from | what it was | where it lives now |
|---|---|---|
| `HISTORY.md` (main) | this file | returned, extended with Eras 5–6 and this section |
| `paper/`, `video/` (main) | the instrument paper (arXiv, tag `arxiv.2`), the frontier paper, results, the explainer | returned as documents; each paper's README names the era it describes |
| `Dockerfile`, `DOCKER.md` (main) | the pinned toolchain image | returned as `oracles/bench/` — the oracle bench: pinned engines that testify at admission and never run in a play (`KERNEL.md` §6) |
| `kernel/mechanization/Kernel.lean` (main) | the Era-4 proofs (result order, ratchet, once-terminal) | returned as the seed of Era 6's mechanization; the gap and trust-meet obligations (`KERNEL.md` §9) still to prove |
| `registry/` (main) | 14 languages, 23 pairs, 8 of them wrapping engines | tag `era4-final`; its `vectors/` and `corpus/` directories — the same format Era 6 uses — extracted as **anchor packs** under `oracles/packs/` with provenance, for the loop to regenerate each language against |
| `gurdy/` (main) | the Era-3 library the Era-4 entries imported | tag `era4-final`; run one last time at the tag to pin pack observables; never imported again |
| `tools/` (main) | fuzz harnesses comparing riscv and sail against outside oracles | tag; the recipe survives as oracle testimony about transports (`KERNEL.md` §6) |
| `mini/`, `tests/`, `scripts/` (main) | the K1 bootstrap evidence, the Era-4 suite, helpers | tag; superseded by Eras 5–6's actual bootstrap from empty and by the gate itself |
| `paper/frontier/results/hwmcc-sosylab-beem/` | the Era-3 campaign ledger, 110 questions | stays with the paper; its engine verdicts are labels for a third hardware benchmark |
| `registry/terminals/btor2-bdd` (v5) | the second-lineage BDD search | tag `era5-final`; regeneration as an Era-6 search is named work |
| `runs/hwmcc24-arrays`, `runs/hwmcc24-mid` (v5) | pinned tiers, 55 and 80 questions | carried forward pinned, logs empty, to be played under Era 6 |
| `registry/languages/state`, `pairs/state--*` (v5) | solver state as a derived language | tag; generalized by evidence languages |
| Era 5 logs | the ledger pilot's data | tag `era5-final` |

The consolidation also made three doctrine edits, recorded in
`KERNEL.md` rather than here: oracle testimony gained its second use
— relative performance, recorded beside cost and never ranked — and
its dispute record (§6); the frontier gained its second layer, the
capability frontier drawn from the registry alone (§5); and the
conjecture order regained what Era 6 had dropped from Era 5 — routes
into unrelated domains — sharpened into the hub rule (§7–8).

## How the next entry gets written

A redesign lands as: the new specification in the tree, the removals
beside it, one era entry here naming what changed shape and why, the
tags/commits where the old state lives, and — where the change
invalidates a paper's claims — a note in the paper's README rather
than a silent edit. Between redesigns this file does not change;
day-to-day evolution is the registry growing, and the registry
carries its own history (append-only entries, admission evidence,
run logs).
