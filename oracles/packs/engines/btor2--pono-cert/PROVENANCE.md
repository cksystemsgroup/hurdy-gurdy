# `btor2--pono-cert` — recorded testimony (anchor pack)

- **Source**: tag `era4-final`, `registry/pairs/btor2--pono-cert/` (Era 4).
- **Kind at Era 4**: solver pair at `btor2`, deciding
  bad; engine lineage: pono, smt-switch, bitwuzla, boolector; budget
  {"frames_k": 10000, "modes": ["ic3bits", "mbic3", "ind"], "wall_s": 60}. Carried over from gurdy/solvers/pono_btor2.py + gurdy/solvers/invariant.py (v3; the unbounded leg with its certificate printer and the base/step/safe re-discharge; supersedes btor2--pono, pruned between runs).
- **Corpus**: 3 programs, each with a `.q` question carrying the
  engine's **label** — the verdict the pinned engine (`oracles/bench/`)
  gave at admission (corpus: 3, controls:
  2).
- **Status**: engine testimony (`KERNEL.md` §6). The labels are an
  oracle's verdicts at its pinned version: they corroborate a
  generated search's results and enter as anchors with this
  provenance — never as a judge, never inside a play. Wall times for
  performance testimony must be re-measured on the playing host
  against the bench digest; none are recorded here.
