# Registering `ebpf-btor2` under the generalized-pairs architecture

`main` was synced into this branch on 2026-06-06, bringing the generalized-pairs
architecture: the `Hop` genus / `Pair` species, a `Language` registry,
`routes()`, the generic `Chain` runner, `tier` / determinism / `preservation`,
the localizing chain alignment oracle, and the **BTOR2 ↔ SMT-LIB bridge**. See
`DESIGN_pair_taxonomy.md` and `DESIGN_generalized_pairs.md`.

When this branch's pillars are assembled and you register the `Pair` (the P6+
registration step), build it against the **current** API so it lands
graph-first-class:

- `Pair` now subclasses `Hop`. In its construction set:
  - `in_lang="ebpf"`, `out_lang="btor2"`
  - `tier=Tier.transparent` (this is a transparent, schema-predictable lowering)
  - `preservation=Preservation(keeps=(...), discards=(...), note="...")`
- Register the source language once:
  `register_language(Language(id="ebpf", kind="input", semantics="..."))`
  (`btor2` is already registered by `riscv-btor2`.)
- Register with `register_pair(PAIR)` as before.

Once registered, the pair is automatically:

- **routable**: `routes("ebpf", "btor2")`, and `routes("ebpf", "smtlib")` via the
  `btor2-smtlib` bridge;
- **cross-checkable**: dispatch its BTOR2 through the native `z3-bmc` *and*
  through the bridge to SMT-LIB, and compare verdicts — a translator-bug
  detector (`DESIGN_generalized_pairs.md` §6);
- integrated into the graph's determinism / trust / preservation computations.

Templates: `gurdy/pairs/riscv_btor2/__init__.py` (full reasoning pair),
`gurdy/pairs/crn_smtlib/` (a from-scratch reasoning pair), and
`gurdy/pairs/btor2_smtlib/` (the bridge).

**Do not merge this branch into `main` until the `Pair` is assembled, registered,
and its suite is green** — `main` stays shippable.
