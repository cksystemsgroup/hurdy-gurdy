"""The kernel — the fixed part of hurdy-gurdy, outside the gate (KERNEL.md).

Five modules, stdlib only:

- ``runner``   — sealed deterministic execution with budgets
- ``registry`` — append-only registry: languages (with their evidence
  judges), pairs (with their translators and carry-backs), searches,
  domains
- ``results``  — the result core: schema, order, gap and trust, log,
  frontier, board, graph
- ``gate``     — the one gate: determinism, round-trips of every
  artifact a pair carries, certificate judges, controls, the
  generation rule
- ``driver``   — the two modes: play a benchmark, admit an entry, and
  the check-time moves (regrade), plus the printable trusted base

The kernel is generated like everything else in the tree, but it does
not enter through admission — it *is* the gate — so it is made solid
four ways (KERNEL.md §9): the proved half in Lean under
``mechanization/``; the operational half falsified by ``tests/``
(``python3 -m kernel.tests``); a second lineage of the pure half under
``second/``, generated clean-room and held to byte-agreement; and
review. This lineage is ``kernel-first-g1``.

The kernel ships empty — zero languages, zero transports, zero
domains — and it never trusts a claim it can measure. Generation
produces syntax; only interpretation produces truth: the LLM never
writes a result — only the kernel does, by running judges over
transported evidence.
"""

LINEAGE = "kernel-first-g1"
