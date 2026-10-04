# `c` operator tables — recorded testimony (2026-10-04)

- **What**: 37 programs that never fail (`build.py` writes them),
  each declaring a few variables at the corners of one integer type
  and asserting, in one expression, a conjunction of checks — one
  operator against the value ISO C gives it under ILP32's sizes and
  two's-complement wrap. `build.py` computes the expected values from
  the standard's conversion and arithmetic rules and from no
  interpreter in the registry. `testimony.jsonl` holds one record per
  program; `vectors.json` says which certificate vector of
  `registry/languages/c@7` each program became.
- **Oracle**: Apple clang 21.0.0 on the host (arm64, LP64), `-O0
  -fwrapv`, outside the seal. For 34 programs and 651 checks: as
  written the program returns from `main`, and with any one check's
  expected value moved by one it reaches `__assert_fail`. No dispute.
  The two programs that read inputs are identities and were run by a
  driver — `bytes` over every pair of bytes, `words` over a grid of
  corners (12 ints by 12 ints by 10 unsigned by 10 unsigned), which
  is testimony about the grid and an argument, not a test, beyond it.
  The programs use neither `long` nor plain `char`.
- **Not put to the oracle**: `stipulated_shift`, `stipulated_zero`,
  `stipulated_overflow` pin the fragment's own total semantics where
  C leaves the behaviour undefined (shift counts at and beyond the
  width and below zero; a zero divisor as SMT-LIB has it; the one
  signed overflow of division).
- **Why**: fault injection (`kernel/faults`, 2026-10-03) left 114 of
  200 sampled mutants of `c@5`'s two checkers unrefused, and a probe
  found one of them laxer than the intact checker: a zero-extending
  shift dropped from the machine the `induction` checker builds.
- **Where it entered**: `registry/languages/c@7`, by revision, as
  certificate vectors for both checkers (`induction` 010-046,
  `ranges` 006-042). The certificates are not testimony and not
  written here: each `ranges` certificate is what the admitted search
  `c-ai` wrote — for the programs it cannot prove, the boxes it wrote
  for the same program with a trivially true assertion — and each
  `induction` certificate is the smallest k the checker discharges;
  what makes a certificate a vector is that the checker discharges
  it, and what makes the program safe is the testimony above.
- **Status**: testimony (`KERNEL.md` §6). Nothing here executes in the
  kernel. Re-derive by running `build.py` on a host with clang.
