# The frontier paper

A **new submission** (not a version of *Untrusted Authors, Trusted
Answers*): the map is the contribution and the calculus is cited as
the means — [`FRONTIER-PLAN.md`](../../FRONTIER-PLAN.md) §4. Shares
only `../references.bib` with the instrument paper; the preamble is
deliberately from-scratch and minimal. `make` builds `frontier.pdf`.

**Title:** *The hurdy-gurdy Platform — Exploring the Frontier of
Reducible Decidability in Practice.*

Phase-4 state (2026-07-16): **complete except benchmarks**, by
design — all eight sections written, in lockstep with the
mechanization (`../mechanization/Calculus/Frontier.lean`; statements
cite Lean names inline, and a statement without a Lean name says
where its content lives instead). Updated 2026-07-18: the subtitle
is now *Exploring…* (the paper checks direction and lays the ground
for the experiments, not just the map), and the synthesis lane
([`SYNTHESIS.md`](../../SYNTHESIS.md)) is reflected throughout —
the `native-procedure` demand and its atlas in/out line (§2, §6),
the third production lane with solver briefs, lineage-aware
corroboration, and the admission gate (§4), the landed oracle
operators (§6), and the staged-extensions close (§8, with the
proof-demand design of [`PROVING.md`](../../PROVING.md) named as
designed-not-built). Claims about synthesis are deliberately capped
at tooled-shadow-first: the reference inhabitant is hand-built, no
autonomy rung exists, and no synthesized procedure is claimed to
have moved a frontier. Three figures illustrate the load-bearing
objects — the answerability filtration (§2), the commuting square
(§3), one loop iteration with the valve and the lanes (§4) — and
the build is overfull-free (the one residual is a 1pt vbox on the
last page, below the tolerance the instrument paper itself ships
with).

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
