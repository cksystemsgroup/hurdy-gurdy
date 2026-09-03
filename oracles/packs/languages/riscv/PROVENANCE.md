# `riscv` — recorded testimony (anchor pack)

- **Source**: tag `era4-final`, `registry/languages/riscv/` (Era 4); the
  interpreter that pinned these expectations was carried over from
  gurdy/languages/riscv (v3; the RV64IMC user-ISA shared interpreter, Era-3-corroborated by the sail_riscv_sim differential).
- **Observables**: halted, pc, x5, x6 (read from the pinned expectations)
- **Lineage declared at Era 4**: hurdy-gurdy:riscv-interp
- **Root language at Era 4**: yes
- **Vectors**: 3, copied verbatim as `NNN.program` / `NNN.input` /
  `NNN.expect` — the format this generation's gate reads. Each
  `.expect` was produced by the Era-3 interpreter at the tag and
  admitted under the Era-4 gate (vectors: 3,
  controls: 1).
- **Status**: testimony (`KERNEL.md` §6). Nothing here executes. A
  regenerated `riscv` cites this pack as an anchor and is admitted
  against it; a disagreement is a dispute to record and adjudicate,
  never a verdict. Re-derive or extend the testimony by running the
  Era-3 interpreter in a worktree at `era4-final`; never by importing
  it.
