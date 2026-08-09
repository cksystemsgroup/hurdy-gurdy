# Audit — K1, btor2, sonnet, 120-turn cap (2026-08-08, ~31 min)

**REACH: PASS.** 12/12 terminal across both maps, all labels matched;
byte-identical regeneration (A4); zero interventions. The agent built
the btor2 language (8 vectors, 5 mutants), btormc as an external
engine, and its flagship: `btor2-explicit`, a from-scratch
explicit-state reachability engine whose unbounded claims carry
certificates (reachable-set closure), discharged and defended by 4
certificate mutants. All four inf asks certified — honestly
uncorroborated where only its own lineage can see that far, and
btormc's partials say exactly why ("k-induction success is not
reliably readable from btormc's plain output").

**EXPAND: vacuous again** — play 0 was already maximal; the agent
built its certified engine before first play.

**Audit.** A1: 18/18 witnesses independently replayed. A2: all four
inf claims re-checked by pono (never registered by the agent) — all
agree. A3: gate log clean. A4: both reports regenerate.
