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

## Era 4 — the kernel (2026-08-05 → )

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
- Era 3 is not discarded but **mined**: its code (`gurdy/`, `pairs/`,
  `languages/`, `tools/`, `tests/`) stays in the tree as the quarry
  the carry-over wraps into `registry/` entries — first done for the
  btor2 interpreter and btormc (`runs/btor2-demo/`);
- at the 2026-08-13 reconciliation the vocabulary completed: **domain**
  (a root language plus its external anchors — the ungenerable half of
  the old kit) and **path** (one play of a route, logged with result,
  grade, and cost) join language, pair, route, and frontier as the
  first-class concepts, and the frontier renders as **board and
  graph** (`frontier.md`, `frontier.dot`), both pure functions of the
  log.

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
READMEs and docstrings under `gurdy/`, `pairs/`, `languages/`, and
`tools/` speak Era-3 vocabulary and cite the retired documents; they
are historical artifacts of the generation they document, mined rather
than maintained, and their citations resolve in git history.

## How the next entry gets written

A redesign lands as: the new specification in the tree, the removals
beside it, one era entry here naming what changed shape and why, the
tags/commits where the old state lives, and — where the change
invalidates a paper's claims — a note in the paper's README rather
than a silent edit. Between redesigns this file does not change;
day-to-day evolution is the registry growing, and the registry
carries its own history (append-only entries, admission evidence,
run logs).
