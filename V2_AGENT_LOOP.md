# `wasm-btor2` Agent Loop — Iteration Playbook

> Read this every iteration before doing anything else.
>
> This file is the procedure. `V2_BOOTSTRAP.md` is the spec.
> `V2_PROGRESS.md` is the state. The three together are enough for
> any fresh Claude Code session to continue the work.

## 1. Pre-flight (every iteration)

Run, in order:

1. `git status` — must be clean. If not: stash or commit first.
2. `git branch --show-current` — must be `wasm-btor2-bootstrap`. If
   not: `git checkout wasm-btor2-bootstrap`. **Never edit on `main`,
   `v2-bootstrap`, or any other pair's branch.**
3. Read `V2_BOOTSTRAP.md` §6 (phase plan) and §8 (stop conditions).
4. Read `V2_PROGRESS.md` end-to-end. The last entry says where you
   are.
5. Re-read this file. *Yes, every iteration.* Procedures drift; the
   file does not.

If any pre-flight step fails or surprises you, write a `BLOCKER:`
line to `V2_PROGRESS.md`, commit, and stop the iteration.

## 2. Decide what to do this iteration

Pick exactly **one** of these. Do not bundle.

**Priority order** (do the highest applicable):

A. **Resolve a BLOCKER** from `V2_PROGRESS.md`. If there's an open
   blocker the user has unblocked (`UNBLOCKED:` reply), that is this
   iteration.

B. **Fix a regression**: if the last `harness` run shows a previously
   green corpus task is now red, that is this iteration. Bisect to
   the commit, revert or patch, re-run the affected tasks only.

C. **Advance the current phase** by one increment. "One increment"
   = one PR-sized change.

D. **Run the harness** on ≤ 5 corpus tasks, update the Pareto table.
   At most every 3 iterations to avoid thrashing.

E. **Plan a SOTA experiment** without running it — write a design
   note in `bench/wasm-btor2/experiments/NNNN-<slug>.md`.

F. **Extend the corpus** by ≤ 5 tasks. Hand-crafted seeds first;
   external WASM modules via the streaming recipe in §4 once the
   seed corpus has converged.

## 3. Do the work

### Commit conventions

- Branch: always `wasm-btor2-bootstrap`.
- Commit message format:
  ```
  wasm/<phase>: <one-line subject>

  <body — what & why, not how. Reference V2_BOOTSTRAP.md §N if relevant.>
  ```
  Examples: `wasm/P2: WASM module decoder skeleton`, `wasm/P7: seed
  task 0001-i32-add-wrap lands`.
- One iteration = one commit, ideally. Two if a clean refactor +
  feature split helps reviewability.
- **Never** amend, force-push, or rewrite history.

### Testing

- Add a test for every new public function or schema rule.
- Run only the tests touching what you changed.
- Full-suite runs only when the current phase says so.

### When you reach an impasse

Write `BLOCKER: <one-line reason>` at the top of `V2_PROGRESS.md`,
add a 5–10 line context dump, commit, and stop. **Do not** muscle
through with destructive operations.

## 4. RAM and resource safety

Hard rules (a previous session in this repo OOM-crashed the user's
machine):

- **Parallelism cap**: `-j 2` maximum. Never `xargs -P` higher.
- **Per-process memory cap**: pass `--memory` / `ulimit -v 2000000`
  (2 GiB) or smaller, *always*.
- **Per-process time cap**: default 60s; never exceed 300s without
  an explicit `BLOCKER:`-class justification.
- **No bulk corpus download**: never `git clone` large WASM
  collections in full. Use a streaming recipe:
  ```python
  # bench/wasm-btor2/corpus/_external_stream.py — fetch *one* wasm
  # by URL via `requests`, with a hardcoded whitelist. Never walk a
  # remote tree.
  ```
- **No unbounded `subprocess.PIPE`**: cap output capture at 16 MB.
- **No `pytest -n auto`**: explicit `-n 2` only.

If an iteration's planned work might exceed these caps, write a
`BLOCKER: needs user approval for resource-heavy run` instead.

## 5. Reasonable scope per iteration

A good iteration is 15–45 minutes of equivalent human work. Bad
iterations look like:

- "Implement the whole WASM decoder." → split into header parser /
  type section / function section / code section.
- "Run all 10 seed tasks + record Pareto table + write up results."
  → three iterations.
- "Refactor the translator now that I see how P9 will look." →
  no. Land P9 first.

If you finish early, **don't grab more work**. Update
`V2_PROGRESS.md` and stop. The next iteration is cheap.

## 6. End-of-iteration checklist

1. `git status` shows only the files you intended to change.
2. `git diff --stat HEAD~1` is in the 15–45-min-of-work range.
3. `V2_PROGRESS.md` updated:
   - Last entry timestamped (UTC ISO 8601).
   - Phase + sub-task identified.
   - One line of "what changed".
   - One line of "next iteration's planned work".
   - Any `BLOCKER:` or `UNBLOCKED:` lines visible.
4. Commit on `wasm-btor2-bootstrap`.
5. Push: `git push -u origin wasm-btor2-bootstrap`. The user has
   pre-authorized push to this branch in the bootstrap directive.

## 7. Self-pacing

This loop is driven by the `loop` skill in dynamic mode (or by
scheduled web sessions). Each iteration ends with a wake-up that
fires the same `/loop` prompt, re-entering this playbook.

Wake-up cadence:

- **20 minutes (1200s)** is the default.
- **Up to 60 minutes (3600s)** when the work just done was a
  speculative refactor.
- **Never** under 5 minutes.

## 8. When to stop the loop entirely

Stop scheduling new wake-ups when **any** of:

- Three consecutive iterations have written `BLOCKER:` and the user
  has not responded with `UNBLOCKED:`.
- The Pareto table shows hurdy-gurdy strictly dominating SOTA
  (Manticore-WASM + KLEE-WASM) on the seed + external WASM corpus
  for 30 consecutive iterations. Mission accomplished — write a
  final report and stop.
- The repo has uncommitted changes that pre-flight can't resolve
  safely. Write a `BLOCKER:` and stop.
- The user has added a file `STOP_LOOP` at the repo root. Treat as
  immediate halt.

Stopping = omit the next wake-up. The loop ends.

## 9. Reference

- `V2_BOOTSTRAP.md` — what we're building and why.
- `V2_PROGRESS.md` — where we are.
- `PLAN.md` (on this branch once the agent writes it) — phase plan.
- `bench/wasm-btor2/SCOPE.md` — what's in scope for the pair.
- `main` branch — v1 reference. `v2-bootstrap` branch —
  `riscv-btor2` v2 line with the foundation patterns
  (interpreter alignment, multi-engine cross oracle) already
  built. Inspect freely (`git show v2-bootstrap:<path>`); copy
  contract-compatible code where it helps.
