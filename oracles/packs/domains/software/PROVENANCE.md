# `domains/software` — recorded testimony: the SV-COMP 2025 results

- **File**: `svcomp25-results-reachsafety.csv` (25,464 rows): one row
  per (task, verifier) of the SV-COMP 2025 categories
  ReachSafety-Loops and ReachSafety-BitVectors — `status` (the
  verifier's answer), `outcome` (correct, wrong, unknown, error,
  correct-unconfirmed, as scored by the competition), `cputime_s`,
  `walltime_s`.
- **Source**: extracted outside this tree on 2026-08-19 from the
  per-verifier result tables the competition publishes under
  `https://sv-comp.sosy-lab.org/2025/results/results-verified/`
  (`<verifier>.<timestamp>.results.SV-COMP25_unreach-call.<category>.xml.bz2`),
  33 verifiers; the file was the input to the `official` strings and
  the selection of `runs/svcomp25-mini/benchmark.json`. SV-COMP 2025
  ran each verifier with 15 min of CPU time, 15 GB of memory, and 8
  processing units per task (sv-comp.sosy-lab.org/2025/rules.php).
- **Use** (KERNEL.md §6, relative performance): testimony beside cost;
  `paper/gate/oracle.py` joins the file to the pinned questions by task
  name (`<category dir>/<task>.yml`) and draws, per question, the best
  result's cost beside the best correct verifier's CPU time. Never
  ranked by the kernel, never a grade; nothing here runs in a play.
- **Calibration**: `calibration.jsonl` beside this file, when present,
  records the pinned oracle `cbmc` 6.11.0 run on the host that plays
  on the existential questions of the pinned board under the same
  wall the slice was played at.
- **Reading the calibration records** (written 2026-10-28, wall 900 s,
  one process at a time beside one single-threaded play): `unwind` is
  the last unwinding tried; `result` is `failed` when `cbmc` reported
  `VERIFICATION FAILED` at that unwinding (the witness found), `wall`
  when the doublings ran out of wall, `memory` when the host guard
  killed a run above 5 GB of resident memory, and `rc=N` when a run
  ended with neither verdict (a parse or front-end failure, exit code
  N). `wall_s` is the total over all unwindings tried.
- **Reading `outcome`**: `paper/gate/oracle.py` counts a verifier as
  having answered a task when its outcome is `correct` or
  `correct-unconfirmed` (the verdict right, the witness not validated
  by the competition); the pinned `official` strings of
  `runs/svcomp25-mini/benchmark.json` count the same way. 25 of the 79
  pinned tasks were answered only by unconfirmed verdicts.
