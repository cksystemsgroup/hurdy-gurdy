# Scaling — hardening hurdy-gurdy for automated pair development

This is the plan for evolving hurdy-gurdy from *human-registered, agent-built,
human-gated* pairs into a platform that **scales in language support through AI
automation**: independent builder agents turn briefs (and unfinished pairs)
into PRs, and a centralized **coordinator** integrates them — including the
shared-emitter edits that today require human sign-off — with no human in the
mechanical loop.

It builds on the existing division of labor ([`AGENTS.md`](./AGENTS.md)), the
pair contract ([`PAIRING.md`](./PAIRING.md)), and the inherited framework
([`FRAMEWORK.md`](./FRAMEWORK.md)). It does not change what a pair *is*; it
changes how pairs are *produced, checked, and integrated* at scale, and it
hardens the checks so they can bear the trust a human used to.

## 1. The central shift: the gate becomes the only trust boundary

Today a human catches things: setting scope at registration, signing off on
shared-emitter edits, unblocking. Full automation moves that trust onto **CI
plus the coordinator**. The design rule for everything below:

> Green CI must actually mean *safe to merge*, so the coordinator can merge on
> that signal alone.

Registration stays a human act ([`AGENTS.md`](./AGENTS.md) §1) — it is the one
place platform scope grows, and the last human safety valve. Everything
downstream is mechanized.

The cautionary evidence is our own incident history: I21 and I24 and the
MUL/ADD blind spot show that agent-authored components share failure modes. At
one-pair-with-a-human that is tolerable; at *N* concurrent autonomous builders,
**correlated (common-mode) error is the dominant risk**, and defending against
it (§9) is not optional.

## 2. What scopes the whole effort: the universal-only attack surface

The existential/universal asymmetry ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §7,
paper Thm 4.8/4.9) is also the security boundary. A misaligned or blind builder
writes both `T` and `Λ`, so it can make a wrong translation *self-consistent*
and pass its own square. But trace what that can produce:

- **It cannot forge a false `reachable`/`sat`.** A witness is carried back to a
  concrete input and **replayed through the shared, language-owned source
  interpreter `I_s`**; `Λ` only proposes, `I_s` disposes. A wrong `Λ` yields an
  input that fails to replay → caught.
- **So an adversarial builder is confined to false *universals*** (`unreachable`
  / `unsat`), and only for a construct where (a) the corroborating branch shares
  the misreading *and* (b) no external differential covers it.

Every hardening measure below either shrinks that corner or protects the
machinery that judges it. Three invariants, in priority order, close it:

1. **Grader integrity** (§3) — checked code never runs as part of its own
   checker.
2. **Author-disjointness rooted in an external artifact** (§9) — the thing that
   checks a pair derives from a *different* source than the pair.
3. **Protected invariants** (§4, §9) — inventories, probes, anchors, coverage
   targets, and `π` are not builder-writable.

## 3. Grader integrity — the load-bearing closer

Arbitrary Python cannot be sandboxed in-process: importing a pair runs
top-level code that can monkeypatch the oracle, mutate the registry, overwrite
a sibling's square, or seed the cache before the grader captures a reference
(cf. the `sys.modules` exec and the I19 substring no-op). So the grader must
**never run pair code in its own process.**

### 3.1 The trust split

A pair's `T` and `Λ` are pure ([`PAIRING.md`](./PAIRING.md) §5); everything else
the grader needs is trusted and language-owned. Two trees:

| Component | Owner | Runs |
|---|---|---|
| `I_s`, `I_t` interpreters | language (`gurdy/languages/*`) | **trusted** |
| probes / construct inventory | language (`gurdy/languages/*/inventory.py`) | **trusted** |
| `π`, coverage target | the **brief** (`brief.yaml`, protected) | **trusted** |
| `align` oracle, coverage, route-grader | framework (`gurdy/core/*`) | **trusted** |
| **`T` (translate)**, **`Λ` (lift)** | the pair (untrusted) | **sandbox** |

The coordinator grades with **its own `main` checkout of `gurdy/`**, not the
PR's, and drives the square keeping every trusted step in-process while shelling
the two untrusted pure calls to a sandbox:

