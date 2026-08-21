"""The kernel — the fixed, hand-written part of hurdy-gurdy (KERNEL.md).

Five modules, stdlib only:

- ``runner``   — sealed deterministic execution with budgets
- ``registry`` — append-only registry: languages (with their evidence
  judges), pairs (with their channel sets), searches, domains
- ``results``  — the result core: schema, order, gap and trust, log,
  frontier, board, graph
- ``checker``  — the one gate: determinism, per-channel round-trips,
  evidence judges, two-sided controls, the generation rule
- ``driver``   — the two modes: play a benchmark, admit an entry, and
  the check-time moves (regrade), plus the printable trusted base

The kernel ships empty — zero languages, zero transports, zero
domains — and it never trusts a claim it can measure. Generation
produces syntax; only interpretation produces truth: the LLM never
writes a result — only the kernel does, by running judges over
transported evidence.
"""
