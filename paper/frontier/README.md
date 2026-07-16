# The frontier paper

A **new submission** (not a version of *Untrusted Authors, Trusted
Answers*): the map is the contribution and the calculus is cited as
the means — [`FRONTIER-PLAN.md`](../../FRONTIER-PLAN.md) §4. Shares
only `../references.bib` with the instrument paper; the preamble is
deliberately from-scratch and minimal. `make` builds `frontier.pdf`.

**Title:** *The hurdy-gurdy Platform — Mapping the Frontier of
Reducible Decidability in Practice.*

Phase-4 state (2026-07-16): **complete except benchmarks**, by
design — all eight sections written, in lockstep with the
mechanization (`../mechanization/Calculus/Frontier.lean`; statements
cite Lean names inline, and a statement without a Lean name says
where its content lives instead):

- §1 introduction (platform-first: explore the frontier, eventually
  push it; saturating benchmarks is the way there);
- §2 the frontier problem (the filtration, the diagnosis, the
  three-tier currency, saturation, the map);
- §3 the instrument as means (the requirement-table spine);
- §4 the loop (two loops, the valve and the mandate, CEGAR as the
  cost engine, the structural one-iteration driver);
- §5 the facilitation theorems F1–F6 + currency lemmas + ablations +
  the collected trusted base;
- §6 the domain kit (frozen), the design oracle (extraction
  operators; the fragment atlas — `gurdy/core/atlas.py`), challenge
  bundles, and the **pre-registered HWMCC protocol** in place of a
  benchmarks section — no number from any run appears in the paper;
- §7 related work; §8 limitations and conclusion.

The missing section is the saturation report the protocol will
produce (`tools/frontier_loop.py` → `tools/saturation_report.py`).
