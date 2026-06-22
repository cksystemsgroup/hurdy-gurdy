# Pair — `smiles-formula`  ·  SMILES → molecular formula

*Status: **partial** (the organic-subset linear single-bonded chain — bare
atoms `B C N O P S F Cl Br I` with implicit hydrogens; coverage **5/17**). A
compile pair and field-blindness witness; ported from v2, widened to the
organic-subset heteroatoms (SMILES interpreter `0.2`). The full translation
schema is in [`SPEC.md`](./SPEC.md); implementation under
[`gurdy/pairs/smiles_formula/`](../../gurdy/pairs/smiles_formula/).*

Translate a SMILES string to its molecular formula (Hill notation). This is
a **compile pair**, not a reasoning pair: its target is a representation, not
a solver input, so it has no solver and no `proved` tier — only a faithful,
deterministic re-representation. It exists to show the same pair machinery
and commuting-square contract carry an entirely **non-computational**
translation unchanged.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** SMILES — [`languages/smiles`](../../languages/smiles/README.md).
- **Target.** molecular formula —
  [`languages/molecular-formula`](../../languages/molecular-formula/README.md).
- **Translator `T`.** A schema-determined map: parse the SMILES molecular
  graph, apply implicit-hydrogen rules, count atoms, emit Hill notation.
  Deterministic and **schema-predictable**.
- **Source interpreter.** The **shared** SMILES interpreter (the graph
  reader) ([`languages/smiles`](../../languages/smiles/README.md)) — reused;
  contributed by this pair if first.
- **Target interpreter.** The **shared** molecular-formula reader/normalizer
  ([`languages/molecular-formula`](../../languages/molecular-formula/README.md))
  — reused.
- **Target-to-source interpreter `L`.** Maps a formula's atom multiset back
  to the source-graph observable (the multiset). There is no solver witness
  here; `L` is the trivial re-projection that lets the square be checked.
  Pair-owned.

## Projection `π`

The **atom multiset**. The pair preserves the multiset of atoms; it
**discards** connectivity (bonds, rings, stereochemistry) — an explicit,
honest loss ([`PATHS.md`](../../PATHS.md) §3).

## Fidelity target + evidence

- **`predicted`** — given the SMILES and the OpenSMILES + Hill-notation
  rules, the formula is determined byte-for-byte. A compile pair has no
  `proved` tier (no solver); its assurance is byte-prediction plus the
  square.

## Soundness story

The square commutes by construction: the atom multiset computed from the
source graph (`I_smiles`) equals the multiset of the emitted formula
(`L(I_formula(T(p)))`). Validate the SMILES reader against RDKit/InChI
([`languages/smiles`](../../languages/smiles/README.md),
[`PAIRING.md`](../../PAIRING.md) §6).

## Notes for the implementing agent

- This is the cheapest end-to-end witness that the architecture is
  field-blind — keep it small and exact.
- No solver, no certificate; the deliverable is the translator, the trivial
  `L`, and the declared `π` (atom multiset kept, connectivity discarded).

## Built — the organic-subset chain (`partial`, 5/17)

**Covered construct (end-to-end through the square):** the **organic-subset
linear single-bonded chain** — bare atoms `B C N O P S F Cl Br I` (alongside the
original carbon `C`) joined by implicit single bonds, with implicit hydrogens
filled by the pinned per-element valence rule (`B`3 `C`4 `N`3 `O`2 `P`3 `S`2
`F`/`Cl`/`Br`/`I`1; H = `max(0, normal_valence − single-bond degree)`). Linear
chains may now **mix elements**: `C` → `CH4`, `CC` → `C2H6`, `CCO` → `C2H6O`
(ethanol), `CN` → `CH5N`, `CF` → `CH3F`, `CCl` → `CH3Cl`, `O` → `H2O`, `N` →
`H3N`. The translator `T`, the carry-back `L`, and both shared interpreters
(`gurdy/languages/smiles/`, `gurdy/languages/molecular_formula/`) share one
source of truth — the molecular-formula language's `parse`/`to_hill` over the
same multiset — so the square commutes by construction.

