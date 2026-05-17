# `ebpf-btor2` Agent Loop — Iteration Playbook

> Read this every iteration before doing anything else.
>
> This file is the procedure. `V2_BOOTSTRAP.md` is the spec.
> `V2_PROGRESS.md` is the state.

## 1. Pre-flight (every iteration)

1. `git status` — must be clean.
2. `git branch --show-current` — must be `ebpf-btor2-bootstrap`. If
   not: `git checkout ebpf-btor2-bootstrap`. **Never edit on `main`,
   `v2-bootstrap`, or any other pair's branch.**
3. Read `V2_BOOTSTRAP.md` §6 (phase plan) and §8 (stop conditions).
4. Read `V2_PROGRESS.md` end-to-end.
5. Re-read this file.

`BLOCKER:` + commit + stop on any pre-flight surprise.

## 2. Decide what to do this iteration

Pick exactly **one**. Priority order:

A. **Resolve a BLOCKER** the user has `UNBLOCKED:`.
B. **Fix a regression**.
C. **Advance the current phase** by one increment.
D. **Run the harness** on ≤ 5 corpus tasks. At most every 3
   iterations.
E. **Plan a SOTA experiment** as a design note in
   `bench/ebpf-btor2/experiments/NNNN-<slug>.md`.
F. **Extend the corpus** by ≤ 5 tasks. Hand-crafted seeds first;
   verifier-reject programs via streaming once seeds converge.

## 3. Do the work

### Commit conventions

- Branch: always `ebpf-btor2-bootstrap`.
- Commit message format:
  ```
  ebpf/<phase>: <one-line subject>

  <body — what & why, not how.>
  ```
- One iteration = one commit, ideally.
- **Never** amend, force-push, or rewrite history.

### Testing

- Test every new public function / schema rule.
- Run only the tests touching what you changed.

### Impasse

`BLOCKER: <reason>` at top of `V2_PROGRESS.md` + 5–10 line context
dump + commit + stop. No destructive shortcuts.

## 4. RAM and resource safety

Hard rules:

- **Parallelism cap**: `-j 2`.
- **Per-process memory cap**: `ulimit -v 2000000` (2 GiB) or smaller.
- **Per-process time cap**: 60s default; ≤ 300s with explicit
  justification.
- **No bulk corpus download**: never clone Linux kernel sources,
  Cilium, Falco, or Pixie repos in full. Streaming recipe:
  ```python
  # bench/ebpf-btor2/corpus/_external_stream.py — fetch *one*
  # .bpf.o or .c file by raw URL, with a hardcoded whitelist.
  ```
- **No unbounded `subprocess.PIPE`**: cap output at 16 MB.
- **No `pytest -n auto`**: explicit `-n 2`.
- **No live kernel attachments**: the kernel-verifier baseline
  loads programs with `BPF_PROG_LOAD` *for verifier feedback
  only* and never attaches them to live hooks. If load fails
  due to missing capability, the adapter must
  **skip-with-note**, never error the loop.

## 5. Reasonable scope per iteration

15–45 minutes of human work. Split anything larger.

If you finish early, **don't grab more work**. Update
`V2_PROGRESS.md` and stop.

## 6. End-of-iteration checklist

1. `git status` shows only intended files.
2. `git diff --stat HEAD~1` is 15–45 min.
3. `V2_PROGRESS.md` updated:
   - UTC ISO 8601 timestamp.
   - Phase + sub-task.
   - "What changed" / "next iteration's planned work".
   - Any `BLOCKER:` / `UNBLOCKED:` visible.
4. Commit on `ebpf-btor2-bootstrap`.
5. Push: `git push -u origin ebpf-btor2-bootstrap`. Pre-authorized.

## 7. Self-pacing

20-min wake-up default. Up to 60 min after speculative refactor.
Never < 5 min.

## 8. When to stop the loop entirely

- 3 consecutive `BLOCKER:` without `UNBLOCKED:`.
- Pareto table shows hurdy-gurdy proving safe ≥ K kernel-rejected
  programs (where K is the seed corpus size) with zero false
  positives, for 30 consecutive iterations. Final report, then
  stop.
- Uncommitted changes pre-flight can't resolve safely.
- `STOP_LOOP` file at repo root.

Stopping = omit the next wake-up.

## 9. Reference

- `V2_BOOTSTRAP.md` — what we're building.
- `V2_PROGRESS.md` — where we are.
- `PLAN.md` (on this branch once written) — phase plan.
- `bench/ebpf-btor2/SCOPE.md` — pair scope.
- `main` — v1 reference. `v2-bootstrap` — `riscv-btor2` v2 line
  with foundation patterns. Inspect freely; copy
  contract-compatible code where helpful.