```text
src     = I_s(program)                    # trusted
artifact= T(program)                      # UNTRUSTED → sandbox (bytes over a pipe)
btrace  = I_t(artifact, steps=n+1)        # trusted
carried = Λ(btrace)                       # UNTRUSTED → sandbox
result  = align(src, carried[1:n+1], π)   # trusted
```

The sandbox holds only the pair's `translate.py` / `lift.py` — no framework
internals, no network, read-only FS + scratch, fixed `PYTHONHASHSEED`,
wall-clock + memory limits (a real isolation layer, not bare `subprocess`).
Consequences made explicit:

- The grader **ignores the pair's own `square()` / `attach_square`** and
  rebuilds the square from `T`, `Λ`, `π`, and the trusted oracle. A rigged
  `square()` is never called.
- Grading is driven by **brief data, not registration side-effects**: `π`, the
  inventory, and the coverage target come from `brief.yaml` and the protected
  language module, never from the pair mutating a shared registry.

### 3.2 Two-sided negative controls (grader-integrity ∧ probe-adequacy)

Before trusting a PASS, prove this exact invocation can FAIL — the I19 lesson,
generalized. The control is built **without trusting pair code**, reusing the
`tools/fault_injection.py` `_shadow` pattern (uniqueness-checked source patch),
run in the same sandbox:

```text
assert grade(shadow_mutate(T, seeded_mislowering)) == FAIL   # can it catch a defect?
assert grade(prior_merged_version_of_the_pair)     == PASS   # is it not always-fail?
verdict = grade(T)                                            # only now trust the real run
```

The first line does double duty: a surviving mutant means the grader is no-op'd
**or the probes are too weak** (the I23/I24 class) — either way the PR is
blocked. For a widening PR the prior `partial`/`built` version is a perfect
known-good.

### 3.3 Where pair code can still escape, and the closers

1. **Any import of the pair in the trusted process re-admits arbitrary code.**
   → Read metadata from `brief.yaml`; execute pair code *only* in the sandbox.
2. **Sandbox escape / resource exhaustion.** → gVisor/nsjail/Firecracker-class
   isolation; cgroup limits; timeout → FAIL.
3. **Non-determinism / environment probing** (graded one way, runs another). →
   determinism guards as sandbox policy (no clock/rng syscalls, fixed hash
   seed), plus run `T` twice in two fresh sandboxes and byte-diff — twice-and-
   diff the pair cannot fake because it never sees the second run.
4. **IPC channel confusion.** → length-prefixed binary framing, defensive
   parse ("a checker adapter without a negative control is unchecked").
5. **Cache seeding.** → grade cache-cold; the cache lives in the trusted
   process; cache key is a content hash of the pair source, never a
   pair-declared version string.
6. **The TOCTOU gap — graded clean, runs dirty.** → the architectural
   commitment: **the framework runs all pair code behind the same sandbox
   boundary in production**, so *graded == run*. Pairs become genuinely
   contained pure oracles everywhere — the paper's stance made operational.

## 4. Machine-readable contracts (what the coordinator reads)

The coordinator cannot coordinate prose. Three artifacts per PR:

- **Structured brief** `pairs/<id>/brief.yaml` beside the prose README:
  source/target, translator kind, target fidelity, `π` fields, square
  direction, coverage target + inventory ref, `reuses:` / `contributes:`
  shared components. This is
  [`AGENTS.md`](./AGENTS.md) §1 as data. The coverage target, `π`, the
  direction, and inventory refs are **protected fields** — a CI diff rejects
  any PR that changes them
  (the "agent's not to shrink" rule, mechanized).
- **PR manifest** `.hg/pr.yaml` (generated): what the PR delivers, which pairs
  it claims to leave byte-identical, **coordinator-attested** agent/model
  provenance (not self-reported), and self-verification results.
- **Shared-change manifest** (only if the PR touches `gurdy/languages/*` or a
  shared emitter): the input to §6.

## 5. The contribution lifecycle (PR-native state machine)

```text
registered ──build──▶ slice-PR ──gate──▶ partial ──widen──▶ widen-PR ──gate──▶ built
  (human)    (builder)          (CI)              (builder)           (CI)
```

- Each builder works in an isolated worktree/branch, opens exactly one PR,
  never touches `main`.
