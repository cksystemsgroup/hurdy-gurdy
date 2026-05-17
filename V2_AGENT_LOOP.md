# `evm-btor2` Agent Loop — Iteration Playbook

> Read this every iteration before doing anything else.
>
> This file is the procedure. `V2_BOOTSTRAP.md` is the spec.
> `V2_PROGRESS.md` is the state.

## 1. Pre-flight (every iteration)

1. `git status` — must be clean.
2. `git branch --show-current` — must be `evm-btor2-bootstrap`. If
   not: `git checkout evm-btor2-bootstrap`. **Never edit on `main`,
   `v2-bootstrap`, or any other pair's branch.**
3. Read `V2_BOOTSTRAP.md` §6 (phase plan) and §8 (stop conditions).
4. Read `V2_PROGRESS.md` end-to-end.
5. Re-read this file. *Yes, every iteration.*

`BLOCKER:` + commit + stop on any pre-flight surprise.

## 2. Decide what to do this iteration

Pick exactly **one**. Priority order:

A. **Resolve a BLOCKER** the user has `UNBLOCKED:`.
B. **Fix a regression**: previously-green corpus task now red.
C. **Advance the current phase** by one increment (one PR-sized
   change).
D. **Run the harness** on ≤ 5 corpus tasks, update Pareto table.
   At most every 3 iterations.
E. **Plan a SOTA experiment** without running it — design note in
   `bench/evm-btor2/experiments/NNNN-<slug>.md`.
F. **Extend the corpus** by ≤ 5 tasks. Hand-crafted seeds first;
   Etherscan verified-source contracts via streaming once seeds
   converge.

## 3. Do the work

### Commit conventions

- Branch: always `evm-btor2-bootstrap`.
- Commit message format:
  ```
  evm/<phase>: <one-line subject>

  <body — what & why, not how. Reference V2_BOOTSTRAP.md §N if relevant.>
  ```
- One iteration = one commit, ideally.
- **Never** amend, force-push, or rewrite history.

### Testing

- Test every new public function / schema rule.
- Run only the tests touching what you changed.
- Full-suite runs only when the current phase says so.

### Impasse

`BLOCKER: <reason>` at top of `V2_PROGRESS.md`, 5–10 line context
dump, commit, stop. No destructive shortcuts.

## 4. RAM and resource safety

Hard rules:

- **Parallelism cap**: `-j 2`. Never higher.
- **Per-process memory cap**: `ulimit -v 2000000` (2 GiB) or smaller.
- **Per-process time cap**: 60s default; never > 300s without an
  explicit `BLOCKER:`-class justification.
- **No bulk corpus download**: never `git clone` Etherscan dumps or
  large contract corpora. Use:
  ```python
  # bench/evm-btor2/corpus/_etherscan_stream.py — fetch *one*
  # verified-source bytecode by address via the Etherscan API
  # (or a public mirror), with a hardcoded whitelist. Never
  # walk an index.
  ```
- **No unbounded `subprocess.PIPE`**: cap output capture at 16 MB.
- **No `pytest -n auto`**: explicit `-n 2` only.
- **No solc invocation without pinned version**: `solc-select`
  or a Docker pull for the exact version of each test.

If an iteration's work might exceed these caps, write a
`BLOCKER: needs user approval for resource-heavy run` instead.

## 5. Reasonable scope per iteration

A good iteration is 15–45 minutes of equivalent human work. Bad
iterations: "implement all of EVM in one go", "run all baselines +
write up". Split.

If you finish early, **don't grab more work**. Update
`V2_PROGRESS.md` and stop.

## 6. End-of-iteration checklist

1. `git status` shows only the files you intended to change.
2. `git diff --stat HEAD~1` is 15–45 min of work.
3. `V2_PROGRESS.md` updated:
   - UTC ISO 8601 timestamp.
   - Phase + sub-task.
   - One line of "what changed".
   - One line of "next iteration's planned work".
   - Any `BLOCKER:` / `UNBLOCKED:` visible.
4. Commit on `evm-btor2-bootstrap`.
5. Push: `git push -u origin evm-btor2-bootstrap`. Pre-authorized.

## 7. Self-pacing

20-min wake-up default. Up to 60 min after speculative refactor.
Never < 5 min.

## 8. When to stop the loop entirely

Stop on any of:

- 3 consecutive `BLOCKER:` without `UNBLOCKED:`.
- Pareto table shows hurdy-gurdy strictly dominating SMTChecker +
  hevm on the seed + external corpus for 30 consecutive
  iterations. Final report, then stop.
- Uncommitted changes pre-flight can't resolve safely.
- `STOP_LOOP` file at repo root.

Stopping = omit the next wake-up.

## 9. Reference

- `V2_BOOTSTRAP.md` — what we're building.
- `V2_PROGRESS.md` — where we are.
- `PLAN.md` (on this branch once written) — phase plan.
- `bench/evm-btor2/SCOPE.md` — pair scope.
- `main` — v1 reference. `v2-bootstrap` — `riscv-btor2` v2 line
  with foundation patterns. Inspect freely
  (`git show v2-bootstrap:<path>`); copy contract-compatible code
  where helpful.
