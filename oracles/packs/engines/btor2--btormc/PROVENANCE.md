# `btor2--btormc` — recorded testimony (anchor pack)

- **Source**: tag `era4-final`, `registry/pairs/btor2--btormc/` (Era 4).
- **Kind at Era 4**: solver pair at `btor2`, deciding
  bad; engine lineage: btormc, boolector; budget
  {"inf_cap_k": 20, "wall_s": 60}. Carried over from gurdy/solvers/native_btor2.py (v3; incl. the canary discipline for the silent-exhaustion signal).
- **Corpus**: 2 programs, each with a `.q` question carrying the
  engine's **label** — the verdict the pinned engine (`oracles/bench/`)
  gave at admission (corpus: 2, controls:
  1).
- **Status**: engine testimony (`KERNEL.md` §6). The labels are an
  oracle's verdicts at its pinned version: they corroborate a
  generated search's results and enter as anchors with this
  provenance — never as a judge, never inside a play. Wall times for
  performance testimony must be re-measured on the playing host
  against the bench digest; none are recorded here.
