# `btor2--z3` — recorded testimony (anchor pack)

- **Source**: tag `era4-final`, `registry/pairs/btor2--z3/` (Era 4).
- **Kind at Era 4**: solver pair at `btor2`, deciding
  bad; engine lineage: z3, btor2-smtlib-operator-mapping; budget
  {"inf_cap_k": 20, "wall_s": 60}. Carried over from gurdy/pairs/btor2_smtlib/translate.py + lift.py + gurdy/solvers/z3_smt.py (v3; the bridged engine of the native-vs-bridged cross-check, as one solver pair).
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