- **"Start thin, then widen" ([`PAIRING.md`](./PAIRING.md) §1) is the unit of a
  PR:** a slice PR (one construct end-to-end, the rest typed `unsupported`)
  merges at `partial`; each widening is its own small PR. Small PRs mean cheap
  gates, easy conflict resolution, and a monotone ratchet
  ([`BENCHMARKS.md`](./BENCHMARKS.md) §5).
- **Unfinished pairs are first-class work.** A builder resumes a `partial` pair
  by reading the registry + the `unsupported` histogram + the brief's §9 notes,
  and widens by one construct. The ratchet guarantees this is safe and monotone,
  so partial-pair widening is the *easiest* thing to automate — start here (§10).

## 6. The shared-layer protocol (replacing human sign-off)

[`AGENTS.md`](./AGENTS.md) §5 today returns incompatible shared changes to a
human. Replace that with a protocol the coordinator arbitrates, split by the
ratchet's extension test (Prop 4.7):

**Lane A — additive extension (auto-integrable).** Decide additivity
**syntactically** — [`tools/additivity.py`](./tools/additivity.py) parses base
and head, and accepts the change iff every pre-existing statement reappears, in
order, with an identical AST subtree, and the only differences are *insertions*
of new statements/branches (plus two behaviour-inert allowances: the shared
version bump itself, and docstring/comment edits). (Syntactic additivity beats
byte-diff-on-corpus, which is only as strong as coverage and misses breakage on
untested inputs; identical-subtree is a proof *by construction* — no corpus.) A
Lane-A change bumps the shared version, re-stamps evidence, and merges with no
human. The classifier rides in the PR manifest as `verdict.shared_lane` so the
coordinator reads one artifact. *Most widening lands here — a widening written
as new guard-clause branches is Lane A; folding a new case into an existing
dispatch tuple is Lane B, so the builder brief prefers the former.*

