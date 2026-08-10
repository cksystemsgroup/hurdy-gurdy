# Audit — K1, dimacs, sonnet 250 turns, v2 tiers (2026-08-10):
REACH + EXPAND both PASS — and this run completes K1's protocol

**E1 on both benchmarks.** `php1110-wall` and `php1211-hard` each
read: honest wall-block partials (cadical; for the hard one z3 too),
then `all(inf)` certified via `dimacs-pigeonhole` — the structural
counting-argument prover, independently rebuilt in this run — with
z3 corroborating where it can. The question curated to sit beyond
every engine wall closed by structure, inside a completed run.

**REACH**: 10/10 terminal across both maps, labels matched, SUMMARY
within budget, zero interventions.

**Audit**: A1 8/8 witnesses independently replayed. A2: bitwuzla
(never registered) agrees on every unsat it can reach — php(12,11)
excluded as beyond it too; that label is a theorem. Adversarial
probe of the prover: abstains on satisfiable php(4,4) and on
php(12,11) weakened by one clause. A3 gate log clean. A4
byte-identical regeneration.

**With this run, K1's pre-registered demonstration is complete:
three domains, two benchmarks each, reached and expanded by
autonomous agents from the empty 595-line kernel, every run audited
from outside it.**
