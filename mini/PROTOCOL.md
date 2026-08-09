# The minikernel protocol — pre-registered

The question this program answers: **what is the smallest kernel
implementation from which an autonomous AI agent, starting empty,
reaches and expands frontiers?** Throw-away kernels K1, K2, … are the
instruments. Concepts are not the thing being minimized — the
implementation is. The more principled concepts the runs confirm or
discover, the better; the code must not bloat.

## Fixed concepts (not up for ablation)

Pairs (one edge kind; a solver pair's target is the result), routes
and the componentwise contract meet, determinism measured (run twice,
byte-compare), results as the only currency (witness / all(bound) /
partial), witness replay as existential certification, the grade
ladder with source re-discharge (claimed < checked < certified),
two-sided falsifiability (controls that must fail), the routing
contract (decides / maps / bound caps), the frontier as the
non-terminal bests, the append-only log with a byte-identically
regenerating report, pinned benchmarks, plug-pull safety, and the
conjecture order (semantics first) as agent guidance.

## What varies: mechanisms

Each kernel variant may change *how* a concept is implemented, never
whether it holds. Probes queued: admission evidence as a gate-log
event rather than a manifest stamp (K1 does this); one registry
namespace instead of languages/ + pairs/ trees (K1 does this);
language as a degenerate pair (one gate path); discharge engines as
registry entries reusable across solvers; routes checked rather than
enumerated; label sequestration vs. visible-plus-audit (K1: visible).

## The measure

Per kernel: **code LOC** (the kernel file), **contract LOC** (the
agent-facing CONTRACT.md), and the **concept ledger** — each concept
marked *confirmed* (some run failed without it or through its
absence), *unexercised* (no run needed it; probe harder), or
*discovered* (a failure forced a concept no design had).

## Domains and benchmarks

Three domains, two benchmarks each, all engines host-local. Every
benchmark is hand-curated, tiny, tiered, with labels fixed by
construction:

- **btor2** (hardware): btormc, pono, AVR, ABC, z3 reachable on PATH.
  Tiers: bounded reach/unreach; unbounded asks needing IC3 or
  k-induction; an expansion tier only an invariant certificate or a
  disjoint engine can improve.
- **dimacs** (SAT): cadical on PATH; drat-trim and cake_lpr for the
  certificate tier. Tiers: satisfiable (witness replay), unsatisfiable
  (all(inf) claimed), and the expansion tier: the same unsats lifted
  claimed → certified via DRAT re-checking.
- **c** (software): cbmc and the system C compiler on PATH. The agent
  must invent I_s itself (compile-and-run is the expected move).
  Tiers: assertion violations with concrete replayable inputs; safe
  loop-free programs (complete verdicts); loopy programs where a
  bounded unwind reaches level 1 and `--unwinding-assertions` or an
  invariant argument expands to all(inf).

Question observables per domain are fixed by the benchmark files:
`bad` (btor2), `sat` (dimacs), `violation` (c).

## The run protocol

One autonomous run per (kernel, domain), presented with **both**
benchmarks of the domain at once. Bare room: a fresh working
directory containing exactly `kernel.py`, `CONTRACT.md`, and
`benchmarks/`; engines on PATH; **no quarry, no repo, no network
beyond the agent's own model**. Pinned model and prompt; hard wall
and turn budgets; **zero user intervention** — a run that asks a
question has failed. Everything archived: transcript, final registry,
gate log, run logs, reports.

## Success criteria (pre-registered)

**Reach** — R1: no recorded verdict contradicts a benchmark label.
R2: `report` regenerates byte-identically from the log. R3: every
non-terminal question's best result carries progress evidence (a
partial that says how far and why). R4: zero interventions.

**Expand** — E1: after the first complete map, at least one strict
improvement per benchmark (level, bound, or grade — never cost) where
the curation makes one possible, visible in the log as a later record
whose key exceeds the earlier best.

## The audit (outside the kernel, after each run)

A1: independently replay every recorded witness through the language
entry's interpreter. A2: re-check a sample of universal claims with
an engine the agent did not register. A3: read the gate log for
evidence the kernel did not produce. A4: diff `report` output against
the committed report. A run passes only if the audit does.

## Iteration and settlement

A failed run names the mechanism (or missing concept) that failed;
the next kernel changes exactly that. A clean pass queues ablations.
**Settled** = a kernel whose six runs all reach and expand, and for
which every retained mechanism has a failing ablation run on record.
The frontier paper is then about that kernel: its concept ledger, and
what the agents did to reach their frontiers.

## Amendment 1 (2026-08-09): expand tiers v2

The first three K1 runs showed agents building their best kit —
certificate printers included — before first play, arriving at
maximal maps: E1 vacuous three times. Re-curation adds one
expansion-forcing question per benchmark (5 total), each verified
unclosable by a careful first kit at the default wall:
`parity32-inf` / `mod4-32-inf` (btor2: 2^31-state parity arguments —
explicit closure infeasible, BMC cannot reach inf, plain k-induction
fails; IC3-class engines close them instantly), `php1110-wall` /
`php1211-hard` (dimacs: pigeonhole past the 60 s wall — 56 s and
beyond-every-wall respectively; labels are theorems, php(11,10) also
engine-confirmed at 300 s), and `bigloop-safe` (c: 60k-iteration
safe loop that wall-blocks cbmc at full unwind; label arithmetic
plus 304 sampled concrete executions). c-straightline deliberately
keeps no expand tier; E1 applies where curation makes one possible.
