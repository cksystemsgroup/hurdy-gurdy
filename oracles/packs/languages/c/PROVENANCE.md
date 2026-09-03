# `c` — recorded testimony (anchor pack)

- **Source**: tag `era4-final`, `registry/languages/c/` (Era 4); the
  interpreter that pinned these expectations was carried over from
  gurdy/pairs/c_riscv (v3; the C leg of the audited spine — the host's pinned compiler as the real interpreter).
- **Observables**: halted, result (read from the pinned expectations)
- **Lineage declared at Era 4**: hurdy-gurdy:c-native
- **Root language at Era 4**: yes
- **Vectors**: 3, copied verbatim as `NNN.program` / `NNN.input` /
  `NNN.expect` — this generation's file layout under Era 3/4's
  conventions: `.input` is a step count, not a stimulus tape, and
  the observable names are the Era-3 interpreter's (see the README
  beside the packs). Each
  `.expect` was produced by the Era-3 interpreter at the tag and
  admitted under the Era-4 gate (vectors: 3,
  controls: 1).
- **Status**: testimony (`KERNEL.md` §6). Nothing here executes. A
  regenerated `c` cites this pack as an anchor and is admitted
  against it; a disagreement is a dispute to record and adjudicate,
  never a verdict. Re-derive or extend the testimony by running the
  Era-3 interpreter in a worktree at `era4-final`; never by importing
  it.
