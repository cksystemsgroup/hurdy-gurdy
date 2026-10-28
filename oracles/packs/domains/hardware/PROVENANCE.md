# `domains/hardware` — recorded testimony: the HWMCC'24 results

- **Files**: `hwmcc24-results-bv.csv` (2,552 rows) and
  `hwmcc24-results-array.csv` (1,605 rows): one row per (benchmark,
  solver) of the HWMCC'24 bit-vector and array tracks — `status`,
  `result` (sat / unsat / unknown), `time_real`, `time_cpu` (seconds),
  `memory` (MB).
- **Source**: the files the competition publishes at
  `https://hwmcc.github.io/2024/hwmcc24_btor2_bv.csv` and
  `https://hwmcc.github.io/2024/hwmcc24_btor2_array.csv`; both copies
  were compared byte for byte with fresh downloads on 2026-10-28
  (md5 `e7ce6f1e008945ef1d55b79343b5d75c` and
  `ef63c2e8f1f2203663e618a04c768dc1`). The competition ran each solver
  with a 1-hour wall-clock limit and a 120 GB memory limit on a 16-core
  node with 128 GB RAM (hwmcc.github.io/2024); eight solvers
  participated in the bit-vector track: ric3, avr, nuxmv, pono,
  avr_dp, btor2-selectmc, satvik, btormc.
- **Use** (KERNEL.md §6, relative performance): testimony beside cost.
  The per-question `official` strings of `runs/hwmcc24-*/benchmark.json`
  were written from these files; `paper/gate/oracle.py` joins them to
  the pinned questions by benchmark path and draws, per question, the
  best result's cost beside the best official solver's real time. Never
  ranked by the kernel, never a grade; nothing here runs in a play.
- **Calibration**: `calibration.jsonl` beside this file, when present,
  records the pinned oracle `btormc` 3.2.4 run on the host that plays
  (see its `host` records) on the existential questions of the pinned
  boards, with the same bound the question asks and the same wall the
  slice was played at, so that host time and competition time can be
  related for the same tool on the same instance.
- **Reading the calibration records** (written 2026-10-28, wall 900 s,
  one process at a time beside one single-threaded play): `result` is
  `sat` or `unsat` when `btormc` printed that verdict before the wall
  (a `sat` with `wall_s` at 900 was printed at the wall), `wall` when
  it was killed at the wall without a verdict, `memory` when the host
  guard killed it above 6 GB of resident memory, and `rc=0` when it
  exhausted `-kmax` without finding a bad state — for a question whose
  official verdict is `sat` that says the bad state lies deeper than
  the pinned bound. The slice itself was played with the same guard;
  a play killed by it in one of the kernel's two runs is booked by the
  kernel as `search nondeterministic`, the guard's doing, not the
  search's.
