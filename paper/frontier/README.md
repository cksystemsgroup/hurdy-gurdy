# The frontier paper

A **new submission** (not a version of *Untrusted Authors, Trusted
Answers*): the frontier is the contribution and the calculus is cited
as the means. Shares only `../references.bib` with the instrument
paper; the preamble is deliberately from-scratch and minimal. `make`
builds `frontier.pdf`.

**Title:** *The hurdy-gurdy Platform — Exploring the Frontier of
Reducible Decidability in Practice.*

State (2026-08-06): **re-cut for the kernel architecture**
([`KERNEL.md`](../../KERNEL.md); Era 4 in
[`HISTORY.md`](../../HISTORY.md)) — nine sections, 7 pp, short by
design. The Era-3 version (the answerability filtration, the six
facilitation theorems F1–F6, the domain kit K1–K4, the valve and the
discovery ladder; 14 pp, in lockstep with
`../mechanization/Calculus/Frontier.lean`) is preserved whole in git
history at `4b17542`; §6 of the current paper accounts for where each
of its theorems went. The kernel properties cited in §6 live in
`kernel/mechanization/Kernel.lean`.

Experiments are deliberately only what the paper rests on (§7): the
seven-iteration `hwmcc-sosylab-beem` campaign — every number read
from the deposited ledger under `results/`, from which the full
report regenerates byte-identically — and the kernel demonstration
(`runs/btor2-demo/` in the repository). Four figures illustrate the
load-bearing objects: one edge kind — the commuting square and its
solver-pair degeneration (§2), the grade ladder with the
replay/re-discharge mirror (§3), one loop iteration without a valve
(§5), and the conjecture order as the square's unknowns (§5).

- §1 introduction: the frontier, the campaign's two lessons, the
  organizing move (one edge kind, results the only currency), the
  one-sentence trust story;
- §2 languages, pairs, results (roots cost trust; the directional
  square; solver pairs; the result schema; determinism measured);
- §3 certification and the grade ladder (claimed < checked <
  certified; corroborated orthogonal; contradiction events);
- §4 the frontier is the non-terminal results (the order; monotone
  by data structure);
- §5 the loop: semantics first, then syntax (the conjecture order
  (a)–(c); one gate, no valve; plug-pull; bootstrap from empty);
- §6 what is proved (kernel Lean: strict order, best_mono,
  terminal_ratchet, grade lemmas) and the six theorems re-accounted;
- §7 the experiments this paper rests on: the campaign that forced
  the redesign, and the carried-over three-question demonstration;
- §8 related work; §9 limitations and conclusion (three walls).
