# Audit — K1, c, sonnet, v2 tiers (2026-08-10): REACH + EXPAND both PASS

**E1 fired in both flavors.** `bigloop-safe`: cbmc's honest bounded
facts first (`all(1024)` certified — level 1 against the inf ask),
then `all(inf)` certified via `c-loopsum`, a conjectured loop
summarizer — the level/bound expansion. `mulcomm-safe`: cbmc's
wall-block partial first, then `all(inf)` certified via `c-z3bmc`,
the word-level engine conjecture the tier was curated to force —
and the summarizer honestly abstains on it ("not exactly one loop").

**REACH**: 10/10 terminal across both maps, labels matched, zero
interventions, SUMMARY written within budget.

**Audit**: A1 8/8 witnesses independently replayed. A2: 609 concrete
executions with an independent compile harness (boundary values +
seeded samples) — zero violations, all universal claims agree. A3:
gate log clean — four entries, every solver carrying certificate
mutants. A4: both reports regenerate byte-identically.

The registry: the c language (10 vectors, 6 mutants), c-cbmc and
c-z3bmc (both discharging), and c-loopsum — a genuine class-(a)
conjecture that turns single-loop accumulation into closed-form
obligations.
