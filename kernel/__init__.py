"""The kernel — the fixed, hand-written part of hurdy-gurdy (KERNEL.md).

Five modules, stdlib only:

- ``runner``   — sandboxed deterministic execution with budgets
- ``results``  — the result core: schema, order, log, frontier, report
- ``registry`` — append-only registry of languages and pairs
- ``checker``  — admission: determinism, square, replay, controls
- ``driver``   — one loop iteration: play a benchmark, record, report

The kernel never trusts a claim it can measure, and the LLM never
writes a result: only the kernel does, by running checked code.
"""
