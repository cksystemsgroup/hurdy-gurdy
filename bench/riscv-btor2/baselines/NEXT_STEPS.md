# Next steps — decisions for the user

> **HISTORICAL — superseded.** These were the open decisions at the close
> of the autonomous baselines run; most have since landed (e.g. the
> adversarial wedge battery 0125 / 0300–0303, the pono install). Kept for
> history, no longer maintained. Current baseline results:
> `baselines/SUMMARY.md`; current plan: `PLAN.md`.

> Produced at the natural close of the 25-iter autonomous run on
> `v2-bootstrap`. Each item is a discrete decision; pick zero, one,
> or several. The loop can resume on any of them with no special
> handoff — `V2_PROGRESS.md` carries the state.

## High-leverage (do these first)

### 1. Approve the P1.3a translator fix (BLOCKER pending since iter 10)

**Status**: fully specified, gated on your review per
`V2_AGENT_LOOP.md` §1.3a.

The alignment oracle caught a real translator bug on its very
first exercise: `gurdy/pairs/riscv_btor2/translation/exprs.py:218`
hardcodes the result sort `"bv64"` for `add/sub/and/or/xor`,
producing malformed BTOR2 when the operands are bv1 (the `bad`
clause's combined AND of boolean equalities).

Fix shape (~25 LOC):
- Builder gains `_nid_sort: dict[int, str]` populated by
  `const`, `ones`, `emit`.
- `Builder.sort_of_nid(nid) -> str | None` helper.
- `exprs.py` `and/or/xor` branch reads the first operand's
  sort and emits the result with the same sort. `add/sub/mul`
  remain `"bv64"`.

To unblock: reply `UNBLOCKED: approve P1.3a fix`. The next loop
iteration will apply the patch, run
`pytest tests/pairs/riscv_btor2/translation/`, re-run
`framework_oracle.py` (verdict regression), and re-run
`oracle_align.py` on 0007 + 0002 (alignment confirms green).

### 2. Decide whether to publish the wedge finding

5/5 wedges on the C-UB-but-RV64-defined predictive subset, 18-
task pooled sample. CBMC 13/18 correct vs hurdy-gurdy 18/18.
Reproducible across iters 18, 20, and 22 measurements.

The headline is sharper than the original V2_BOOTSTRAP.md §5
prediction asked for. Options:

- Just merge the v2-bootstrap learnings to `main` (the
  `baselines/` dir, `oracle_align.py`, `INITIAL_FINDINGS.md`,
  the canonical 18-task table). Internal use, no external claim.
- Stronger: write a SCOPE.md update referencing the wedge
  pattern and add it to BENCHMARKING.md as a §10 "soundness
  comparison" subsection.
- Strongest: release a v0.5 note that documents the wedge
  pattern as a hurdy-gurdy strength on UB-class tasks. This
  changes how the project's claim is framed: "more sound than
  C-level verifiers on UB tasks" is a concrete differentiator,
  not just an architectural argument.

## Medium-leverage (expand the empirical claim)

### 3. Install pono / docker images for fuller SOTA comparison

Only CBMC is natively available on this machine. The Pareto
table is currently CBMC-vs-hurdy-gurdy alone. Adding:
- **pono** (build from source or homebrew tap when available)
  — apples-to-apples BTOR2 peer.
- **ESBMC** (homebrew may work; otherwise Docker) — second-
  vendor C BMC.
- **SeaHorn / Symbiotic** (Docker) — Horn-clause / slicing
  alternatives.

Each adapter is already written and skip-with-note's when its
binary is missing. Once the binaries appear, the next loop
iteration's Pareto run lights up the additional columns
without code changes.

### 4. Generate adversarial wedges to harden the claim

The 5 existing wedges came from the corpus author's own
`lowering_sensitive=true` tagging. Hand-craft new C tasks
exercising other C-UB-RV64-defined constructs the corpus
doesn't yet cover:
- Unary `-INT_MIN` (signed overflow on negation).
- Oversized variable shift count (e.g. `int s = 64; x << s`).
- `INT_MAX + 1` via volatile.
- Pointer arithmetic past one-past-the-end.

`bench/riscv-btor2/corpus/_compile_c.py` is the toolchain
(`riscv64-unknown-elf-gcc` is on PATH). One new task per loop
iter would build out the corpus carefully.

### 5. Run the wedge battery on an actual SV-COMP slice

The v0.5 SV-COMP pilot work in `bench/riscv-btor2/_svcomp_*`
is already in progress on `main`. Replaying the wedge analysis
on real SV-COMP `c/` track tasks would lift the claim from
"hand-curated 18 tasks" to "subset of the standard reference
benchmark". This is exactly what the original PLAN.md §14
called for.

## Lower-leverage (close gaps; not on the critical path)

### 6. Close the wall-clock gap

CBMC's ~25× median speed advantage is structural (per-task
BTOR2 compile + z3 subprocess startup). The right levers:

- Engine pinning per spec (bitwuzla 6-13× faster on some
  classes — see `bench/riscv-btor2/CORPUS_V0.3_PLAN.md`).
- Translator caching by `(spec_hash, source_hash)` —
  framework cache exists but bench harness doesn't share
  across tasks.
- Tighter `analysis.bound` per spec (default 20; many tasks
  evident-bound ≤ 5).

This is meaningful only if wall-clock matters to a specific
downstream consumer. For research / soundness comparisons it
doesn't.

### 7. Merge v2-bootstrap to main, selectively

After the P1.3a fix lands and the wedge writeup is published,
the v2-bootstrap learnings worth keeping:
- `oracle_align.py` (bench-side primary alignment oracle).
- `bench/riscv-btor2/baselines/` (all of it).
- `V2_AUDIT.md` (canonical map of which contracts v1 satisfies).
- Possibly the corrected `PLAN.md` framing.

The bootstrap docs (`V2_BOOTSTRAP.md`, `V2_AGENT_LOOP.md`,
`V2_PROGRESS.md`) are branch-life artifacts; they don't need
to merge. A clean cherry-pick + squash of the build commits
would leave `main` carrying the durable wins without the iter-
by-iter narrative.

## To pause / stop the loop

- Add a `STOP_LOOP` file at the repo root — the next iteration
  detects it and halts cleanly.
- Or just stop typing `/loop` — each iteration is invoked
  manually; if you don't, the loop ends.

## What this run did and didn't do

**Did**: produced a working bench-side primary alignment oracle
that immediately caught a real translator bug; built a SOTA-
baselines comparison framework; ran 5 measurement iterations
covering 18 tasks; produced one reproducible-across-runs
headline (CBMC 13/18 vs HG 18/18, 5/5 wedge rate on UB
predictive subset).

**Didn't**: apply the P1.3a fix (gated on you); generate new
corpus tasks (toolchain present but not autonomous-safe);
install or invoke non-CBMC SOTA tools (binaries absent); merge
to `main` (gated on you).

The architecture's thesis is now empirically supported. The
remaining work is policy decisions, not engineering discovery.
