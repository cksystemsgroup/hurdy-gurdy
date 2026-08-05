# The frontier paper

A **new submission** (not a version of *Untrusted Authors, Trusted
Answers*): the map is the contribution and the calculus is cited as
the means — `FRONTIER-PLAN.md` §4 (retired to git history 2026-08-05 — [`HISTORY.md`](../../HISTORY.md)). Shares
only `../references.bib` with the instrument paper; the preamble is
deliberately from-scratch and minimal. `make` builds `frontier.pdf`.

**Title:** *The hurdy-gurdy Platform — Exploring the Frontier of
Reducible Decidability in Practice.*

State (2026-08-05): **all ten sections written** (14 pp), in lockstep
with the mechanization (`../mechanization/Calculus/Frontier.lean`;
statements cite Lean names inline, and a statement without a Lean
name says where its content lives instead). The paper deliberately
carries **no measurements section**: §7 is a summary of where the
experiments stand — every number read from the deposited
`hwmcc-sosylab-beem` ledger under `results/`, from which the full
report regenerates byte-identically — and §8 is the staged discovery
program, `INVERSION.md` (retired to git history — [`HISTORY.md`](../../HISTORY.md)) distilled to paper
scale. The full prose saturation report that briefly stood as §7
(`sections/benchmarks.tex`, iterations 0–5) is preserved in git
history at `a0bb1ee`/`343cd5a`. Four figures illustrate the
load-bearing objects — the answerability filtration (§2), the
commuting square (§3), one loop iteration with the valve and the
lanes (§4), and the square's four unknowns (§8). The build is
clean: no errors, no overfull hboxes (one 1.9 pt vbox residual,
below the tolerance the instrument paper itself ships with).

- §1 introduction (platform-first: explore the frontier, eventually
  push it; saturating benchmarks is the way there);
- §2 the frontier problem (the filtration, the diagnosis, the
  three-tier currency, saturation, the map);
- §3 the instrument as means (the requirement-table spine);
- §4 the loop (two loops, the valve and the mandate, the three
  production lanes, CEGAR as the cost engine, the structural
  one-iteration driver);
- §5 the facilitation theorems F1–F6 + currency lemmas + ablations +
  the collected trusted base;
- §6 the domain kit (**K1–K4 named here — the definition site**;
  `INVERSION.md` cites this vocabulary), the design oracle
  (extraction operators; the fragment atlas — `gurdy/core/atlas.py`),
  challenge bundles, and the pre-registered HWMCC protocol;
- §7 where the experiments stand: the seven-iteration
  `hwmcc-sosylab-beem` campaign summarized (curve 79→81 of 110 under
  each iteration's caps; 82 ever answered, four at every depth; one
  in-set board entry, 29 citing questions; enumeration closed, not
  saturated), the player-v2 separation cited from the instrument
  paper, and the conservativity reading — the loop discovers
  instruments, never facts;
- §8 beyond cartography: the square's four unknowns, the discovery
  ladder L0–L3b, F7 (unfalsifiable deposit, stated), the second kit
  K5–K7, the CRN genericity control — staged design, nothing landed,
  the walls unmoved;
- §9 related work (now incl. conjecture generation / theory
  exploration); §10 limitations and conclusion.
