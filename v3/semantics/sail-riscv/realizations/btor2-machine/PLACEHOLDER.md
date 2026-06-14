# btor2-machine realization (asset slot)

This directory holds the **verified BTOR2 machine model** for rv64 — the
output of `tools/sail_btor2_machine` — once a **machine-build agent** has
generated it and the **machine gate** has proven it equivalent to the Sail
reference.

Expected contents after the agent runs:

- `model.btor2` — the universal rv64 CPU transition system.
- `decode_map.json` — opcode → execute-fragment map.
- `provenance.json` — per-instruction `{sail_clause, btor2_fragment}`.
- `MachineFidelityReport.json` — whole-machine equivalence result.

Until then, `GROUP.yaml`'s `equivalence: PENDING` keeps any pair's
`machine_tool` path **unavailable** (the merge policy refuses to rely on an
un-gated realization). This is the asset a differential-only pair may
*instantiate* at runtime but may **not** read during construction.
