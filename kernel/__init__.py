"""The kernel — the fixed, hand-written part of hurdy-gurdy (KERNEL.md).

Five modules, stdlib only:

- ``runner``   — sealed deterministic execution with budgets
- ``results``  — the result core: schema, order, log, frontier, report
- ``registry`` — append-only registry: languages, pairs, terminals, domains
- ``checker``  — the one gate: determinism, square, replay, controls,
  the generation rule
- ``driver``   — the two modes: play a benchmark, admit an entry

The kernel ships empty — zero languages, zero pairs, zero terminals —
and it never trusts a claim it can measure. The LLM never writes a
result: only the kernel does, by running checked, generated code.
"""
