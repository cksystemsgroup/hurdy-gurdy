# Audit — K1, btor2, sonnet 250 turns, v2 tiers (2026-08-10):
REACH + EXPAND both PASS

**E1 fired, and each expand question stacks the whole ladder in one
log**: btormc's honest BMC partial (kmax 250), btor2-explicit's
certified all(199999) — the bounded ratchet pushed six digits — pono
claimed all(inf), and `btor2-congruence` certified all(inf),
corroborated across disjoint lineages. The congruence entry is a
genuine invented decision procedure: modular-invariant search
("state mod 2^k == r") over bitvector SMT queries with base /
inductive / safe obligations — the invariant re-discharge pattern,
independently reinvented — precisely where explicit BFS caps out and
plain induction fails.

**REACH**: 14/14 terminal across both maps, labels matched, SUMMARY
written within budget, zero interventions.

**Audit**: A1 23/23 witnesses independently replayed. A2 (AVR, never
registered by the agent): agrees on frozen-inf and blocked-inf;
self-reports memout on the four parity/mod questions — inconclusive,
not disagreement; their labels are theorems (parity arguments) and
were engine-verified at curation. A3 gate log clean (five entries,
certificate mutants on the certifying solvers). A4 byte-identical.
