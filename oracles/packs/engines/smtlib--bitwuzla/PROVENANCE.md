# `smtlib--bitwuzla` — recorded testimony (anchor pack)

- **Source**: tag `era4-final`, `registry/pairs/smtlib--bitwuzla/` (Era 4).
- **Kind at Era 4**: solver pair at `smtlib`, deciding
  sat; engine lineage: boolector, bitwuzla; budget
  {"wall_s": 60}. Carried over from gurdy/solvers/bitwuzla_smt.py (v3; the second SMT codebase — boolector's successor, declared so agreement with btormc/pono is never over-counted).
- **Corpus**: 2 programs, each with a `.q` question carrying the
  engine's **label** — the verdict the pinned engine (`oracles/bench/`)
  gave at admission (corpus: 2, controls:
  2).
- **Status**: engine testimony (`KERNEL.md` §6). The labels are an
  oracle's verdicts at its pinned version: they corroborate a
  generated search's results and enter as anchors with this
  provenance — never as a judge, never inside a play. Wall times for
  performance testimony must be re-measured on the playing host
  against the bench digest; none are recorded here.
