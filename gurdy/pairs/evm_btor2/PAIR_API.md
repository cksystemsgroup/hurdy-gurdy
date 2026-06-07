# Registering `evm-btor2` under the generalized-pairs architecture

`main` was synced into this branch on 2026-06-06, bringing the generalized-pairs
architecture: the `Hop` genus / `Pair` species, a `Language` registry,
`routes()`, the generic `Chain` runner, `tier` / determinism / `preservation`,
the localizing chain alignment oracle, and the **BTOR2 ↔ SMT-LIB bridge**. See
`DESIGN_pair_taxonomy.md` and `DESIGN_generalized_pairs.md`.

When this branch's pillars are assembled and you register the `Pair`, build it
against the **current** API so it lands graph-first-class:

- `Pair` now subclasses `Hop`. In its construction set:
  - `in_lang="evm"`, `out_lang="btor2"`
  - `tier=Tier.transparent` (a transparent, schema-predictable lowering)
  - `preservation=Preservation(keeps=(...), discards=(...), note="...")`
- Register the source language once:
  `register_language(Language(id="evm", kind="input", semantics="..."))`
  (`btor2` is already registered by `riscv-btor2`.)
- Register with `register_pair(PAIR)` as before.

Once registered the pair is automatically **routable** (`routes("evm","btor2")`,
and `routes("evm","smtlib")` via the `btor2-smtlib` bridge) and
**cross-checkable** (dispatch its BTOR2 through native `z3-bmc` *and* through the
bridge to SMT-LIB, compare verdicts — a translator-bug detector).

Templates: `gurdy/pairs/riscv_btor2/__init__.py`, `gurdy/pairs/crn_smtlib/`,
`gurdy/pairs/btor2_smtlib/`.

**Do not merge this branch into `main` until the `Pair` is assembled, registered,
and its suite is green** — `main` stays shippable.