This is the **heteroatom widening** of the original carbon-only slice (coverage
ratchet, [`BENCHMARKS.md`](../../BENCHMARKS.md) §5): **1/17 → 5/17**, nothing
dropped. It bumped the **shared SMILES interpreter to `0.2`** (AGENTS.md §3, an
additive valence-table change; carbon-chain behavior unchanged) and the
translator to `0.2`. The molecular-formula language was already general over
elements and needed no change.

**Fidelity: `predicted`.** Evidence: the self-contained schema in
[`SPEC.md`](./SPEC.md) (now with the per-element valence table) determines the
output bytes (Hill notation gives the canonical, host-independent element order);
a twice-and-diff test (`tests/test_smiles_formula.py`) confirms byte-identical
output for `T` and both interpreters (also verified across `PYTHONHASHSEED`); the
commuting-square oracle aligns `I_s(p) ≡_π L(I_t(T(p)))` on a heteroatom corpus.

**Out-of-scope → typed abort** (`unsupported: smiles:<construct>`,
[`BENCHMARKS.md`](../../BENCHMARKS.md) §3). Construct coverage **5/17** of the
spec-enumerable inventory (`coverage.measure` over
`gurdy/pairs/smiles_formula/inventory.py`). In scope: `organic-chain` (the
mixed-element single-bonded chain probe `CCO`) plus the four heteroatom probes
`organic-atom-N`/`-O`/`-Cl`/`-Br` (carbon-only before the widening, covered
now). The `unsupported` histogram (probe count blocked, by the construct named
first under left-to-right parsing; `bracket-atom` subsumes the
charge/isotope/stereo probes that live inside `[...]`):

```
aromatic-atom          1   (c1ccccc1)
bracket-atom           4   ([CH4] [NH4+] [13C] [C@H])
branch                 1   (C(C)C)
disconnection          1   (C.C)
double-bond            1   (C=C)
explicit-single-bond   1   (C-C)
ring-bond              1   (C1CCCCC1)
stereo-bond            1   (F/C=C/F)
triple-bond            1   (C#C)
```

**Tests:** `python -m unittest discover -s tests` (full repo suite: 584 tests,
2 host-skips, OK — includes the 25 `test_smiles_formula` tests:
per-element/per-molecule vs spec, twice-and-diff on `T` + both interpreters, the
commuting-square check on a heteroatom corpus, carry-back replay through `L`,
registration smoke, and the 5/17 coverage/histogram check).

**What we learned (PAIRING.md §9).** The widening was **purely additive in the
source-language layer**: the valence rule generalized from a single carbon
constant to a per-element table, and the parser from "count `C`s" to a longest-
match tokenizer over `{B C N O P S F Cl Br I}`. The target language
(molecular-formula) was already element-general, so the heteroatom widening
touched only `gurdy/languages/smiles/` (interp bump `0.1` → `0.2`) plus the
inventory; the pair's `T`/`L`/`π` were unchanged. Two subtleties worth
recording: (1) the simplified Hill convention this stack pins places hydrogen
*always second* when present, so carbon-free formulas read `H3N`, `H2O`, `H3B`
(not strict-IUPAC `BH3`); the brief fixes this convention, and because both
`I_s` and `L(I_t(T(p)))` use the same `to_hill`, the square commutes regardless.
(2) Once `F` became an in-scope atom, the `stereo-bond` probe `F/C=C/F` stopped
leaking as `organic-atom:F` and now correctly aborts at the `/` as
`stereo-bond` — the histogram got *more* honest, not less.

**Future widening** (coverage ratchet, [`BENCHMARKS.md`](../../BENCHMARKS.md)
§5): branches `()`, ring closures, multiple bonds (bond-order affects implicit
H), then bracket atoms / charges / isotopes / aromatic atoms / stereo, and
finally a public coverage anchor (RDKit/InChI canonical formula over a
ChEMBL/PubChem slice) as the external oracle.