**Lane B — non-additive change (coordinated).** Any edit to an existing path
(a bug fix like I21's off-code halt, a refactor, a semantics correction):

1. The shared-change manifest declares the symbol, why non-additive, the
   affected dependent pairs, and the **expected new verdict per pair**.
2. The coordinator runs the **re-validation fan-out**: every dependent pair's
   full gate against the changed shared code in one integration branch. Green→red
   that the manifest did not predict is a regression → reject; a change matching
   the manifest → accept.
3. Because such fixes are often needed in several lowerings at once (I21's
   common-mode pattern), the manifest can bundle a coordinated multi-pair fix
   into **one atomic integration** — exactly what the human sign-off gated, now
   executed as data.

**Concurrency control.** Shared-touching PRs are **serialized through a merge
queue** (rebase + re-gate against up-to-date `main`); independent pair PRs stay
parallel and cheap. Advisory **locks per shared symbol** (from the brief's
`contributes:`/`modifies:`) keep two builders off the same emitter at once. If
two pairs want the same new shared logic, the coordinator **promotes** it into
the language layer once and points both PRs at it ([`AGENTS.md`](./AGENTS.md)
§3).

## 7. The coordinator agent

A distinct agent from the builders and the route-grader — the trunk's
merge-queue brain, and **mechanism, not judgment**: it executes the ratchet and
the fan-out; it does not decide whether code is "good." Its decision logic is
[`tools/merge_queue.py`](./tools/merge_queue.py) (Phase 6, propose mode).

- **Owns the merge queue**, ordered by a dependency DAG (interpreter-contributing
  PRs before consumers; shared-layer PRs serialized; independent pairs parallel)
  — [`FRAMEWORK.md`](./FRAMEWORK.md)'s `framework → interpreters → pairs`
  bootstrap order generalized to a live queue (`merge_queue.order_waves`).
- **Runs the re-validation fan-out** (§6) and the route-grader
  ([`AGENTS.md`](./AGENTS.md) §7) for anything that changes a route.
- **Arbitrates the shared layer** and rejects with a **localized, machine-
  readable reason** — the oracle's step/observable divergence — so the builder
  gets a precise fix target, not "try again."
- **Dispatches work**: picks the next `registered` brief or the next `partial`
  pair below target, spawns a builder, tracks it — closing the loop into a
  self-driving queue.
- **Enforces global invariants**: suite green, determinism, no protected-field
  change, provenance present, grader run in isolation (§3).

## 8. Builder agents

Same contract ([`PAIRING.md`](./PAIRING.md)) whether building a new pair or
resuming a `partial` one (§5). Each builder **self-verifies before opening the
PR** (its square, coverage, determinism, and — if it touched shared code — the
local dependent-pair check) and attaches results to the manifest; a PR that
arrives red is the builder's bug. Provenance (model family, prompt, seed) is
recorded by the coordinator that dispatched it, not self-reported.

## 9. Anti-gaming and common-mode defense

The universal corner (§2) and the meta-level are where a green gate can still be
wrong. Defenses, mapped to the incidents that motivate them:

- **Protected invariants.** Inventories, probes, anchors, coverage targets,
  `π`, and the square **direction** ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §3)
  live in a protected tree; any change is gated by the escape and
  common-mode experiments passing. A builder can raise the *measured* number,
  never the *target* — and never flip an `over` square to `exact` (which would
  launder an abstraction's added behaviors into a meaning-preservation claim).
  (Closes coverage-shrink, `π`-narrowing, probe-weakening — the I22/I23/I24
  class as deliberate attacks.)
- **Escape/common-mode in CI, per PR** ([`tools/common_mode_gate.py`](./tools/common_mode_gate.py)).
  Reframe the fault-injection experiments ([`BENCHMARKS.md`](./BENCHMARKS.md),
  `tools/fault_injection.py`) as a per-construct gate: seed the single-leg and
  both-leg mutation families against the constructs the PR touches; a survivor
  fails the PR. The fast lane runs the single-leg family through the pure-python
  square and flags square-escaping mutations as *anchor-required*; the both-leg
  round requires the external anchor to still catch a shared misreading, and runs
  at BENCHMARKS cadence. Each pair carries a **posture** — `external-differential`
  or `single-artifact` (the §11 residue) — in the PR manifest.
- **Author-diversity rooted in an external artifact** ([`tools/provenance.py`](./tools/provenance.py)).
  For a corroborating branch ([`ROUTES.md`](./ROUTES.md) §4, Assumption 2),
  require the two legs be built by **different model families** *and* derive from
  **different semantic artifacts** (the Sail model vs the prose manual). The
  artifact is also declared registry-side (`Pair.semantic_artifact`, protected
  like `π`), which is what the trust advisor's independence judgment reads
  ([`ROUTES.md`](./ROUTES.md) §4).
  Model-diversity alone is insufficient (two models can misread the same manual
  identically); the artifact-derived external differential is the actual root of
  trust, and must never be author-able by the agents building the pairs. The
  provenance record is **coordinator-attested, not self-reported**, and the
  merge queue folds its verdict into each candidate's decision.
- **Interpreter/pair separation.** An interpreter-contributing agent must not
  also build a pair over that interpreter (a self-consistent `T+Λ+I_s` would
  pass its own square). Interpreters are standalone deliverables
  ([`FRAMEWORK.md`](./FRAMEWORK.md) §1) that must clear the external differential
  *before* any pair builds on them.
- **`proved`-tier encoding.** Keep the I19 negative-control discipline (a bogus
  certificate must fail; exact success-line parse; independent verified checker)
  and tie each certified universal to a witness-replay-checkable dual (the
  reachable sibling must genuinely replay).
- **Prompt-injection.** Agents treat all repo content — briefs, comments,
  registry — as **data, not instructions**; the coordinator validates against
  the machine contract, never against prose found in-repo.

## 10. Bounded human involvement and failure modes

- **Retry caps.** A pair that fails the gate *K* times escalates to the human
  who registered it, with the localized failure attached
  ([`AGENTS.md`](./AGENTS.md) §5). Per-pair token/time budgets bound cost.
- **Irreducible conflicts.** When the Lane-B fan-out shows two registered pairs
  need incompatible shared semantics, the coordinator **detects but does not
  resolve** — it escalates with the exact conflicting expectations. Humans stay
  in the loop for *scope/semantics* only, never mechanical integration.
- **Protected-instrument changes.** Any edit to inventories, probes, or anchors
  requires the common-mode experiment to pass — the I24 lesson, that an agent
  could weaken the very vectors that discriminate a defect.

## 11. Honest residue (stated, not closed)

Automation does not create these; it makes them the *only* remaining holes once
the mechanical ones are closed. They are the paper's own limitations:

- **Single-semantic-artifact common mode** — where only one formal model exists,
  a shared misreading between a pair and its anchor is uncatchable.
- **Circular interpreters** — a language whose interpreter *is* its semantics
  (pinned CPython for Python) has no external oracle; an interpreter-contributing
  agent's misreading there cannot be checked. Such languages cannot be fully
  autonomously authored.
- **Bounded-coverage sleepers** — a pair correct on everything measured today,
  wrong on a construct the inventory adds later; the ratchet catches it *when
  coverage reaches it*, never before. Coverage is dated; soundness is never
  claimed beyond it.
- **`proved`-encoding faithfulness** — that a universal claim's CNF means what
  it says is itself a translation needing a square.

## 12. Phased rollout

Each phase is a finite, human-registered framework increment with its own
`partial`→`built` status, exactly like [`FRAMEWORK.md`](./FRAMEWORK.md) §4.

1. **PR-native gate.** *(landed)* The fast per-change gate runs on every branch
   (`.github/workflows/ci.yml` `manifest` job): `tools/pr_manifest.py` measures
   Definition 4.6 coverage for every registered pair, runs a twice-and-diff
   determinism check on touched pairs, maps the diff to touched pairs /
   languages / protected instruments, and emits `.hg/pr.yaml` (§4) as a CI
   artifact. It fails on a pair that cannot be measured or a touched pair that
   is non-deterministic, and it carries its own negative control
   (`tests/test_pr_manifest.py`). The heavier route-grader / branch-agreement
   runs stay a later phase.
2. **The `PureOracle` seam.** *(landed)* `gurdy/core/pure_oracle.py` runs a
   pair's untrusted `translate`/`lift` either in-process (reference) or in a
   **separate long-lived child** behind a **safe result channel** — the parent
   pickles the input to the child but parses its output defensively (raw bytes
   for `translate`, JSON for `lift`), so untrusted child code never runs in the
   grader's process and can never hand it executable data (§3.1, §3.3). Since a
   square is a pure function of `(T, Λ, I_s, I_t, π, program)`,
   `tests/test_pure_oracle.py` proves the boundary is byte-transparent — every
   probe of every pair translates identically across both backends, lift too on
   the BTOR2 spine — with negative controls that the comparison discriminates
   and a bad child surfaces as an error. No measured number changed. Still to
   harden (later phases): OS-level isolation of the child
   (filesystem/network/seccomp) and making the grader authoritative over a
   pair's own `square()`.
3. **Negative-control harness.** *(landed)* `gurdy/core/negative_control.py`
   runs the two-sided control of §3.2: it grades a pair with a seeded defect
   (which must be caught) and intact (which must pass on every accepted probe),
   injecting the grader-authored mutant by rebinding the pair module's
   `translate`. The fast gate (§12.1) runs it for every *touched* pair with a
   decidable square and fails on a survivor — a survivor means the square is
   no-op'd or the probes are too weak (the I23/I24 class). `tests/
   test_negative_control.py` dogfoods it: gross defects caught on all checked
   pairs, the control proven non-vacuous (an identity mutant is not "caught"),
   and a semantic op-swap from `tools/fault_injection.py` caught as the
   *probe-adequacy* control. Predicted-grade hops have no build-time square, so
   no control. (Still to add: the `prior_merged_version` side of §3.2 — grade
   the base version too — which the coordinator supplies at merge, a later
   phase.)
4. **Partial-pair widening automation** *(landed; demonstrated on `evm-btor2`,
   PR #3)* — lowest risk, ratchet-protected, almost all Lane A.
   `tools/builder_dispatch.py` turns a partial pair's uncovered constructs into
   work: `work_list` (the builder queue), `build_brief` (a self-contained
   PAIRING.md work item), and `self_verify` (the per-construct gate — conjoined
   coverage, determinism, and the two-sided negative control of §3.2). The loop:
   pick a partial pair below target → generate a brief → run a builder on an
   isolated branch that implements one construct, self-verifies, and **commits on
   green** construct by construct → the coordinator runs the full gate and
   **opens a PR when the milestone is reached**. Spawning the builder agent and
   opening the PR are the coordinator's actions (a Claude Agent SDK orchestrator
   in unattended deployment).

   *Demonstration (`evm-btor2` 86→91/144, bitwise AND/OR/XOR/NOT/ISZERO).* The
   run exercised the design's core safety property: the first builder found the
   opcodes needed a *shared-interpreter* extension, **stopped at the lane
   boundary** rather than forcing through it, and in doing so surfaced a real
   framework bug (`coverage.measure()` didn't guard the square's interpreter call
   against `Unsupported`). The coordinator resolved it in two honestly-separated
   tiers — a framework fix on `main`, then the shared `gurdy/languages/evm`
   interpreter extension (INTERP_VERSION 0.9→0.10) — after which a second builder
   landed the five BTOR2 lowerings cleanly, one commit per opcode, staying inside
   `translate.py`/`inventory.py`/`SPEC.md`. Coordinator integration bumped
   `translator_version` and re-validated the dependent coverage-snapshot tests
   (the ratchet). Gate green throughout; PR opened only at the milestone.
5. **The syntactic additivity checker** *(landed)* — the highest-leverage
   integration piece: lets shared-layer widening merge with no human.
   [`tools/additivity.py`](./tools/additivity.py) parses base vs. head and
   returns Lane A (only insertions of new statements/branches, plus the inert
   version-bump and docstring allowances — a proof by construction that no
   existing path changed) or Lane B (any edit/rebind/deletion of an existing
   path, with a localized reason). Recurses into function/class bodies; matches
   declarations by identity so a container can be *additively modified*. Wired
   into the PR manifest as `verdict.shared_lane` (fails **safe** to Lane B if the
   check errors). Validated on the Phase-4 diff: evm-btor2's shared change
   (`asm.py` new opcodes + `interp.py` new `_execute` branches + the
   `INTERP_VERSION` bump) classifies **Lane A** — it could have auto-integrated.
6. **The coordinator merge queue** *(landed, propose mode)* — with shared-layer
   serialization and the Lane-B fan-out (§6–§7). [`tools/merge_queue.py`](./tools/merge_queue.py)
   consumes each candidate PR's Phase-1 manifest (plus, for a non-additive shared
   change, its shared-change manifest) and emits an **ordered merge plan**:
   shared-touching PRs serialized in the `framework → interpreters → pairs` DAG
   order, independent pair PRs packed into parallel waves under a per-pair lock;
   a per-candidate decision (`MERGE` for independent or Lane-A additive, `FAN_OUT`
   for Lane B, `ESCALATE` for a protected instrument, `REJECT` for a red gate or
   a Lane-B change missing its manifest); and, for each Lane-B candidate, the
   fan-out spec — the dependent pairs (everything consuming the touched
   interpreter; every pair for a `gurdy/core` change) and the manifest's expected
   verdict per pair, which `reconcile()` checks against the observed re-gate (an
   unpredicted green→red is a regression → reject). It **starts in propose mode**
   — the plan is emitted for a human to approve, never auto-merged; autonomy is
   graduated in only once the fan-out has caught real regressions.
7. **Common-mode-in-CI + author-diversity provenance** *(landed)* (§9) — the
   hardening that makes autonomous merge trustworthy.
   [`tools/provenance.py`](./tools/provenance.py) validates the coordinator-
   attested provenance record: it rejects self-reported provenance, an
   interpreter-contributor authoring a pair over that interpreter, and a
   corroborated pair whose legs share a model family *or* a semantic artifact;
   it escalates a leg whose artifact is not a registered external one (possibly
   builder-authorable). It folds into the merge queue (a provenance REJECT is
   terminal; an ESCALATE pulls a would-be merge to human review).
   [`tools/common_mode_gate.py`](./tools/common_mode_gate.py) reframes the
   fault-injection experiments as a per-construct gate: the single-leg mutation
   family through the pure-python square (fast lane), classifying square-escaping
   mutations as *anchor-required* (the external differential catches them, at
   BENCHMARKS cadence); and each pair's **common-mode posture** —
   `external-differential` (a Sail model exists) vs `single-artifact` (the §11
   residue, now explicit) — which rides in the PR manifest. A pair's
   anchor-required set must clear the anchor round before the merge queue
   graduates it to autonomous merge.

The through-line: the discipline already exists (ratchet, versioned events,
externalized grading, conjoined coverage). Automation is (a) running those
checks per-PR in CI, (b) expressing shared-layer change as a manifest the
coordinator executes via the additive/coordinated split, and (c) hardening the
grader and the common-mode corner so a green gate is trustworthy without a human
behind it.

### 12.8 Graduating autonomy (draft — [`tools/autonomy.py`](./tools/autonomy.py), defaults to propose)

Phases 1–7 land the queue in **propose mode**: it emits plans, a human approves,
nothing auto-merges. Turning autonomy on is not one switch — it is a **monotone
ladder whose every rung is earned by evidence**, governed by the platform's own
negative-control discipline applied to the merge decision itself: *a gate you let
merge unattended must first have demonstrably caught real defects.* A fan-out that
never rejected anything, a negative control that never fired, is untrustworthy
precisely because it is unproven.

| Level | Auto-executes | Earned when |
|---|---|---|
| **L0 propose** *(default)* | nothing | — |
| **L1 independent** | `MERGE` for independent pair PRs (pair-only, gate green — the lowest-risk, ratchet-protected class) | the per-pair negative control has caught ≥ K seeded defects (non-vacuous) **and** a shadow run of independent MERGEs agreed with the human with **zero** disagreements |
| **L2 additive-shared** | + Lane-A (syntactically additive) shared MERGEs (safe by construction) | the additivity checker has classified ≥ N shared changes with zero shadow disagreements, on a clean L1 window |
| **L3 fan-out** | + Lane-B candidates whose re-validation fan-out reconcile-accepts | **the fan-out has caught ≥ R real regressions** — the non-vacuity proof — with a clean reconcile shadow record |

`ESCALATE` is always human and `REJECT` never merges, at every rung. **Safety
rails** (they only ever pull EXECUTE → PROPOSE): a protected-instrument change is
always human (§9); an external-differential pair whose anchor round has not
confirmed its anchor-required set stays proposed (§9); a Lane-B candidate that has
not reconcile-accepted stays proposed. **Kill switch:** any autonomous merge
followed by `main` going red collapses the attained level to L0 until a human
re-graduates — autonomy is continuously re-earned, not granted once.

`attained_level(ledger)` reads the coordinator's evidence ledger and returns the
highest earned rung (L0 on an empty ledger); `annotate()` tags each plan decision
with `EXECUTE`/`PROPOSE`. Wiring it in changes nothing until the evidence exists
*and* a human raises the level.

**Accruing the evidence ([`tools/shadow_ledger.py`](./tools/shadow_ledger.py)).**
The ledger is not hand-authored — it accumulates from CI *while the queue sits at
L0*. Every resolved PR is a free **shadow trial**: the coordinator records what
autonomy *would* have executed (a `shadow_execution` computed at that risk
class's level) beside what the human actually did, plus the per-run non-vacuity
signals — did the per-pair negative control fire, did a Lane-B fan-out reject a
real regression — and the post-merge outcome. `entry_from_plan()` builds one
entry from a live merge-queue plan; `accumulate()` folds a stream into the
ledger; `progress()` reports the gap to each rung. Only a trial autonomy *would
have gone on* (`shadow_execution == EXECUTE`) counts toward a class's total, and a
trial where the human declined to merge is a disagreement — exactly the false-go
that must stay at zero. So the bar for L1/L2/L3 is cleared by real trunk history
before anyone flips the level, and the flip is a confirmation, not a gamble.

CI closes the loop: on every merge to `main`, the `manifest` job runs
`shadow_ledger.py entry` and uploads the resulting shadow entry as an artifact
(auxiliary and non-gating — it can never red a merge). The coordinator collects
those `shadow-entry-*` artifacts, finalizes each `outcome` from observed
post-merge health, and `accumulate`s them into the ledger; `progress` then shows
the standing gap to each rung. Nothing about this changes the operative mode —
the queue stays at L0 until the evidence is in and a human raises the level.
