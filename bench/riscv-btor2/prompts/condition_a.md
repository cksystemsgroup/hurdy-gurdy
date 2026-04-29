# Condition A — source-only baseline

You have:

- The RISC-V assembly source above.
- The disassembled instructions above.
- A scratch sandbox if you want to mentally simulate execution; you
  may NOT call out to a solver, model checker, or any external tool.

You do **not** have:

- An SMT solver.
- A model checker.
- The `riscv-btor2` pair's translation, schema, or tool surface.

Reason from the RISC-V semantics directly. Commit to a verdict and,
if `reachable`, a witness fingerprint per the schema above.

If you cannot decide from unaided reasoning within the time budget,
emit `unknown` with calibrated confidence. The benchmark explicitly
scores `unknown` separately from wrong-verdict; the latter is the
expensive failure mode.
