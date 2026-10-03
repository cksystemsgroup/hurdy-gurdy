# `c` assertion vectors — recorded testimony (2026-10-03)

- **What**: `testimony.jsonl`, three programs (vectors 013, 014, 015
  of `registry/languages/c@6`): 28, 27, and 13 assertions, each
  program closed by one assertion that cannot hold.
- **Oracle**: Apple clang 21.0.0 on the host (arm64, LP64), `-O0
  -fwrapv`, outside the seal. `testify.py` compiles each program as
  written — it must reach `__assert_fail` — and without its last
  assertion — it must return from `main`. Both hold for all three. No
  dispute. The programs use neither `long` nor plain `char`, the two
  types the host's ABI gives differently from the fragment's ILP32.
- **Why**: fault injection (`kernel/faults`, 2026-10-03) left 39 of 100
  sampled mutants of `c@5`'s interpreter unrefused.
- **What the oracle does not say**: the pinned *depth* of each vector
  is the generated interpreter's own frame count, not clang's.
- **Not put to the oracle**: vector 016 (shift counts at and beyond
  the width, and negative) pins a stipulation of the fragment where C
  leaves the behaviour undefined; vector 017 (halt is absorbing) reads
  inputs through the fragment's frame-addressed stimulus, which no
  compiler has.
- **Status**: testimony (`KERNEL.md` §6). Nothing here executes in the
  kernel. Re-derive by running `testify.py` on a host with clang.
