# Audit — K1, c, sonnet, 120-turn cap (2026-08-08, killed overnight
after the maps were complete)

**REACH: PASS.** 8/8 terminal, all labels matched; byte-identical
regeneration; zero interventions. The agent invented I_s from the
bare room — the compile-head interpreter (cc + a nondet harness) —
then built `c--cbmc` and `c--z3sym`, a z3-based symbolic executor,
BOTH with certificate discharge and certificate mutants: every safe
program certified, every verdict corroborated across the two
disjoint lineages.

**EXPAND: vacuous** — single play, maximal on arrival.

**Audit.** A1: 6/6 violation witnesses independently replayed. A2:
every universal claim re-verified by concrete execution with my own
compile harness — exhaustive over the guarded ranges (guard-safe
1004 runs, accum 35, downcount 45, loop-safe closed-form), 20k
samples on the one range too large to exhaust: zero violations,
all agree. A3: gate log clean. A4: both reports regenerate.
