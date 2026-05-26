# V2 Agent Loop — Iteration Playbook

> Read this every iteration before doing anything else.
>
> This file is the procedure. `V2_BOOTSTRAP.md` is the spec. `V2_PROGRESS.md`
> is the state. The three together are enough for any fresh Claude Code
> session to continue the work.

## 1. Pre-flight (every iteration)

Run, in order:

1. `git status` — must be clean. If not: stash or commit first.
2. The riscv-btor2 / v2 line now lives on `main` (the former
   `v2-bootstrap` branch was merged into `main` and deleted). Work on
   a branch off `main` — a remote routine session provisions one
   automatically; locally, create/checkout one. **Never commit or
   push to `main` directly.** When the iteration is done, push your
   working branch; the user reviews and merges it into `main`.
3. Read `V2_BOOTSTRAP.md` §7 (phase plan) and §9 (improvement loop).
4. Read `V2_PROGRESS.md` end-to-end. The last entry says where you are.
5. Re-read this file. *Yes, every iteration.* Procedures drift; the
   file does not.

If any pre-flight step fails or surprises you, write a `BLOCKER:` line
to `V2_PROGRESS.md`, commit, and stop the iteration. Do not push
through.

## 2. Decide what to do this iteration

Pick exactly **one** of these. Do not bundle.

**Priority order** (do the highest applicable):

A. **Resolve a BLOCKER** from `V2_PROGRESS.md`. If there's an open
   blocker the user has unblocked (look for `UNBLOCKED:` reply), that
   is this iteration.

B. **Fix a regression**: if the last `harness` run shows a previously
   green corpus task is now red, that is this iteration. Bisect to
   the commit, revert or patch, re-run the affected tasks only.

C. **Advance the current phase** by one increment. "One increment" =
   one PR-sized change: one file added, or one feature in one module,
   or one schema rule. Not "implement P3 in one go".

D. **Run the harness** on ≤ 5 corpus tasks, update the Pareto table.
   This is allowed at most every 3 iterations to avoid thrashing.

E. **Plan a SOTA experiment** without running it — write a design
   note in `bench/riscv-btor2/experiments/NNNN-<slug>.md`. The next
   iteration runs it.

F. **Extend the corpus** by ≤ 5 tasks via the streaming recipe in §4.
   Never bulk-download.

## 3. Do the work

### Commit conventions

- Branch: always `v2-bootstrap`. Never `main`.
- Commit message format:
  ```
  v2/<phase>: <one-line subject>

  <body — what & why, not how. Reference V2_BOOTSTRAP.md §N if relevant.>
  ```
  Examples: `v2/P3: BTOR2 parser skeleton`, `v2/P12: bitwuzla adapter
  subprocess + timeout`.
- One iteration = one commit, ideally. Two if a clean refactor +
  feature split helps reviewability.
- **Never** amend, force-push, or rewrite history.

### Testing

- Add a test for every new public function or schema rule.
- Run only the tests touching what you changed (e.g.
  `pytest tests/pairs/riscv_btor2/source_interp/`), not the full
  suite, unless an iteration's purpose is full-suite validation.
- Full-suite runs are allowed but only when current phase says so.

### When you reach an impasse

Write `BLOCKER: <one-line reason>` at the top of `V2_PROGRESS.md`,
add a 5–10 line context dump below explaining what you tried and
what you'd need to proceed, commit, and stop. **Do not** try to
muscle through with destructive operations or by lowering the bar
on correctness.

## 4. RAM and resource safety

A previous session in this repo OOM-crashed the user's machine.
Treat the following as hard rules:

- **Parallelism cap**: `-j 2` maximum for any compilation, pytest,
  or subprocess fanout. Never `xargs -P` higher than 2.
- **Per-process memory cap**: when invoking solvers, pass
  `--memory` / `ulimit -v 2000000` (2 GiB) or smaller, *always*.
- **Per-process time cap**: default 60s; never exceed 300s without
  an explicit `BLOCKER:`-class justification in
  `V2_PROGRESS.md`.
