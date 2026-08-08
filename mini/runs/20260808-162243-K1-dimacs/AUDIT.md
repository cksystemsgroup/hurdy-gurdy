# Audit — K1, dimacs, sonnet, 100-turn cap (2026-08-08, 17 min)

**REACH: PASS.** R1: all 8 verdicts match labels. R2: both reports
regenerate byte-identically (re-run during audit). R3: vacuous — no
open questions. R4: zero interventions (headless start to finish;
the run ended at the turn cap, after SUMMARY.md was written).

**EXPAND: vacuous, and that is a curation finding.** The agent built
its certificate discharge before first play, so the first complete
map was already maximal (every unsat certified, every verdict
corroborated) — no post-map strict improvement was possible. The
agent's own summary says why: at this size every engine agrees in
milliseconds. Protocol learning: the expand tier must be unreachable
by a first kit (an instance the default wall cannot close).

**Audit.** A1: all 16 recorded witnesses independently replayed
(lam + interp run by hand, outside the kernel): 16/16 fired. A2:
every universal claim re-checked by bitwuzla — an engine the agent
never registered — through an independent CNF-to-SMT2 encoding: all
agree. A3: gate.jsonl holds only kernel-written admission events
with consistent evidence shapes. A4: byte-identical regeneration.

**What the agent built** (from empty, unprompted): the dimacs
language (7 vectors, 3 mutants); cadical with LRAT proofs discharged
by cake_lpr (4 certificate mutants incl. a proof lifted from a
different formula — all rejected); z3 as a disjoint second lineage;
and a from-scratch DPLL solver emitting RUP refutation traces
verified by its own independent checker — an unprompted class-(a)
conjecture with a certificate printer.

**Concept ledger deltas.** Confirmed in action: replay, discharge,
corroboration, two-sided controls (incl. certificate mutants), the
gate-log admission mechanism. Unexercised: translation pairs,
routes, bound caps (single-language domain — watch btor2 and C).
