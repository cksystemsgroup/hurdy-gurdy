# `btor2--avr` — recorded testimony (anchor pack)

- **Source**: tag `era4-final`, `registry/pairs/btor2--avr/` (Era 4).
- **Kind at Era 4**: solver pair at `btor2`, deciding
  bad; engine lineage: avr, yices; budget
  {"memout_mb": 8192, "wall_s": 60}. Carried over from gurdy/solvers/avr_btor2.py (v3; HWMCC'20 winner, host-built Yices2-only — the first lineage disjoint from every boolector-family engine).
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