- **No bulk corpus download**: never `git clone` SV-COMP in full.
  Use the streaming recipe:
  ```python
  # bench/riscv-btor2/corpus/_svcomp_stream.py — fetch *one* file by
  # path via GitHub raw URL with `requests` and a hardcoded
  # whitelist. Never recursively walk the remote tree.
  ```
- **No unbounded `subprocess.PIPE`**: always cap output capture at
  16 MB. Anything bigger redirects to a tempfile.
- **No in-memory list of all corpus files**: iterate, process, drop.
- **No `pytest -n auto`**: explicit `-n 2` only.

If any iteration's planned work might exceed these caps (e.g.
running on the full SV-COMP slice), the iteration's job is to write
a `BLOCKER: needs user approval for resource-heavy run` instead.

## 5. Reasonable scope per iteration

A good iteration is 15–45 minutes of equivalent human work. Bad
iterations look like:

- "Implement the whole BTOR2 simulator." → split into parser /
  state-machine / observable-recorder.
- "Run all 10 seed tasks + record full Pareto table + write up
  results." → that's three iterations.
- "Refactor the translator now that I see how P9 will look." →
  *no.* Land P9 first; refactor later when its shape is real.

If you finish your planned increment early and have spare budget,
**don't grab more work**. Update `V2_PROGRESS.md` with what you did
and what's next, commit, and stop. The next iteration is cheap.

## 6. End-of-iteration checklist

Before the iteration ends:

1. `git status` shows only the files you intended to change.
2. `git diff --stat HEAD~1` is in the 15–45-min-of-work range.
3. `V2_PROGRESS.md` updated:
   - Last entry timestamped (UTC ISO 8601).
   - Phase + sub-task identified.
   - One line of "what changed".
   - One line of "next iteration's planned work".
   - Any `BLOCKER:` or `UNBLOCKED:` lines visible.
4. Commit on your working branch (never `main`). In a remote routine
   session the branch is persisted/pushed when the session ends;
   running locally, leave pushing to the user.
5. Schedule the next wake-up via `ScheduleWakeup` (see §7).

## 7. Self-pacing

This loop is driven by the `loop` skill in dynamic mode. Each
iteration ends with a `ScheduleWakeup` that fires the *same* `/loop`
prompt, re-entering this playbook.

Wake-up cadence:

- **20 minutes (1200s)** is the default. Long enough for any
  in-flight subprocess to finish, short enough that meaningful
  work happens daily even if the user is away.
- **Up to 60 minutes (3600s)** when the work just done was a
  speculative refactor and the next iteration should let context
  cool (rare).
- **Never** under 5 minutes. There is no condition in this project
  worth polling more often than that.

Pass the literal `<<autonomous-loop-dynamic>>` sentinel back as the
`prompt`, per the `ScheduleWakeup` tool docs. The runtime expands it
to the loop instructions on fire.

## 8. When to stop the loop entirely

Stop scheduling new wake-ups when **any** of:

- Three consecutive iterations have written `BLOCKER:` and the
  user has not responded with `UNBLOCKED:`. (User is away or the
  blocker is not unblockable autonomously.)
- The Pareto table shows hurdy-gurdy strictly dominating SOTA on
  the SV-COMP slice for 30 consecutive iterations. Mission
  accomplished — write a final report and stop.
- The repo has uncommitted changes that pre-flight can't resolve
  safely. Write a `BLOCKER:` and stop.
- The user has added a file `STOP_LOOP` at the repo root. Treat as
  immediate halt.

Stopping = omit `ScheduleWakeup`. The loop ends.

## 9. Reference

- `V2_BOOTSTRAP.md` — what we're building and why.
- `V2_PROGRESS.md` — where we are.
- `PLAN.md` (on `v2-bootstrap` once the agent writes it) — phase plan.
- `bench/riscv-btor2/SCOPE.md` — what's in scope for the pair.
- `main` branch — v1 reference implementation; inspect freely
  (`git show main:<path>`), copy when contract-compatible.
- `gurdy/pairs/riscv_btor2/SCHEMA.md` on `main` — v1 schema as a
  starting point for v2 schema v1.0.0.
